"""Local read-only dashboard implemented with the Python standard library."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from simops_studio.database import SimulationDatabase


def render_dashboard(
    *, database: SimulationDatabase, run_id: str, project_name: str
) -> str:
    summary = database.summary(run_id)
    rows = database.result_rows(run_id)
    table = "".join(
        f"<tr><td><code>{html.escape(str(row['case_id']))}</code></td>"
        f"<td>{html.escape(str(row['status']))}</td>"
        f"<td>{html.escape(str(row['pass_fail'] or '—'))}</td>"
        f"<td>{float(row['risk_score']):.3f}</td>"
        f"<td>{html.escape(str(row['assigned_worker'] or '—'))}</td></tr>"
        for row in rows
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SimOps Dashboard</title>
<style>body{{font:15px Segoe UI,sans-serif;background:#07111f;color:#e2e8f0;margin:0}}main{{max-width:1050px;margin:auto;padding:36px 22px}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:15px;min-width:150px}}.value{{font-size:28px;font-weight:700}}table{{margin-top:24px;width:100%;border-collapse:collapse;background:#111827}}th,td{{padding:10px;border-bottom:1px solid #334155;text-align:left}}a{{color:#38bdf8}}code{{color:#bae6fd}}</style></head>
<body><main><p>SIMOPS STUDIO · AUTO REFRESH 5S</p><h1>{html.escape(project_name)}</h1>
<div class="cards"><div class="card"><div>Run status</div><div class="value">{html.escape(str(summary['run_status']))}</div></div>
<div class="card"><div>Total</div><div class="value">{summary['total']}</div></div>
<div class="card"><div>PASS</div><div class="value">{summary['decisions'].get('PASS',0)}</div></div>
<div class="card"><div>FAIL</div><div class="value">{summary['decisions'].get('FAIL',0)}</div></div></div>
<p><a href="/report">Open engineering report</a> · <a href="/api/summary">Summary API</a> · <a href="/api/cases">Cases API</a></p>
<table><thead><tr><th>Case</th><th>Status</th><th>Decision</th><th>Risk</th><th>Worker</th></tr></thead><tbody>{table}</tbody></table>
</main></body></html>"""


def _safe_case_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {
        "case_id",
        "sequence",
        "status",
        "risk_score",
        "assigned_worker",
        "attempts",
        "duration_ms",
        "pass_fail",
        "max_impedance_ohm",
        "worst_frequency_hz",
        "violation_fraction",
    }
    return [{key: row[key] for key in allowed} for row in rows]


def serve_dashboard(
    *,
    database: SimulationDatabase,
    run_id: str,
    project_name: str,
    output_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("dashboard binds to the local machine only")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                self._send(
                    "text/html; charset=utf-8",
                    render_dashboard(
                        database=database, run_id=run_id, project_name=project_name
                    ).encode("utf-8"),
                )
            elif self.path == "/api/summary":
                self._send_json(database.summary(run_id))
            elif self.path == "/api/cases":
                self._send_json(_safe_case_rows(database.result_rows(run_id)))
            elif self.path == "/report":
                report = output_dir / "report.html"
                if not report.exists():
                    self.send_error(404, "report not generated")
                else:
                    self._send("text/html; charset=utf-8", report.read_bytes())
            else:
                self.send_error(404)

        def _send_json(self, value: Any) -> None:
            self._send(
                "application/json; charset=utf-8",
                json.dumps(value, indent=2).encode("utf-8"),
            )

        def _send(self, content_type: str, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard: http://{host}:{port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

