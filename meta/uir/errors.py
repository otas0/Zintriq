"""Errors for the unified intermediate representation."""

from __future__ import annotations


class UIRError(ValueError):
    """UIR graph is malformed or cannot round-trip a description."""
