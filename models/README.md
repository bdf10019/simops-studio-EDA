# Local models

`models/local/` stores locally trained risk-model files and is ignored by Git. The bundled
demo creates `risk_model.joblib`; its public metadata and SHA-256 are written to
`outputs/demo/model_metrics.json`.

Model files are executable serialization artifacts. Load only models produced by a trusted
local run. See `docs/MODEL_CARD.md` for intended use and guardrails.
