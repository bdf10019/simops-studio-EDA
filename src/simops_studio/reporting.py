"""CSV, JSON, chart, and self-contained HTML report generation."""

from __future__ import annotations

import base64
import csv
import html
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from simops_studio.database import SimulationDatabase, utc_now
from simops_studio.hashing import hash_file
from simops_studio.models import PDN_PARAMETER_NAMES


def _public_row(row: dict[str, Any], *, include_curve: bool) -> dict[str, Any]:
    parameters = json.loads(row["parameters_json"])
    value: dict[str, Any] = {
        "case_id": row["case_id"],
        "sequence": row["sequence"],
        "input_hash": row["input_hash"],
        "parameters": parameters,
        "status": row["status"],
        "risk_score": row["risk_score"],
        "assigned_worker": row["assigned_worker"],
        "attempts": row["attempts"],
        "duration_ms": row["duration_ms"],
        "error": row["error"],
        "decision": row["pass_fail"],
        "max_impedance_ohm": row["max_impedance_ohm"],
        "min_impedance_ohm": row["min_impedance_ohm"],
        "worst_frequency_hz": row["worst_frequency_hz"],
        "resonant_frequency_hz": row["resonant_frequency_hz"],
        "violation_fraction": row["violation_fraction"],
    }
    if include_curve and row["result_json"]:
        result = json.loads(row["result_json"])
        value["frequencies_hz"] = result["frequencies_hz"]
        value["impedance_ohm"] = result["impedance_ohm"]
    return value


def _save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "case_id",
        "sequence",
        *PDN_PARAMETER_NAMES,
        "risk_score",
        "status",
        "decision",
        "assigned_worker",
        "attempts",
        "duration_ms",
        "max_impedance_ohm",
        "min_impedance_ohm",
        "worst_frequency_hz",
        "resonant_frequency_hz",
        "violation_fraction",
        "input_hash",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {key: row.get(key) for key in fields}
            flat.update(row["parameters"])
            writer.writerow(flat)


def _chart_png(rows: list[dict[str, Any]], target_impedance_ohm: float) -> bytes:
    figure, axis = plt.subplots(figsize=(10, 5.2), dpi=130)
    completed = [row for row in rows if row.get("frequencies_hz")]
    for row in completed:
        color = "#ef4444" if row["decision"] == "FAIL" else "#10b981"
        axis.plot(
            row["frequencies_hz"],
            row["impedance_ohm"],
            color=color,
            alpha=0.35,
            linewidth=1.0,
        )
    axis.axhline(target_impedance_ohm, color="#f59e0b", linestyle="--", linewidth=2)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Frequency (Hz)")
    axis.set_ylabel("Impedance magnitude (ohm)")
    axis.set_title("PDN impedance sweep overview")
    axis.grid(True, which="both", alpha=0.2)
    figure.tight_layout()
    buffer = BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    return buffer.getvalue()


def _summary_chart_png(rows: list[dict[str, Any]]) -> bytes:
    labels = ["PASS", "FAIL", "ERROR"]
    counts = [
        sum(row["decision"] == "PASS" for row in rows),
        sum(row["decision"] == "FAIL" for row in rows),
        sum(row["status"] == "FAILED" for row in rows),
    ]
    figure, axis = plt.subplots(figsize=(6.5, 3.6), dpi=130)
    bars = axis.bar(labels, counts, color=["#10b981", "#ef4444", "#64748b"])
    axis.bar_label(bars, padding=3)
    axis.set_ylabel("Cases")
    axis.set_title("Batch outcome")
    axis.set_ylim(0, max(counts + [1]) * 1.2)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    buffer = BytesIO()
    figure.savefig(buffer, format="png")
    plt.close(figure)
    return buffer.getvalue()


def _data_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _number(value: Any, format_spec: str) -> str:
    return "—" if value is None else format(float(value), format_spec)


