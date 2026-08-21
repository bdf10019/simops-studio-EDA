"""Generic no-shell command adapter for enterprise EDA integration."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from simops_studio.eda.base import AdapterUnavailable, SimulationAdapter
from simops_studio.models import FrequencyConfig, SimulationCase, SimulationResult
from simops_studio.simulation.pdn import build_result


class ExternalCommandAdapter(SimulationAdapter):
    name = "external-command"

    def __init__(self, command: list[str]) -> None:
        if not command:
            raise ValueError("external command cannot be empty")
        self.command = list(command)

    def available(self) -> bool:
        return shutil.which(self.command[0]) is not None

    def simulate(
        self,
        case: SimulationCase,
        frequency: FrequencyConfig,
        target_impedance_ohm: float,
    ) -> SimulationResult:
        if not self.available():
            raise AdapterUnavailable(f"external executable is unavailable: {self.command[0]}")
        with tempfile.TemporaryDirectory(prefix="simops-external-") as directory:
            work = Path(directory)
            input_path = work / "input.json"
            output_path = work / "output.csv"
            input_path.write_text(
                json.dumps(
                    {
                        "case_id": case.case_id,
                        "parameters": case.parameters,
                        "frequency": frequency.__dict__,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            replacements = {
                "{input_json}": str(input_path),
                "{output_csv}": str(output_path),
            }
            command = [replacements.get(token, token) for token in self.command]
            started = time.perf_counter()
            process = subprocess.run(
                command,
                cwd=work,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                shell=False,
            )
            duration_ms = (time.perf_counter() - started) * 1000
            if process.returncode != 0 or not output_path.exists():
                detail = (process.stderr or process.stdout).strip()[-1000:]
                raise RuntimeError(
                    f"external simulator failed with code {process.returncode}: {detail}"
                )
            frequencies, impedance = self._read_output(output_path)
            return build_result(
                case=case,
                adapter=self.name,
                frequencies_hz=frequencies,
                impedance_ohm=impedance,
                target_impedance_ohm=target_impedance_ohm,
                duration_ms=duration_ms,
            )

    @staticmethod
    def _read_output(path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
        frequencies: list[float] = []
        impedance: list[float] = []
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"frequency_hz", "impedance_ohm"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("external output must contain frequency_hz and impedance_ohm")
            for row in reader:
                frequencies.append(float(row["frequency_hz"]))
                impedance.append(float(row["impedance_ohm"]))
        return tuple(frequencies), tuple(impedance)

