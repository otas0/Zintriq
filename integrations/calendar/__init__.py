"""Calendar integrations — external calendar providers (reserved for future use)."""

from __future__ import annotations


def calendar_provider_slug() -> str:
    return ""


def is_calendar_available(conn, user_id: int) -> bool:
    return False
