"""Customer home feed — discover + resume (not the full places library)."""

from __future__ import annotations

from typing import Any


def home_feed(
    conn,
    visitor_key: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
    avatar_limit: int = 3,
    venue_limit: int = 6,
) -> dict[str, Any]:
    from guest_platform import recent_stores_for_visitor, recent_store_count
    from place_platform import public_places

    recent = recent_stores_for_visitor(conn, visitor_key, limit=avatar_limit)
    total = recent_store_count(conn, visitor_key)
    continue_place = recent_stores_for_visitor(conn, visitor_key, limit=1)
    venues = public_places(conn, limit=venue_limit)

    return {
        "recent_places": recent,
        "recent_places_total": total,
        "continue_place": continue_place[0] if continue_place else None,
        "venues": venues,
    }
