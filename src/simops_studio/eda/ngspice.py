"""Optional ngspice batch adapter.

The adapter generates a temporary one-amp AC injection deck. Voltage magnitude at
the PDN node is therefore the impedance magnitude. ngspice is optional and is never
downloaded or installed automatically.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from simops_studio.eda.base import AdapterUnavailable, SimulationAdapter
from simops_studio.models import FrequencyConfig, SimulationCase, SimulationResult
from simops_studio.simulation.pdn import build_result


class NgspiceAdapter(SimulationAdapter):
    name = "ngspice"

    def __init__(self, executable: str = "ngspice") -> None:
        self.executable = executable

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def simulate(
        self,
        case: SimulationCase,
        frequency: FrequencyConfig,
        target_impedance_ohm: float,
    ) -> SimulationResult:
        if not self.available():
            raise AdapterUnavailable(
                "ngspice is not installed; select builtin-pdn or install ngspice separately"
            )
        with tempfile.TemporaryDirectory(prefix="simops-ngspice-") as directory:
            work = Path(directory)
            deck = work / "pdn.cir"
            output = work / "impedance.csv"
            deck.write_text(self._deck(case, frequency, output), encoding="utf-8")
            started = time.perf_counter()
            process = subprocess.run(
                [self.executable, "-b", str(deck)],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            duration_ms = (time.perf_counter() - started) * 1000
            if process.returncode != 0 or not output.exists():
                detail = (process.stderr or process.stdout).strip()[-1000:]
                raise RuntimeError(f"ngspice failed with code {process.returncode}: {detail}")
            frequencies, impedance = self.parse_wrdata(output)
            return build_result(
                case=case,
                adapter=self.name,
                frequencies_hz=frequencies,
                impedance_ohm=impedance,
                target_impedance_ohm=target_impedance_ohm,
                duration_ms=duration_ms,
            )

    @staticmethod
    def _deck(case: SimulationCase, frequency: FrequencyConfig, output: Path) -> str:
        p = case.parameters
        decades = math.log10(frequency.stop_hz / frequency.start_hz)
        per_decade = max(1, math.ceil((frequency.points - 1) / decades))
        path = output.as_posix()
        return f"""SimOps Studio synthetic PDN
Itest 0 pdn AC 1
Rplane pdn nplane {p['plane_resistance_ohm']}
Lplane nplane 0 {p['plane_inductance_h']}
Resr pdn ncap1 {p['capacitor_esr_ohm']}
Lesl ncap1 ncap2 {p['capacitor_esl_h']}
Cdec ncap2 0 {p['capacitance_f']}
.control
set wr_singlescale
ac dec {per_decade} {frequency.start_hz} {frequency.stop_hz}
wrdata {path} mag(v(pdn))
quit
.endc
.end
"""

    @staticmethod
    def parse_wrdata(path: Path) -> tuple[tuple[float, ...], tuple[float, ...]]:
        frequencies: list[float] = []
        impedance: list[float] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            values: list[float] = []
            for token in line.replace(",", " ").split():
                try:
                    values.append(float(token))
                except ValueError:
                    continue
            if len(values) >= 2 and values[0] > 0 and values[-1] >= 0:
                frequencies.append(values[0])
                impedance.append(values[-1])
        if not frequencies:
            raise ValueError("ngspice output did not contain numeric frequency/impedance rows")
        return tuple(frequencies), tuple(impedance)

