"""Errors for the meta-simulation layer."""

from __future__ import annotations


class SimulationError(ValueError):
    """Simulation description is invalid or no transition applies."""
