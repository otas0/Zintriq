"""Calendar integrations — delegates to existing Google Calendar plugin."""

from __future__ import annotations


def calendar_provider_slug() -> str:
    from integrations.config import calendar_provider_name
    return calendar_provider_name()


def is_calendar_available(conn, user_id: int) -> bool:
    from integration_platform import get_user_connection
    row = get_user_connection(conn, user_id, "google_calendar")
    return bool(row and row["status"] in ("connected", "active", "installed"))
