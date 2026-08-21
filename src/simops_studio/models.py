"""Configuration and workflow data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PDN_PARAMETER_NAMES = (
    "plane_resistance_ohm",
    "plane_inductance_h",
    "capacitance_f",
    "capacitor_esr_ohm",
    "capacitor_esl_h",
)


class ConfigurationError(ValueError):
    """Raised when a project file fails validation."""


@dataclass(frozen=True)
class FrequencyConfig:
    start_hz: float
    stop_hz: float
    points: int


@dataclass(frozen=True)
class SimulationConfig:
    adapter: str
    frequency: FrequencyConfig
    target_impedance_ohm: float
    base: dict[str, float]
    sweep: dict[str, tuple[float, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerConfig:
    name: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowConfig:
    workers: tuple[WorkerConfig, ...]
    retries: int
    priority: str


@dataclass(frozen=True)
class PcbRules:
    min_track_width_mm: float
    min_via_drill_mm: float
    min_annular_ring_mm: float


@dataclass(frozen=True)
class PcbConfig:
    path: Path
    rules: PcbRules


@dataclass(frozen=True)
class AiConfig:
    enabled: bool
    model_path: Path
    min_samples: int


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    description: str
    source_path: Path
    config_hash: str
    raw: dict[str, Any]
    simulation: SimulationConfig
    workflow: WorkflowConfig
    output_dir: Path
    database_path: Path
    pcb: PcbConfig | None
    ai: AiConfig

