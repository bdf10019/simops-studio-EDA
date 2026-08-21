"""Capability-aware parallel dispatch with retries and resumable state."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from simops_studio.database import SimulationDatabase
from simops_studio.eda.base import SimulationAdapter
from simops_studio.models import (
    FrequencyConfig,
    SimulationCase,
    WorkerConfig,
)


@dataclass(frozen=True)
class DispatchSummary:
    submitted: int
    completed: int
    failed: int
    skipped: int
    pending: int
    assignments: dict[str, tuple[str, ...]]


class SimulationScheduler:
    def __init__(
        self,
        *,
        database: SimulationDatabase,
        run_id: str,
        adapter: SimulationAdapter,
        frequency: FrequencyConfig,
        target_impedance_ohm: float,
        workers: tuple[WorkerConfig, ...],
        retries: int,
        priority: str,
    ) -> None:
        self.database = database
        self.run_id = run_id
        self.adapter = adapter
        self.frequency = frequency
        self.target_impedance_ohm = target_impedance_ohm
        self.workers = tuple(
            worker
            for worker in workers
            if adapter.name in worker.capabilities or "*" in worker.capabilities
        )
        if not self.workers:
            raise ValueError(f"no worker has capability {adapter.name}")
        self.retries = retries
        self.priority = priority

    def run(
        self, cases: list[SimulationCase], cancel_event: threading.Event | None = None
    ) -> DispatchSummary:
        cancel = cancel_event or threading.Event()
        skipped = sum(self.database.case_status(case.case_id) == "COMPLETED" for case in cases)
        pending_cases = [
            case for case in cases if self.database.case_status(case.case_id) != "COMPLETED"
        ]
        queues = self._partition(pending_cases)
        completed = 0
        failed = 0
        assignments = {
            worker.name: tuple(case.case_id for case in queues[worker.name])
            for worker in self.workers
        }
        with ThreadPoolExecutor(max_workers=len(self.workers), thread_name_prefix="simops") as pool:
            futures = {
                pool.submit(self._run_worker, worker, queues[worker.name], cancel): worker.name
                for worker in self.workers
            }
            try:
                for future in as_completed(futures):
                    worker_completed, worker_failed = future.result()
                    completed += worker_completed
                    failed += worker_failed
            except KeyboardInterrupt:
                cancel.set()
                self.database.add_event(
                    self.run_id,
                    None,
                    "WARNING",
                    "cancellation requested; current simulations will finish before stopping",
                )
                for future in futures:
                    worker_completed, worker_failed = future.result()
                    completed += worker_completed
                    failed += worker_failed
        still_pending = sum(
            self.database.case_status(case.case_id) != "COMPLETED"
            and self.database.case_status(case.case_id) != "FAILED"
            for case in cases
        )
        return DispatchSummary(
            submitted=len(pending_cases),
            completed=completed,
            failed=failed,
            skipped=skipped,
            pending=still_pending,
            assignments=assignments,
        )

    def _partition(self, cases: list[SimulationCase]) -> dict[str, list[SimulationCase]]:
        if self.priority == "risk-first":
            ordered = sorted(cases, key=lambda item: (-item.risk_score, item.sequence))
        else:
            ordered = sorted(cases, key=lambda item: item.sequence)
        queues = {worker.name: [] for worker in self.workers}
        loads = {worker.name: 0.0 for worker in self.workers}
        for case in ordered:
            worker_name = min(loads, key=lambda name: (loads[name], name))
            queues[worker_name].append(case)
            loads[worker_name] += 1.0
        return queues

    def _run_worker(
        self,
        worker: WorkerConfig,
        cases: list[SimulationCase],
        cancel: threading.Event,
    ) -> tuple[int, int]:
        completed = 0
        failed = 0
        for case in cases:
            if cancel.is_set():
                break
            error: Exception | None = None
            for attempt in range(self.retries + 1):
                self.database.mark_running(self.run_id, case.case_id, worker.name)
                try:
                    result = self.adapter.simulate(
                        case, self.frequency, self.target_impedance_ohm
                    )
                    self.database.save_completed(self.run_id, result)
                    completed += 1
                    error = None
                    break
                except Exception as exc:  # adapter errors must not stop the batch
                    error = exc
                    terminal = attempt >= self.retries
                    self.database.save_failed(
                        self.run_id,
                        case.case_id,
                        f"{type(exc).__name__}: {exc}",
                        terminal=terminal,
                    )
            if error is not None:
                failed += 1
        return completed, failed

