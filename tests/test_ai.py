from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from simops_studio.ai import RiskModelError, score_cases, train_risk_model
from simops_studio.cases import expand_cases
from simops_studio.config import load_project_config
from simops_studio.eda.builtin import BuiltInPdnAdapter


ROOT = Path(__file__).resolve().parents[1]


class RiskModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_project_config(ROOT / "examples" / "project.yaml")
        self.cases = expand_cases(self.config)
        adapter = BuiltInPdnAdapter()
        self.rows = []
        for case in self.cases:
            result = adapter.simulate(
                case,
                self.config.simulation.frequency,
                self.config.simulation.target_impedance_ohm,
            )
            self.rows.append(
                {
                    "parameters": case.parameters,
                    "pass_fail": "PASS" if result.passed else "FAIL",
                }
            )

    def test_train_score_and_out_of_domain_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "risk.joblib"
            metadata = train_risk_model(self.rows, model_path, min_samples=12)
            self.assertEqual(24, metadata["training_samples"])
            self.assertGreaterEqual(metadata["holdout_balanced_accuracy"], 0.5)
            scoring = score_cases(self.cases, model_path)
            self.assertEqual("trained-model", scoring.source)
            self.assertNotEqual({0.5}, {round(case.risk_score, 6) for case in scoring.cases})

            outside = replace(
                self.cases[0],
                parameters={**self.cases[0].parameters, "capacitance_f": 1.0},
            )
            guarded = score_cases([outside], model_path)
            self.assertEqual(1, guarded.out_of_domain_count)
            self.assertEqual(0.5, guarded.cases[0].risk_score)

    def test_insufficient_training_data_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RiskModelError, "at least"):
                train_risk_model(self.rows[:4], Path(directory) / "risk.joblib", min_samples=12)


if __name__ == "__main__":
    unittest.main()

