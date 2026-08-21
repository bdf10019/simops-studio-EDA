"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from simops_studio import __version__
from simops_studio.config import load_project_config
from simops_studio.cases import expand_cases
from simops_studio.eda import create_adapter
from simops_studio.models import ConfigurationError
from simops_studio.pcb import analyze_kicad_pcb
from simops_studio.database import SimulationDatabase
from simops_studio.eda import AdapterUnavailable
from simops_studio.workflow import run_project
from simops_studio.ai import RiskModelError, score_cases, train_risk_model
from simops_studio.dashboard import serve_dashboard
from simops_studio.reporting import generate_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simops", description="EDA simulation automation and dispatch workbench"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a YAML/JSON project")
    validate.add_argument("project", type=Path)

    commands.add_parser("doctor", help="show optional EDA tool availability")

    simulate = commands.add_parser("simulate", help="run one deterministic simulation case")
    simulate.add_argument("project", type=Path)
    simulate.add_argument("--case-index", type=int, default=0)

    pcb_check = commands.add_parser("pcb-check", help="analyze the configured KiCad PCB")
    pcb_check.add_argument("project", type=Path)

    run = commands.add_parser("run", help="run or resume the complete simulation batch")
    run.add_argument("project", type=Path)
    run.add_argument("--force", action="store_true", help="rerun completed cases")
    run.add_argument("--train-ai", action="store_true", help="train risk model after simulation")

    status = commands.add_parser("status", help="show persisted run status")
    status.add_argument("project", type=Path)

    train = commands.add_parser("train-ai", help="train risk model from completed cases")
    train.add_argument("project", type=Path)

    predict = commands.add_parser("predict", help="preview risk scores for configured cases")
    predict.add_argument("project", type=Path)

    report = commands.add_parser("report", help="regenerate CSV, JSON, charts, and HTML")
    report.add_argument("project", type=Path)

    dashboard = commands.add_parser("dashboard", help="serve the local read-only dashboard")
    dashboard.add_argument("project", type=Path)
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8080)

    demo = commands.add_parser("demo", help="run the bundled end-to-end demonstration")
    demo.add_argument("--force", action="store_true")
    return parser


def _validate(path: Path) -> int:
    config = load_project_config(path)
    case_count = 1
    for values in config.simulation.sweep.values():
        case_count *= len(values)
    payload = {
        "valid": True,
        "project": config.name,
        "config_hash": config.config_hash,
        "adapter": config.simulation.adapter,
        "case_count": case_count,
        "workers": [worker.name for worker in config.workflow.workers],
        "output_dir": config.output_dir.name,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _doctor() -> int:
    payload = {
        "python": sys.version.split()[0],
        "ngspice": shutil.which("ngspice"),
        "kicad_cli": shutil.which("kicad-cli"),
        "notes": "Optional tools are not required for the built-in demo.",
    }
    print(json.dumps(payload, indent=2))
    return 0


def _simulate(path: Path, case_index: int) -> int:
    config = load_project_config(path)
    cases = expand_cases(config)
    if case_index < 0 or case_index >= len(cases):
        raise ConfigurationError(f"case index must be between 0 and {len(cases) - 1}")
    adapter = create_adapter(config.simulation.adapter, config.simulation.adapter_options)
    result = adapter.simulate(
        cases[case_index],
        config.simulation.frequency,
        config.simulation.target_impedance_ohm,
    )
    print(
        json.dumps(
            {
                "case_id": result.case_id,
                "adapter": result.adapter,
                "status": "PASS" if result.passed else "FAIL",
                "max_impedance_ohm": result.max_impedance_ohm,
                "worst_frequency_hz": result.worst_frequency_hz,
                "violation_fraction": result.violation_fraction,
                "duration_ms": result.duration_ms,
            },
            indent=2,
        )
    )
    return 0 if result.passed else 1


def _pcb_check(path: Path) -> int:
    config = load_project_config(path)
    if config.pcb is None:
        raise ConfigurationError("project does not define a pcb section")
    analysis = analyze_kicad_pcb(config.pcb.path, config.pcb.rules)
    public_analysis = {**analysis, "source": config.pcb.path.name}
    print(json.dumps(public_analysis, indent=2, ensure_ascii=False))
    return 0 if analysis["status"] == "PASS" else 1


def _status(path: Path) -> int:
    config = load_project_config(path)
    database = SimulationDatabase(config.database_path)
    database.initialize()
    print(json.dumps(database.summary(config.config_hash[:12]), indent=2))
    return 0


def _train_ai(path: Path) -> int:
    config = load_project_config(path)
    database = SimulationDatabase(config.database_path)
    database.initialize()
    metadata = train_risk_model(
        database.training_rows(config.config_hash[:12]),
        config.ai.model_path,
        min_samples=config.ai.min_samples,
    )
    print(json.dumps(metadata, indent=2))
    return 0


def _predict(path: Path) -> int:
    config = load_project_config(path)
    scoring = score_cases(expand_cases(config), config.ai.model_path)
    print(
        json.dumps(
            {
                "source": scoring.source,
                "out_of_domain_count": scoring.out_of_domain_count,
                "cases": [
                    {"case_id": case.case_id, "risk_score": round(case.risk_score, 6)}
                    for case in scoring.cases
                ],
            },
            indent=2,
        )
    )
    return 0


def _report(path: Path) -> int:
    config = load_project_config(path)
    database = SimulationDatabase(config.database_path)
    database.initialize()
    artifacts = generate_report(
        database=database,
        run_id=config.config_hash[:12],
        output_dir=config.output_dir,
        project_name=config.name,
        target_impedance_ohm=config.simulation.target_impedance_ohm,
    )
    print(json.dumps(artifacts, indent=2))
    return 0


def _dashboard(path: Path, host: str, port: int) -> int:
    config = load_project_config(path)
    database = SimulationDatabase(config.database_path)
    database.initialize()
    serve_dashboard(
        database=database,
        run_id=config.config_hash[:12],
        project_name=config.name,
        output_dir=config.output_dir,
        host=host,
        port=port,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args.project)
        if args.command == "doctor":
            return _doctor()
        if args.command == "simulate":
            return _simulate(args.project, args.case_index)
        if args.command == "pcb-check":
            return _pcb_check(args.project)
        if args.command == "run":
            summary = run_project(args.project, force=args.force, train_ai=args.train_ai)
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0 if summary["statuses"].get("FAILED", 0) == 0 else 1
        if args.command == "status":
            return _status(args.project)
        if args.command == "train-ai":
            return _train_ai(args.project)
        if args.command == "predict":
            return _predict(args.project)
        if args.command == "report":
            return _report(args.project)
        if args.command == "dashboard":
            return _dashboard(args.project, args.host, args.port)
        if args.command == "demo":
            root = Path(__file__).resolve().parents[2]
            summary = run_project(
                root / "examples" / "project.yaml",
                force=args.force,
                train_ai=True,
            )
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0
        return 2
    except (ConfigurationError, AdapterUnavailable, RiskModelError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
