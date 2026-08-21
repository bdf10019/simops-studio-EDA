"""Simulation adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from simops_studio.models import FrequencyConfig, SimulationCase, SimulationResult


class AdapterUnavailable(RuntimeError):
    """Raised when an optional solver executable is not available."""


class SimulationAdapter(ABC):
    name: str

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def simulate(
        self,
        case: SimulationCase,
        frequency: FrequencyConfig,
        target_impedance_ohm: float,
    ) -> SimulationResult:
        raise NotImplementedError

