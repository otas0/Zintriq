"""Errors for the meta-description layer."""

from __future__ import annotations


class DescriptionError(ValueError):
    """Description is malformed, inconsistent, or not serializable."""
