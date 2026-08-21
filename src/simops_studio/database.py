"""SQLite persistence for resumable simulation work."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from simops_studio.models import SimulationCase, SimulationResult


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class SimulationDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _session(self) -> Any:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._session() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    adapter TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    sequence INTEGER NOT NULL,
                    input_hash TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    assigned_worker TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_ms REAL,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS results (
                    case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
                    pass_fail TEXT NOT NULL,
                    max_impedance_ohm REAL NOT NULL,
                    min_impedance_ohm REAL NOT NULL,
                    worst_frequency_hz REAL NOT NULL,
                    resonant_frequency_hz REAL NOT NULL,
                    violation_fraction REAL NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    case_id TEXT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cases_run_status ON cases(run_id, status);
                CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
                """
            )

    def start_run(self, run_id: str, project_name: str, config_hash: str, adapter: str) -> None:
        with self._session() as connection:
            connection.execute(
                """
                INSERT INTO runs(run_id, project_name, config_hash, adapter, status, started_at)
                VALUES (?, ?, ?, ?, 'RUNNING', ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status='RUNNING', ended_at=NULL
                """,
                (run_id, project_name, config_hash, adapter, utc_now()),
            )
        self.add_event(run_id, None, "INFO", "run started or resumed")

    def finish_run(self, run_id: str, status: str) -> None:
        with self._session() as connection:
            connection.execute(
                "UPDATE runs SET status=?, ended_at=? WHERE run_id=?",
                (status, utc_now(), run_id),
            )
        self.add_event(run_id, None, "INFO", f"run finished with status {status}")

    def upsert_case(self, run_id: str, case: SimulationCase, *, force: bool = False) -> str:
        parameters_json = json.dumps(case.parameters, sort_keys=True, separators=(",", ":"))
        with self._session() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO cases(
                    case_id, run_id, sequence, input_hash, parameters_json,
                    status, priority, risk_score
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    case.case_id,
                    run_id,
                    case.sequence,
                    case.input_hash,
                    parameters_json,
                    case.risk_score,
                    case.risk_score,
                ),
            )
            if force:
                connection.execute("DELETE FROM results WHERE case_id=?", (case.case_id,))
                connection.execute(
                    """
                    UPDATE cases SET status='PENDING', priority=?, risk_score=?,
                        assigned_worker=NULL, attempts=0, started_at=NULL, ended_at=NULL,
                        duration_ms=NULL, error=NULL
                    WHERE case_id=?
                    """,
                    (case.risk_score, case.risk_score, case.case_id),
                )
            else:
                connection.execute(
                    "UPDATE cases SET priority=?, risk_score=? WHERE case_id=?",
                    (case.risk_score, case.risk_score, case.case_id),
                )
            row = connection.execute(
                "SELECT status FROM cases WHERE case_id=?", (case.case_id,)
            ).fetchone()
        return str(row["status"])

    def mark_running(self, run_id: str, case_id: str, worker: str) -> int:
        with self._session() as connection:
            connection.execute(
                """
                UPDATE cases SET status='RUNNING', assigned_worker=?, attempts=attempts+1,
                    started_at=?, ended_at=NULL, error=NULL
                WHERE case_id=?
                """,
                (worker, utc_now(), case_id),
            )
            row = connection.execute(
                "SELECT attempts FROM cases WHERE case_id=?", (case_id,)
            ).fetchone()
        attempts = int(row["attempts"])
        self.add_event(run_id, case_id, "INFO", f"attempt {attempts} assigned to {worker}")
        return attempts

    def save_completed(self, run_id: str, result: SimulationResult) -> None:
        payload = json.dumps(asdict(result), separators=(",", ":"))
        with self._session() as connection:
            connection.execute(
                """
                INSERT INTO results(
                    case_id, pass_fail, max_impedance_ohm, min_impedance_ohm,
                    worst_frequency_hz, resonant_frequency_hz, violation_fraction,
                    result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    pass_fail=excluded.pass_fail,
                    max_impedance_ohm=excluded.max_impedance_ohm,
                    min_impedance_ohm=excluded.min_impedance_ohm,
                    worst_frequency_hz=excluded.worst_frequency_hz,
                    resonant_frequency_hz=excluded.resonant_frequency_hz,
                    violation_fraction=excluded.violation_fraction,
                    result_json=excluded.result_json
                """,
                (
                    result.case_id,
                    "PASS" if result.passed else "FAIL",
                    result.max_impedance_ohm,
                    result.min_impedance_ohm,
                    result.worst_frequency_hz,
                    result.resonant_frequency_hz,
                    result.violation_fraction,
                    payload,
                ),
            )
            connection.execute(
                """
                UPDATE cases SET status='COMPLETED', ended_at=?, duration_ms=?, error=NULL
                WHERE case_id=?
                """,
                (utc_now(), result.duration_ms, result.case_id),
            )
        self.add_event(run_id, result.case_id, "INFO", "simulation completed")

    def save_failed(self, run_id: str, case_id: str, error: str, *, terminal: bool) -> None:
        status = "FAILED" if terminal else "PENDING"
        with self._session() as connection:
            connection.execute(
                "UPDATE cases SET status=?, ended_at=?, error=? WHERE case_id=?",
                (status, utc_now(), error[:2000], case_id),
            )
        level = "ERROR" if terminal else "WARNING"
        self.add_event(run_id, case_id, level, error[:1000])

    def add_event(
        self, run_id: str, case_id: str | None, level: str, message: str
    ) -> None:
        with self._session() as connection:
            connection.execute(
                "INSERT INTO events(run_id, case_id, timestamp, level, message) VALUES (?, ?, ?, ?, ?)",
                (run_id, case_id, utc_now(), level, message),
            )

    def case_status(self, case_id: str) -> str | None:
        with self._session() as connection:
            row = connection.execute(
                "SELECT status FROM cases WHERE case_id=?", (case_id,)
            ).fetchone()
        return None if row is None else str(row["status"])

    def summary(self, run_id: str) -> dict[str, Any]:
        with self._session() as connection:
            status_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM cases WHERE run_id=? GROUP BY status",
                (run_id,),
            ).fetchall()
            result_rows = connection.execute(
                "SELECT pass_fail, COUNT(*) AS count FROM results r JOIN cases c USING(case_id) "
                "WHERE c.run_id=? GROUP BY pass_fail",
                (run_id,),
            ).fetchall()
            run = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        statuses = {str(row["status"]): int(row["count"]) for row in status_rows}
        decisions = {str(row["pass_fail"]): int(row["count"]) for row in result_rows}
        return {
            "run_id": run_id,
            "run_status": None if run is None else str(run["status"]),
            "total": sum(statuses.values()),
            "statuses": statuses,
            "decisions": decisions,
        }

    def result_rows(self, run_id: str) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                """
                SELECT c.*, r.pass_fail, r.max_impedance_ohm, r.min_impedance_ohm,
                    r.worst_frequency_hz, r.resonant_frequency_hz,
                    r.violation_fraction, r.result_json
                FROM cases c LEFT JOIN results r USING(case_id)
                WHERE c.run_id=? ORDER BY c.sequence
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def event_rows(self, run_id: str) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT id, case_id, timestamp, level, message FROM events "
                "WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def training_rows(self, run_id: str | None = None) -> list[dict[str, Any]]:
        query = (
            "SELECT c.parameters_json, r.pass_fail FROM cases c "
            "JOIN results r USING(case_id) WHERE c.status='COMPLETED'"
        )
        arguments: Iterable[Any] = ()
        if run_id is not None:
            query += " AND c.run_id=?"
            arguments = (run_id,)
        with self._session() as connection:
            rows = connection.execute(query, tuple(arguments)).fetchall()
        return [
            {"parameters": json.loads(row["parameters_json"]), "pass_fail": row["pass_fail"]}
            for row in rows
        ]
