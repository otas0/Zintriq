"""External platform integrations — reputation, documentation, etc."""

from __future__ import annotations

EXTERNAL_CATEGORIES = ("scheduling", "payments", "documentation", "reputation")


def list_available_plugins(conn) -> list[dict]:
    from integration_platform import get_plugin_by_slug
    rows = conn.execute(
        "SELECT slug, name, provider, description, category, status FROM integration_plugins ORDER BY name",
    ).fetchall()
    return [dict(r) for r in rows]
