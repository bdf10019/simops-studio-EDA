from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simops_studio.config import load_project_config
from simops_studio.models import ConfigurationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_example_is_valid_and_resolves_paths(self) -> None:
        config = load_project_config(PROJECT_ROOT / "examples" / "project.yaml")
        self.assertEqual("pdn-decoupling-study", config.name)
        self.assertEqual(24, self._case_count(config))
        self.assertEqual(2, len(config.workflow.workers))
        self.assertTrue(config.output_dir.is_absolute())
        self.assertEqual(64, len(config.config_hash))

    def test_invalid_frequency_is_rejected(self) -> None:
        text = """
project: {name: invalid}
simulation:
  adapter: builtin-pdn
  frequency: {start_hz: 1000, stop_hz: 100, points: 10}
  target_impedance_ohm: 0.1
  base:
    plane_resistance_ohm: 0.01
    plane_inductance_h: 1.0e-9
    capacitance_f: 1.0e-6
    capacitor_esr_ohm: 0.01
    capacitor_esl_h: 1.0e-9
workflow:
  workers: [{name: local, capabilities: [builtin-pdn]}]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "stop_hz"):
                load_project_config(path)

    @staticmethod
    def _case_count(config: object) -> int:
        count = 1
        for values in config.simulation.sweep.values():  # type: ignore[attr-defined]
            count *= len(values)
        return count


if __name__ == "__main__":
    unittest.main()

