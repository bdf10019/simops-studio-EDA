from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from simops_studio.cli import main


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples" / "project.yaml"


class CliPrivacyTests(unittest.TestCase):
    def test_validate_does_not_print_absolute_output_path(self) -> None:
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = main(["validate", str(PROJECT)])
        payload = json.loads(stream.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("demo", payload["output_dir"])
        self.assertNotIn(str(ROOT), stream.getvalue())

    def test_pcb_check_uses_basename_in_public_output(self) -> None:
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = main(["pcb-check", str(PROJECT)])
        payload = json.loads(stream.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("pdn_demo.kicad_pcb", payload["source"])
        self.assertNotIn(str(ROOT), stream.getvalue())


if __name__ == "__main__":
    unittest.main()
