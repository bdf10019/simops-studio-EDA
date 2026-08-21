from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simops_studio.cases import expand_cases
from simops_studio.config import load_project_config
from simops_studio.eda.builtin import BuiltInPdnAdapter
from simops_studio.eda.ngspice import NgspiceAdapter


ROOT = Path(__file__).resolve().parents[1]


class SimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_project_config(ROOT / "examples" / "project.yaml")
        self.cases = expand_cases(self.config)

    def test_case_expansion_is_deterministic_and_unique(self) -> None:
        again = expand_cases(self.config)
        self.assertEqual(24, len(self.cases))
        self.assertEqual(
            [item.case_id for item in self.cases], [item.case_id for item in again]
        )
        self.assertEqual(24, len({item.case_id for item in self.cases}))

    def test_builtin_simulation_produces_physical_vectors(self) -> None:
        result = BuiltInPdnAdapter().simulate(
            self.cases[0],
            self.config.simulation.frequency,
            self.config.simulation.target_impedance_ohm,
        )
        self.assertEqual(401, len(result.frequencies_hz))
        self.assertEqual(401, len(result.impedance_ohm))
        self.assertGreater(result.max_impedance_ohm, result.min_impedance_ohm)
        self.assertGreaterEqual(result.violation_fraction, 0)
        self.assertLessEqual(result.violation_fraction, 1)

    def test_ngspice_wrdata_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.csv"
            path.write_text("1.0e3 0.02\n1.0e4 0.03\n", encoding="utf-8")
            frequencies, impedance = NgspiceAdapter.parse_wrdata(path)
        self.assertEqual((1000.0, 10000.0), frequencies)
        self.assertEqual((0.02, 0.03), impedance)


if __name__ == "__main__":
    unittest.main()

