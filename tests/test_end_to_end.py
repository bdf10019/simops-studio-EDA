from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from simops_studio.workflow import run_project


ROOT = Path(__file__).resolve().parents[1]


class EndToEndTests(unittest.TestCase):
    def test_project_to_database_ai_and_report(self) -> None:
        raw = yaml.safe_load((ROOT / "examples" / "project.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            raw["output_dir"] = str(workspace / "outputs")
            raw["database_path"] = str(workspace / "outputs" / "simops.db")
            raw["ai"]["model_path"] = str(workspace / "models" / "risk.joblib")
            raw["pcb"]["path"] = str(ROOT / "examples" / "pcb" / "pdn_demo.kicad_pcb")
            project_path = workspace / "project.yaml"
            project_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

            first = run_project(project_path, force=True, train_ai=True)
            self.assertEqual(24, first["statuses"]["COMPLETED"])
            self.assertEqual({"PASS": 12, "FAIL": 12}, first["decisions"])
            self.assertTrue(first["ai"]["trained_this_run"])
            self.assertEqual(1.0, first["ai"]["metrics"]["holdout_balanced_accuracy"])
            for filename in (
                "cases.csv",
                "results.json",
                "report.html",
                "manifest.json",
                "run_summary.json",
                "pcb_analysis.json",
                "model_metrics.json",
            ):
                self.assertTrue((workspace / "outputs" / filename).exists(), filename)
            report = (workspace / "outputs" / "report.html").read_text(encoding="utf-8")
            self.assertNotIn(str(workspace), report)
            pcb_analysis = yaml.safe_load(
                (workspace / "outputs" / "pcb_analysis.json").read_text(encoding="utf-8")
            )
            self.assertEqual("pdn_demo.kicad_pcb", pcb_analysis["source"])

            resumed = run_project(project_path, force=False, train_ai=False)
            self.assertEqual(24, resumed["dispatch"]["skipped"])
            self.assertEqual(0, resumed["dispatch"]["submitted"])


if __name__ == "__main__":
    unittest.main()
