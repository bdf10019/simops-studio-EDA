# Reproducible demo

## Run

From the repository root in PowerShell:

```powershell
python -m pip install -r requirements-lock.txt
python -m pip install -e . --no-deps
.\scripts\verify.ps1
.\scripts\run-demo.ps1
```

The demo validates the project, parses the synthetic PCB, expands 24 parameter combinations,
dispatches them to two logical workers, trains the local risk model, and produces the report.
It is deterministic except for execution durations and generation timestamps.

## Expected baseline

| Check | Expected value |
|---|---:|
| Project cases | 24 |
| Completed | 24 |
| PASS | 12 |
| FAIL | 12 |
| PCB focused check | PASS |
| AI training rows | 24 |
| Fixed holdout rows | 6 |
| Fixed holdout balanced accuracy | 1.0 |
| Resume on unchanged second run | 24 skipped |

The AI score is intentionally reported with its context: this small synthetic sweep has a
simple decision boundary. It validates model plumbing and safety behavior, not production
generalization.

## Inspect artifacts

`outputs/demo/` contains:

- `simops.db`: run, queue, results, and events.
- `cases.csv`, `results.json`, `events.json`: machine-readable exports.
- `report.html`: self-contained engineering report with embedded plots.
- `charts/*.png`: standalone impedance and batch-outcome plots.
- `pcb_analysis.json`: sanitized PCB metrics and focused rule outcome.
- `model_metrics.json`: evaluation, bounds, feature importance, guardrails, and model hash.
- `manifest.json`: configuration/PCB/model/artifact provenance hashes.
- `run_summary.json`: final operational summary and artifact checksums.

Start the read-only dashboard:

```powershell
python -m simops_studio dashboard examples/project.yaml --port 8080
```

Routes are `/`, `/report`, `/api/summary`, and `/api/cases`. Stop with `Ctrl+C`.

## Resume and forced rerun

```powershell
# Uses persisted results and skips completed cases.
python -m simops_studio run examples/project.yaml

# Clears results for the same run ID and dispatches every case again.
python -m simops_studio run examples/project.yaml --force --train-ai
```

Generated outputs and model binaries are ignored by Git. They can be deleted locally when no
longer needed and recreated from the tracked synthetic inputs.
