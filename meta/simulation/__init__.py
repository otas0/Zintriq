"""Meta-simulation layer (minimal subset: discrete state machines)."""

from __future__ import annotations

from meta.simulation.errors import SimulationError
from meta.simulation.machine import (
    StateMachine,
    Transition,
    events_from_state,
    machine_from_desc,
    machine_to_desc,
    step,
)

__all__ = [
    "SimulationError",
    "StateMachine",
    "Transition",
    "events_from_state",
    "machine_from_desc",
    "machine_to_desc",
    "step",
]
