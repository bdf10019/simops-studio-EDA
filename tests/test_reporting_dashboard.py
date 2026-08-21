from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simops_studio.cases import expand_cases
from simops_studio.config import load_project_config
from simops_studio.dashboard import render_dashboard
from simops_studio.database import SimulationDatabase
from simops_studio.eda.builtin import BuiltInPdnAdapter
from simops_studio.reporting import generate_report


ROOT = Path(__file__).resolve().parents[1]


class ReportingDashboardTests(unittest.TestCase):
    def test_report_exports_and_dashboard_render(self) -> None:
        config = load_project_config(ROOT / "examples" / "project.yaml")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            database = SimulationDatabase(output / "simops.db")
            database.initialize()
            run_id = "report-test"
            database.start_run(run_id, config.name, config.config_hash, "builtin-pdn")
            adapter = BuiltInPdnAdapter()
            for case in expand_cases(config)[:3]:
                database.upsert_case(run_id, case)
                database.mark_running(run_id, case.case_id, "test-worker")
                database.save_completed(
                    run_id,
                    adapter.simulate(
                        case,
                        config.simulation.frequency,
                        config.simulation.target_impedance_ohm,
                    ),
                )
            database.finish_run(run_id, "COMPLETED")
            artifacts = generate_report(
                database=database,
                run_id=run_id,
                output_dir=output,
                project_name=config.name,
                target_impedance_ohm=config.simulation.target_impedance_ohm,
            )
            self.assertTrue((output / "cases.csv").exists())
            self.assertTrue((output / "results.json").exists())
            report = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn("PDN impedance sweep overview", report)
            self.assertIn("data:image/png;base64", report)
            self.assertEqual(64, len(artifacts["report_html"]["sha256"]))

            dashboard = render_dashboard(
                database=database, run_id=run_id, project_name=config.name
            )
            self.assertIn("AUTO REFRESH 5S", dashboard)
            self.assertNotIn(str(output), dashboard)


if __name__ == "__main__":
    unittest.main()