def _load_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def generate_report(
    *,
    database: SimulationDatabase,
    run_id: str,
    output_dir: str | Path,
    project_name: str,
    target_impedance_ohm: float,
) -> dict[str, Any]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    chart_dir = destination / "charts"
    chart_dir.mkdir(exist_ok=True)
    database_rows = database.result_rows(run_id)
    public_rows = [_public_row(row, include_curve=True) for row in database_rows]
    csv_rows = [_public_row(row, include_curve=False) for row in database_rows]

    csv_path = destination / "cases.csv"
    json_path = destination / "results.json"
    report_path = destination / "report.html"
    impedance_path = chart_dir / "impedance_overview.png"
    summary_path = chart_dir / "batch_outcome.png"
    _save_csv(csv_path, csv_rows)
    json_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": utc_now(),
                "run_id": run_id,
                "project": project_name,
                "target_impedance_ohm": target_impedance_ohm,
                "cases": public_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    impedance_png = _chart_png(public_rows, target_impedance_ohm)
    summary_png = _summary_chart_png(public_rows)
    impedance_path.write_bytes(impedance_png)
    summary_path.write_bytes(summary_png)

    pcb = _load_optional(destination / "pcb_analysis.json")
    model = _load_optional(destination / "model_metrics.json")
    pass_count = sum(row["decision"] == "PASS" for row in public_rows)
    fail_count = sum(row["decision"] == "FAIL" for row in public_rows)
    error_count = sum(row["status"] == "FAILED" for row in public_rows)
    table_rows = "".join(
        f"""
        <tr>
          <td><code>{html.escape(row['case_id'])}</code></td>
          <td>{row['risk_score']:.3f}</td>
          <td><span class="pill {str(row['decision'] or 'error').lower()}">{html.escape(str(row['decision'] or 'ERROR'))}</span></td>
          <td>{_number(row['max_impedance_ohm'], '.6f')}</td>
          <td>{_number(row['worst_frequency_hz'], '.4g')}</td>
          <td>{html.escape(str(row['assigned_worker'] or '—'))}</td>
          <td>{row['attempts']}</td>
        </tr>"""
        for row in public_rows
    )
    pcb_html = "Not configured"
    if pcb:
        pcb_html = (
            f"{html.escape(pcb['status'])}; {pcb['net_count']} nets, "
            f"{pcb['segment_count']} tracks, {pcb['via_count']} vias, "
            f"{len(pcb['violations'])} focused-rule violations"
        )
    model_html = "Neutral fallback; no trained model was used."
    if model:
        model_html = (
            f"{html.escape(model['model_type'])}, {model['training_samples']} samples, "
            f"holdout balanced accuracy {model['holdout_balanced_accuracy']:.3f}. "
            "Predictions only prioritize work; simulator results remain authoritative."
        )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SimOps Studio — {html.escape(project_name)}</title>
<style>
:root{{--ink:#e5e7eb;--muted:#94a3b8;--panel:#111827;--line:#334155;--bg:#020617;--pass:#10b981;--fail:#ef4444;--accent:#38bdf8}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(145deg,#020617,#0f172a);color:var(--ink);font:15px/1.55 Inter,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:auto;padding:42px 24px 72px}}h1{{font-size:34px;margin:0}}h2{{margin-top:38px}}.muted{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin:26px 0}}.card,.panel{{background:rgba(17,24,39,.92);border:1px solid var(--line);border-radius:14px;padding:18px}}
.value{{font-size:30px;font-weight:750}}.pass-text{{color:var(--pass)}}.fail-text{{color:var(--fail)}}.grid{{display:grid;grid-template-columns:2fr 1fr;gap:18px}}img{{width:100%;border-radius:9px;background:white}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left}}th{{color:#cbd5e1}}.table-wrap{{overflow:auto}}
.pill{{display:inline-block;padding:2px 8px;border-radius:999px;font-weight:700}}.pill.pass{{background:#064e3b;color:#a7f3d0}}.pill.fail{{background:#7f1d1d;color:#fecaca}}.pill.error{{background:#334155;color:#e2e8f0}}
code{{color:#bae6fd}}a{{color:var(--accent)}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<p class="muted">SIMULATION OPERATIONS REPORT</p><h1>{html.escape(project_name)}</h1>
<p class="muted">Run <code>{html.escape(run_id)}</code> · target impedance {target_impedance_ohm:.6g} Ω · generated {html.escape(utc_now())}</p>
<section class="cards"><div class="card"><div class="muted">Cases</div><div class="value">{len(public_rows)}</div></div>
<div class="card"><div class="muted">PASS</div><div class="value pass-text">{pass_count}</div></div>
<div class="card"><div class="muted">FAIL</div><div class="value fail-text">{fail_count}</div></div>
<div class="card"><div class="muted">Errors</div><div class="value">{error_count}</div></div></section>
<section class="grid"><div class="panel"><img alt="PDN impedance sweep overview" src="{_data_uri(impedance_png)}"></div>
<div class="panel"><img alt="Batch outcome" src="{_data_uri(summary_png)}"></div></section>
<h2>Engineering checks</h2><div class="panel"><p><strong>PCB:</strong> {pcb_html}</p><p><strong>ML risk preview:</strong> {model_html}</p></div>
<h2>Cases</h2><div class="panel table-wrap"><table><thead><tr><th>Case</th><th>Risk</th><th>Decision</th><th>Max Z (Ω)</th><th>Worst Hz</th><th>Worker</th><th>Attempts</th></tr></thead>
<tbody>{table_rows}</tbody></table></div>
<h2>Artifacts and boundary</h2><div class="panel"><p><a href="cases.csv">CSV results</a> · <a href="results.json">JSON with curves</a> · <a href="manifest.json">Run manifest</a></p>
<p class="muted">The built-in lumped-element model demonstrates automation and traceability. It does not replace production field-solver sign-off or calibrated measurement.</p></div>
</main></body></html>"""
    report_path.write_text(document, encoding="utf-8")
    return {
        "cases_csv": {"file": csv_path.name, "sha256": hash_file(csv_path)},
        "results_json": {"file": json_path.name, "sha256": hash_file(json_path)},
        "report_html": {"file": report_path.name, "sha256": hash_file(report_path)},
        "impedance_chart": {
            "file": str(impedance_path.relative_to(destination)).replace("\\", "/"),
            "sha256": hash_file(impedance_path),
        },
        "outcome_chart": {
            "file": str(summary_path.relative_to(destination)).replace("\\", "/"),
            "sha256": hash_file(summary_path),
        },
    }
