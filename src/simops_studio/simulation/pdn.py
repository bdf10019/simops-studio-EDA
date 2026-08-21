"""Lumped PDN impedance reference model.

The source path (plane R/L) is placed in parallel with a decoupling-capacitor
R/L/C branch. This is intentionally compact and deterministic: it is useful for
workflow demonstrations, parameter studies, and test fixtures, not field-solver
sign-off.
"""

from __future__ import annotations

import math
import time

from simops_studio.models import FrequencyConfig, SimulationCase, SimulationResult


def logarithmic_frequencies(config: FrequencyConfig) -> tuple[float, ...]:
    start = math.log10(config.start_hz)
    stop = math.log10(config.stop_hz)
    step = (stop - start) / (config.points - 1)
    return tuple(10 ** (start + index * step) for index in range(config.points))


def impedance_at_frequency(parameters: dict[str, float], frequency_hz: float) -> complex:
    omega = 2 * math.pi * frequency_hz
    plane = complex(
        parameters["plane_resistance_ohm"],
        omega * parameters["plane_inductance_h"],
    )
    capacitor = complex(
        parameters["capacitor_esr_ohm"],
        omega * parameters["capacitor_esl_h"]
        - 1.0 / (omega * parameters["capacitance_f"]),
    )
    denominator = plane + capacitor
    if abs(denominator) < 1e-30:
        return complex(math.inf, 0)
    return plane * capacitor / denominator


def build_result(
    *,
    case: SimulationCase,
    adapter: str,
    frequencies_hz: tuple[float, ...],
    impedance_ohm: tuple[float, ...],
    target_impedance_ohm: float,
    duration_ms: float,
) -> SimulationResult:
    if not frequencies_hz or len(frequencies_hz) != len(impedance_ohm):
        raise ValueError("frequency and impedance vectors must be non-empty and equal length")
    max_index = max(range(len(impedance_ohm)), key=impedance_ohm.__getitem__)
    min_index = min(range(len(impedance_ohm)), key=impedance_ohm.__getitem__)
    violations = sum(value > target_impedance_ohm for value in impedance_ohm)
    return SimulationResult(
        case_id=case.case_id,
        adapter=adapter,
        frequencies_hz=frequencies_hz,
        impedance_ohm=impedance_ohm,
        max_impedance_ohm=impedance_ohm[max_index],
        min_impedance_ohm=impedance_ohm[min_index],
        worst_frequency_hz=frequencies_hz[max_index],
        resonant_frequency_hz=frequencies_hz[min_index],
        violation_fraction=violations / len(impedance_ohm),
        passed=violations == 0,
        duration_ms=duration_ms,
    )


def simulate_pdn(
    case: SimulationCase,
    frequency: FrequencyConfig,
    target_impedance_ohm: float,
    *,
    adapter_name: str = "builtin-pdn",
) -> SimulationResult:
    started = time.perf_counter()
    frequencies = logarithmic_frequencies(frequency)
    impedance = tuple(abs(impedance_at_frequency(case.parameters, item)) for item in frequencies)
    duration_ms = (time.perf_counter() - started) * 1000
    return build_result(
        case=case,
        adapter=adapter_name,
        frequencies_hz=frequencies,
        impedance_ohm=impedance,
        target_impedance_ohm=target_impedance_ohm,
        duration_ms=duration_ms,
    )
