"""YAML/JSON loading and strict project validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml

from simops_studio.hashing import hash_value
from simops_studio.models import (
    PDN_PARAMETER_NAMES,
    AiConfig,
    ConfigurationError,
    FrequencyConfig,
    PcbConfig,
    PcbRules,
    ProjectConfig,
    SimulationConfig,
    WorkerConfig,
    WorkflowConfig,
)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a mapping")
    return value


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ConfigurationError(f"{label} must be finite and greater than zero")
    return result


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"{label} must be a non-negative integer")
    return value


def _resolve(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be a non-empty path")
    path = Path(value)
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _load_raw(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"cannot read project file: {exc}") from exc
    try:
        if path.suffix.lower() == ".json":
            value = json.loads(text)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            value = yaml.safe_load(text)
        else:
            raise ConfigurationError("project file must use .yaml, .yml, or .json")
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"invalid project syntax: {exc}") from exc
    return _mapping(value, "project document")


def load_project_config(path: str | Path) -> ProjectConfig:
    source_path = Path(path).resolve()
    raw = _load_raw(source_path)
    base_dir = source_path.parent

    project = _mapping(raw.get("project"), "project")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError("project.name must be a non-empty string")
    description = project.get("description", "")
    if not isinstance(description, str):
        raise ConfigurationError("project.description must be a string")

    simulation_raw = _mapping(raw.get("simulation"), "simulation")
    adapter = simulation_raw.get("adapter", "builtin-pdn")
    if adapter not in {"builtin-pdn", "ngspice", "external-command"}:
        raise ConfigurationError("simulation.adapter is not supported")
    frequency_raw = _mapping(simulation_raw.get("frequency"), "simulation.frequency")
    frequency = FrequencyConfig(
        start_hz=_positive_number(frequency_raw.get("start_hz"), "frequency.start_hz"),
        stop_hz=_positive_number(frequency_raw.get("stop_hz"), "frequency.stop_hz"),
        points=int(_positive_number(frequency_raw.get("points"), "frequency.points")),
    )
    if frequency.stop_hz <= frequency.start_hz:
        raise ConfigurationError("frequency.stop_hz must be greater than start_hz")
    if frequency.points < 3 or frequency.points > 100_000:
        raise ConfigurationError("frequency.points must be between 3 and 100000")

    base_raw = _mapping(simulation_raw.get("base"), "simulation.base")
    pdn_base: dict[str, float] = {}
    for key in PDN_PARAMETER_NAMES:
        pdn_base[key] = _positive_number(base_raw.get(key), f"simulation.base.{key}")

    sweep_raw = _mapping(simulation_raw.get("sweep", {}), "simulation.sweep")
    sweep: dict[str, tuple[float, ...]] = {}
    for key, values in sweep_raw.items():
        if key not in PDN_PARAMETER_NAMES:
            raise ConfigurationError(f"unsupported sweep parameter: {key}")
        if not isinstance(values, list) or not values:
            raise ConfigurationError(f"simulation.sweep.{key} must be a non-empty list")
        sweep[key] = tuple(
            _positive_number(item, f"simulation.sweep.{key}") for item in values
        )

    simulation = SimulationConfig(
        adapter=adapter,
        frequency=frequency,
        target_impedance_ohm=_positive_number(
            simulation_raw.get("target_impedance_ohm"),
            "simulation.target_impedance_ohm",
        ),
        base=pdn_base,
        sweep=sweep,
    )

    workflow_raw = _mapping(raw.get("workflow"), "workflow")
    workers_raw = workflow_raw.get("workers")
    if not isinstance(workers_raw, list) or not workers_raw:
        raise ConfigurationError("workflow.workers must be a non-empty list")
    workers: list[WorkerConfig] = []
    names: set[str] = set()
    for index, item in enumerate(workers_raw):
        worker = _mapping(item, f"workflow.workers[{index}]")
        worker_name = worker.get("name")
        capabilities = worker.get("capabilities")
        if not isinstance(worker_name, str) or not worker_name.strip():
            raise ConfigurationError(f"workflow.workers[{index}].name is required")
        if worker_name in names:
            raise ConfigurationError(f"duplicate worker name: {worker_name}")
        if not isinstance(capabilities, list) or not all(
            isinstance(value, str) and value for value in capabilities
        ):
            raise ConfigurationError(
                f"workflow.workers[{index}].capabilities must be a string list"
            )
        names.add(worker_name)
        workers.append(WorkerConfig(worker_name, tuple(capabilities)))
    priority = workflow_raw.get("priority", "risk-first")
    if priority not in {"risk-first", "fifo"}:
        raise ConfigurationError("workflow.priority must be risk-first or fifo")
    workflow = WorkflowConfig(
        workers=tuple(workers),
        retries=_non_negative_int(workflow_raw.get("retries", 0), "workflow.retries"),
        priority=priority,
    )

    output_dir = _resolve(base_dir, raw.get("output_dir", "../outputs/demo"), "output_dir")
    database_path = _resolve(
        base_dir,
        raw.get("database_path", str(output_dir / "simops.db")),
        "database_path",
    )

    pcb_config: PcbConfig | None = None
    if raw.get("pcb") is not None:
        pcb_raw = _mapping(raw["pcb"], "pcb")
        rules_raw = _mapping(pcb_raw.get("rules"), "pcb.rules")
        pcb_config = PcbConfig(
            path=_resolve(base_dir, pcb_raw.get("path"), "pcb.path"),
            rules=PcbRules(
                min_track_width_mm=_positive_number(
                    rules_raw.get("min_track_width_mm"), "pcb.rules.min_track_width_mm"
                ),
                min_via_drill_mm=_positive_number(
                    rules_raw.get("min_via_drill_mm"), "pcb.rules.min_via_drill_mm"
                ),
                min_annular_ring_mm=_positive_number(
                    rules_raw.get("min_annular_ring_mm"), "pcb.rules.min_annular_ring_mm"
                ),
            ),
        )

    ai_raw = _mapping(raw.get("ai", {}), "ai")
    enabled = ai_raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigurationError("ai.enabled must be true or false")
    ai_config = AiConfig(
        enabled=enabled,
        model_path=_resolve(
            base_dir, ai_raw.get("model_path", "../models/local/risk_model.joblib"), "ai.model_path"
        ),
        min_samples=max(8, _non_negative_int(ai_raw.get("min_samples", 12), "ai.min_samples")),
    )

    return ProjectConfig(
        name=name.strip(),
        description=description.strip(),
        source_path=source_path,
        config_hash=hash_value(raw),
        raw=raw,
        simulation=simulation,
        workflow=workflow,
        output_dir=output_dir,
        database_path=database_path,
        pcb=pcb_config,
        ai=ai_config,
    )

