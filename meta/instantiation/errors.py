"""Errors for the meta-instantiation layer."""

from __future__ import annotations


class InstantiationError(ValueError):
    """Source cannot be compiled to the requested target."""
