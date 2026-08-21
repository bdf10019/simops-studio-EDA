"""End-to-end orchestration before report generation."""

from __future__ import annotations

import json
import platform
from dataclasses import asdict
from pathlib import Path
from typing import Any

from simops_studio import __version__
from simops_studio.ai import RiskModelError, score_cases, train_risk_model
from simops_studio.cases import expand_cases
from simops_studio.config import load_project_config
from simops_studio.database import SimulationDatabase, utc_now
from simops_studio.eda import AdapterUnavailable, create_adapter
from simops_studio.hashing import hash_file
from simops_studio.pcb import analyze_kicad_pcb
from simops_studio.scheduler import SimulationScheduler


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def run_project(
    project_path: str | Path, *, force: bool = False, train_ai: bool = False
) -> dict[str, Any]:
    config = load_project_config(project_path)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    database = SimulationDatabase(config.database_path)
    database.initialize()
    run_id = config.config_hash[:12]
    adapter = create_adapter(config.simulation.adapter, config.simulation.adapter_options)
    if not adapter.available():
        raise AdapterUnavailable(f"adapter is not available: {adapter.name}")

    database.start_run(run_id, config.name, config.config_hash, adapter.name)
    pcb_analysis: dict[str, Any] | None = None
    if config.pcb is not None:
        pcb_analysis = analyze_kicad_pcb(config.pcb.path, config.pcb.rules)
        _write_json(config.output_dir / "pcb_analysis.json", pcb_analysis)
        database.add_event(
            run_id,
            None,
            "INFO" if pcb_analysis["status"] == "PASS" else "WARNING",
            f"focused PCB checks: {pcb_analysis['status']}",
        )

    cases = expand_cases(config)
    scoring_source = "disabled"
    out_of_domain_count = 0
    if config.ai.enabled:
        scoring = score_cases(cases, config.ai.model_path)
        cases = scoring.cases
        scoring_source = scoring.source
        out_of_domain_count = scoring.out_of_domain_count
        database.add_event(
            run_id,
            None,
            "INFO",
            f"risk scoring source={scoring_source}, out_of_domain={out_of_domain_count}",
        )
    for case in cases:
        database.upsert_case(run_id, case, force=force)

    scheduler = SimulationScheduler(
        database=database,
        run_id=run_id,
        adapter=adapter,
        frequency=config.simulation.frequency,
        target_impedance_ohm=config.simulation.target_impedance_ohm,
        workers=config.workflow.workers,
        retries=config.workflow.retries,
        priority=config.workflow.priority,
    )
    dispatch = scheduler.run(cases)
    model_metrics: dict[str, Any] | None = None
    if train_ai and config.ai.enabled:
        try:
            model_metrics = train_risk_model(
                database.training_rows(run_id),
                config.ai.model_path,
                min_samples=config.ai.min_samples,
            )
            _write_json(config.output_dir / "model_metrics.json", model_metrics)
            rescoring = score_cases(cases, config.ai.model_path)
            cases = rescoring.cases
            scoring_source = "trained-model"
            out_of_domain_count = rescoring.out_of_domain_count
            for case in cases:
                database.upsert_case(run_id, case)
            database.add_event(
                run_id,
                None,
                "INFO",
                f"risk model trained with {model_metrics['training_samples']} samples",
            )
        except RiskModelError as exc:
            database.add_event(run_id, None, "WARNING", f"risk model not trained: {exc}")
    run_status = "COMPLETED"
    if dispatch.failed:
        run_status = "COMPLETED_WITH_ERRORS"
    elif dispatch.pending:
        run_status = "INTERRUPTED"
    database.finish_run(run_id, run_status)

    summary = database.summary(run_id)
    summary["dispatch"] = asdict(dispatch)
    summary["pcb_status"] = None if pcb_analysis is None else pcb_analysis["status"]
    summary["ai"] = {
        "enabled": config.ai.enabled,
        "scoring_source": scoring_source,
        "out_of_domain_count": out_of_domain_count,
        "trained_this_run": model_metrics is not None,
        "metrics": model_metrics,
    }
    _write_json(config.output_dir / "run_summary.json", summary)
    _write_json(config.output_dir / "events.json", database.event_rows(run_id))
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "application": "SimOps Studio",
        "application_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "project": config.name,
        "project_file": config.source_path.name,
        "project_file_sha256": hash_file(config.source_path),
        "config_hash": config.config_hash,
        "run_id": run_id,
        "adapter": adapter.name,
        "pcb_file": None if config.pcb is None else config.pcb.path.name,
        "pcb_sha256": None if pcb_analysis is None else pcb_analysis["sha256"],
        "risk_model": None
        if model_metrics is None
        else {
            "type": model_metrics["model_type"],
            "sha256": model_metrics["model_sha256"],
            "training_samples": model_metrics["training_samples"],
        },
        "limitations": [
            "The built-in solver is a lumped-element workflow reference model.",
            "Final engineering decisions require validated production tools and measurements.",
        ],
    }
    _write_json(config.output_dir / "manifest.json", manifest)
    return summary
