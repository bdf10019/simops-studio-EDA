# SimOps Studio

SimOps Studio is a local engineering workbench for validating simulation requests,
dispatching parameter sweeps, recording results, prioritizing cases with a practical ML
model, and generating traceable reports.

The project is an independent, public-ready EDA automation example. It contains only
synthetic circuit and PCB data and does not depend on a commercial solver.

## Planned baseline scope

- YAML/JSON project validation
- Built-in PDN/RLC frequency simulation
- KiCad PCB metadata parsing and practical rule checks
- Pluggable built-in, ngspice, and external-command adapters
- SQLite job state, retries, resume, and audit events
- Risk-based scheduling with a safe heuristic fallback
- CSV, JSON, charts, and self-contained HTML reports
- Local read-only dashboard
- Automated unit, integration, and end-to-end tests

## Quick start

Requires Python 3.11 or later.

```powershell
python -m pip install -e .
simops validate examples/project.yaml
```

The complete runnable workflow will be documented when the baseline implementation is
finished. Generated databases, reports, model files, and optional EDA outputs stay outside
Git by default.

## Safety boundary

The built-in simulator is an educational lumped-element reference model. It demonstrates
workflow automation and is not a replacement for production SI/PI sign-off, calibrated
measurement, or a licensed field solver.

