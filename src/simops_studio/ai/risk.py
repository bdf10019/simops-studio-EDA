"""Explainable and guarded simulation-risk model.

The model predicts the probability that a parameter set will violate the configured
impedance target. It only prioritizes work and previews risk; simulation remains the
source of truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split

from simops_studio.hashing import hash_file
from simops_studio.models import PDN_PARAMETER_NAMES, SimulationCase


class RiskModelError(RuntimeError):
    """Raised when risk model training or loading cannot be completed safely."""


@dataclass(frozen=True)
class RiskScoring:
    cases: list[SimulationCase]
    source: str
    out_of_domain_count: int
    metadata: dict[str, Any] | None


FEATURE_SCALES = {
    "plane_resistance_ohm": 1e3,
    "plane_inductance_h": 1e9,
    "capacitance_f": 1e6,
    "capacitor_esr_ohm": 1e3,
    "capacitor_esl_h": 1e9,
}


def _feature_row(parameters: dict[str, Any]) -> list[float]:
    return [float(parameters[name]) * FEATURE_SCALES[name] for name in PDN_PARAMETER_NAMES]


def _matrix(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    features: list[list[float]] = []
    labels: list[int] = []
    for row in rows:
        parameters = row["parameters"]
        features.append(_feature_row(parameters))
        labels.append(1 if row["pass_fail"] == "FAIL" else 0)
    return np.asarray(features, dtype=np.float64), np.asarray(labels, dtype=np.int64)


def train_risk_model(
    rows: list[dict[str, Any]], model_path: str | Path, *, min_samples: int = 12
) -> dict[str, Any]:
    if len(rows) < min_samples:
        raise RiskModelError(f"need at least {min_samples} completed simulations, got {len(rows)}")
    x, y = _matrix(rows)
    raw_x = np.asarray(
        [
            [float(row["parameters"][name]) for name in PDN_PARAMETER_NAMES]
            for row in rows
        ],
        dtype=np.float64,
    )
    classes, counts = np.unique(y, return_counts=True)
    if set(classes.tolist()) != {0, 1}:
        raise RiskModelError("training data must contain both PASS and FAIL cases")
    if int(counts.min()) < 2:
        raise RiskModelError("each outcome class needs at least two cases")

    test_count = max(4, round(len(rows) * 0.25))
    test_count = min(test_count, len(rows) - 4)
    if test_count < 2:
        raise RiskModelError("not enough data for a holdout evaluation")
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=test_count,
        random_state=42,
        stratify=y,
    )
    evaluation_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        min_samples_leaf=1,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
    )
    evaluation_model.fit(x_train, y_train)
    prediction = evaluation_model.predict(x_test)

    final_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        min_samples_leaf=1,
        class_weight="balanced",
        random_state=42,
        n_jobs=1,
    )
    final_model.fit(x, y)
    bounds = {
        name: {
            "minimum": float(raw_x[:, index].min()),
            "maximum": float(raw_x[:, index].max()),
        }
        for index, name in enumerate(PDN_PARAMETER_NAMES)
    }
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "model_type": "RandomForestClassifier",
        "purpose": "simulation queue prioritization and risk preview only",
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "training_samples": len(rows),
        "class_counts": {"PASS": int((y == 0).sum()), "FAIL": int((y == 1).sum())},
        "holdout_samples": len(y_test),
        "holdout_accuracy": float(accuracy_score(y_test, prediction)),
        "holdout_balanced_accuracy": float(balanced_accuracy_score(y_test, prediction)),
        "confusion_matrix_labels": ["PASS", "FAIL"],
        "confusion_matrix": confusion_matrix(y_test, prediction, labels=[0, 1]).tolist(),
        "features": list(PDN_PARAMETER_NAMES),
        "feature_scales": FEATURE_SCALES,
        "feature_importance": {
            name: float(final_model.feature_importances_[index])
            for index, name in enumerate(PDN_PARAMETER_NAMES)
        },
        "training_bounds": bounds,
        "sklearn_version": sklearn.__version__,
        "guardrails": [
            "Out-of-domain inputs receive a neutral 0.5 risk score.",
            "Predictions never replace simulator PASS/FAIL results.",
            "Retrain and revalidate when topology, target, or parameter ranges change.",
        ],
    }
    destination = Path(model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": final_model,
            "features": list(PDN_PARAMETER_NAMES),
            "bounds": bounds,
            "metadata": metadata,
        },
        destination,
    )
    metadata["model_sha256"] = hash_file(destination)
    metadata_path = destination.with_suffix(destination.suffix + ".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def score_cases(cases: list[SimulationCase], model_path: str | Path) -> RiskScoring:
    path = Path(model_path)
    if not path.exists():
        return RiskScoring(cases=list(cases), source="neutral-fallback", out_of_domain_count=0, metadata=None)
    try:
        bundle = joblib.load(path)
        if bundle.get("features") != list(PDN_PARAMETER_NAMES):
            raise RiskModelError("model feature contract does not match this application")
        model = bundle["model"]
        bounds = bundle["bounds"]
        metadata = dict(bundle["metadata"])
        metadata["model_sha256"] = hash_file(path)
    except Exception as exc:
        if isinstance(exc, RiskModelError):
            raise
        raise RiskModelError(f"cannot load risk model: {exc}") from exc

    in_domain_indices: list[int] = []
    in_domain_features: list[list[float]] = []
    scores = [0.5] * len(cases)
    for index, case in enumerate(cases):
        raw_feature_row = [float(case.parameters[name]) for name in PDN_PARAMETER_NAMES]
        in_domain = all(
            bounds[name]["minimum"] <= raw_feature_row[position] <= bounds[name]["maximum"]
            for position, name in enumerate(PDN_PARAMETER_NAMES)
        )
        if in_domain:
            in_domain_indices.append(index)
            in_domain_features.append(_feature_row(case.parameters))
    if in_domain_features:
        probabilities = model.predict_proba(np.asarray(in_domain_features, dtype=np.float64))
        class_index = list(model.classes_).index(1)
        for index, probability in zip(in_domain_indices, probabilities, strict=True):
            scores[index] = float(probability[class_index])
    scored = [replace(case, risk_score=scores[index]) for index, case in enumerate(cases)]
    return RiskScoring(
        cases=scored,
        source="trained-model",
        out_of_domain_count=len(cases) - len(in_domain_indices),
        metadata=metadata,
    )
