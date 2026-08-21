"""Always-available built-in adapter."""

from __future__ import annotations

from simops_studio.eda.base import SimulationAdapter
from simops_studio.models import FrequencyConfig, SimulationCase, SimulationResult
from simops_studio.simulation import simulate_pdn


class BuiltInPdnAdapter(SimulationAdapter):
    name = "builtin-pdn"

    def available(self) -> bool:
        return True

    def simulate(
        self,
        case: SimulationCase,
        frequency: FrequencyConfig,
        target_impedance_ohm: float,
    ) -> SimulationResult:
        return simulate_pdn(case, frequency, target_impedance_ohm, adapter_name=self.name)

