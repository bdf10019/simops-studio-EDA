"""Deterministic parameter sweep expansion."""

from __future__ import annotations

from itertools import product

from simops_studio.hashing import hash_value
from simops_studio.models import ProjectConfig, SimulationCase


def expand_cases(config: ProjectConfig) -> list[SimulationCase]:
    keys = sorted(config.simulation.sweep)
    combinations = product(*(config.simulation.sweep[key] for key in keys)) if keys else [()]
    cases: list[SimulationCase] = []
    for sequence, values in enumerate(combinations, start=1):
        parameters = dict(config.simulation.base)
        parameters.update(dict(zip(keys, values, strict=True)))
        identity = {
            "project": config.name,
            "adapter": config.simulation.adapter,
            "frequency": {
                "start_hz": config.simulation.frequency.start_hz,
                "stop_hz": config.simulation.frequency.stop_hz,
                "points": config.simulation.frequency.points,
            },
            "target_impedance_ohm": config.simulation.target_impedance_ohm,
            "parameters": parameters,
        }
        input_hash = hash_value(identity)
        cases.append(
            SimulationCase(
                case_id=f"case-{input_hash[:12]}",
                sequence=sequence,
                parameters=parameters,
                input_hash=input_hash,
            )
        )
    return cases

