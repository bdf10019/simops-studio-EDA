from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simops_studio.cases import expand_cases
from simops_studio.config import load_project_config
from simops_studio.database import SimulationDatabase
from simops_studio.eda.builtin import BuiltInPdnAdapter
from simops_studio.models import FrequencyConfig, SimulationCase, SimulationResult
from simops_studio.scheduler import SimulationScheduler


ROOT = Path(__file__).resolve().parents[1]


class FailOnceAdapter(BuiltInPdnAdapter):
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def simulate(
        self,
        case: SimulationCase,
        frequency: FrequencyConfig,
        target_impedance_ohm: float,
    ) -> SimulationResult:
        count = self.calls.get(case.case_id, 0)
        self.calls[case.case_id] = count + 1
        if count == 0:
            raise RuntimeError("synthetic transient failure")
        return super().simulate(case, frequency, target_impedance_ohm)


class DatabaseSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_project_config(ROOT / "examples" / "project.yaml")
        self.cases = expand_cases(self.config)[:4]
        self.temp = tempfile.TemporaryDirectory()
        self.database = SimulationDatabase(Path(self.temp.name) / "simops.db")
        self.database.initialize()
        self.run_id = "unit-test-run"
        self.database.start_run(
            self.run_id, self.config.name, self.config.config_hash, "builtin-pdn"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _scheduler(self, adapter: BuiltInPdnAdapter, retries: int = 0) -> SimulationScheduler:
        return SimulationScheduler(
            database=self.database,
            run_id=self.run_id,
            adapter=adapter,
            frequency=self.config.simulation.frequency,
            target_impedance_ohm=self.config.simulation.target_impedance_ohm,
            workers=self.config.workflow.workers,
            retries=retries,
            priority="risk-first",
        )

    def test_parallel_dispatch_and_resume(self) -> None:
        for case in self.cases:
            self.database.upsert_case(self.run_id, case)
        first = self._scheduler(BuiltInPdnAdapter()).run(self.cases)
        self.assertEqual(4, first.completed)
        self.assertEqual(0, first.failed)
        self.assertEqual(2, len(first.assignments))
        summary = self.database.summary(self.run_id)
        self.assertEqual(4, summary["statuses"]["COMPLETED"])
        self.assertEqual(4, sum(summary["decisions"].values()))

        second = self._scheduler(BuiltInPdnAdapter()).run(self.cases)
        self.assertEqual(0, second.completed)
        self.assertEqual(4, second.skipped)

    def test_retry_recovers_transient_failure(self) -> None:
        case = self.cases[0]
        self.database.upsert_case(self.run_id, case)
        adapter = FailOnceAdapter()
        summary = self._scheduler(adapter, retries=1).run([case])
        self.assertEqual(1, summary.completed)
        self.assertEqual(0, summary.failed)
        row = self.database.result_rows(self.run_id)[0]
        self.assertEqual(2, row["attempts"])
        self.assertEqual("COMPLETED", row["status"])


if __name__ == "__main__":
    unittest.main()

