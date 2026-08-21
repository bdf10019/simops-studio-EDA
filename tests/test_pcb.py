from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simops_studio.config import load_project_config
from simops_studio.models import PcbRules
from simops_studio.pcb import analyze_kicad_pcb


ROOT = Path(__file__).resolve().parents[1]


class PcbTests(unittest.TestCase):
    def test_bundled_board_passes_focused_rules(self) -> None:
        config = load_project_config(ROOT / "examples" / "project.yaml")
        assert config.pcb is not None
        result = analyze_kicad_pcb(config.pcb.path, config.pcb.rules)
        self.assertEqual("PASS", result["status"])
        self.assertEqual(2, result["net_count"])
        self.assertEqual(3, result["segment_count"])
        self.assertEqual(1, result["via_count"])
        self.assertEqual(2, result["footprint_count"])

    def test_narrow_track_is_reported(self) -> None:
        text = """(kicad_pcb (version 20231120)
  (net 0 "")
  (net 1 "VDD")
  (segment (start 0 0) (end 1 0) (width 0.1) (layer "F.Cu") (net 1))
)"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "narrow.kicad_pcb"
            path.write_text(text, encoding="utf-8")
            result = analyze_kicad_pcb(path, PcbRules(0.2, 0.2, 0.1))
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("MIN_TRACK_WIDTH", result["violations"][0]["rule"])


if __name__ == "__main__":
    unittest.main()

