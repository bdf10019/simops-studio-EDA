"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from simops_studio import __version__
from simops_studio.config import load_project_config
from simops_studio.models import ConfigurationError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simops", description="EDA simulation automation and dispatch workbench"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a YAML/JSON project")
    validate.add_argument("project", type=Path)

    commands.add_parser("doctor", help="show optional EDA tool availability")
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
        "output_dir": str(config.output_dir),
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            return _validate(args.project)
        if args.command == "doctor":
            return _doctor()
        return 2
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

