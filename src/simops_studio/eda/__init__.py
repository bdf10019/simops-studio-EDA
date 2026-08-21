"""EDA adapter factory."""

from __future__ import annotations

from typing import Any

from simops_studio.eda.base import AdapterUnavailable, SimulationAdapter
from simops_studio.eda.builtin import BuiltInPdnAdapter
from simops_studio.eda.external import ExternalCommandAdapter
from simops_studio.eda.ngspice import NgspiceAdapter


def create_adapter(name: str, options: dict[str, Any] | None = None) -> SimulationAdapter:
    options = options or {}
    if name == "builtin-pdn":
        return BuiltInPdnAdapter()
    if name == "ngspice":
        return NgspiceAdapter(executable=str(options.get("executable", "ngspice")))
    if name == "external-command":
        command = options.get("command")
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise ValueError("external-command requires adapter_options.command as a string list")
        return ExternalCommandAdapter(command=command)
    raise ValueError(f"unsupported adapter: {name}")


__all__ = ["AdapterUnavailable", "SimulationAdapter", "create_adapter"]

