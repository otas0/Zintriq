"""Discover — opt-in public store listings (Phase 9A list, 9B map + search)."""

from __future__ import annotations

from typing import Any

DEFAULT_DISCOVER_LIMIT = 100
DEFAULT_NEARBY_RADIUS_KM = 25.0


def migrate_discover_columns(conn) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(stores)")}
    if "discoverable" not in columns:
        conn.execute("ALTER TABLE stores ADD COLUMN discoverable INTEGER NOT NULL DEFAULT 0")


def set_store_discoverable(conn, store_id: int, discoverable: bool) -> None:
    conn.execute(
        "UPDATE stores SET discoverable = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (1 if discoverable else 0, store_id),
    )


def _search_haystack(store: dict[str, Any], profile: dict[str, Any]) -> str:
    parts = [
        store.get("name") or "",
        store.get("description") or "",
        store.get("owner_name") or "",
        store.get("address") or "",
        profile.get("address") or "",
    ]
    return " ".join(parts).lower()


def _store_discover_payload(
    conn,
    store: dict[str, Any],
    *,
    origin_lat: float | None = None,
    origin_lng: float | None = None,
) -> dict[str, Any]:
    from storefront_platform import build_store_profile, format_distance_km, haversine_km

    profile = build_store_profile(conn, store)
    hours = profile["hours"]
    store_lat = store.get("latitude")
    store_lng = store.get("longitude")
    distance_km = None
    distance_label = None
    if (
        origin_lat is not None
        and origin_lng is not None
        and store_lat is not None
        and store_lng is not None
    ):
        try:
            distance_km = haversine_km(origin_lat, origin_lng, float(store_lat), float(store_lng))
            distance_label = format_distance_km(distance_km)
        except (TypeError, ValueError):
            pass

    owner_name = (store.get("owner_name") or "").strip() or None
    return {
        "store_id": store["id"],
        "slug": store["slug"],
        "name": store["name"],
        "logo_url": profile.get("logo_url"),
        "description": (store.get("description") or "")[:120] or None,
        "address": profile.get("address"),
        "owner_name": owner_name,
        "category": owner_name,
        "is_open": hours.get("is_open"),
        "hours_line": hours.get("status_line") or hours.get("legacy_text"),
        "lat": store_lat,
        "lng": store_lng,
        "distance_km": distance_km,
        "distance_label": distance_label,
        "storefront_url": f"/store/{store['slug']}?ref=discover",
        "search_text": _search_haystack(store, profile),
    }


def discover_categories(stores: list[dict[str, Any]]) -> list[str]:
    names = sorted({s["category"] for s in stores if s.get("category")})
    return names


def discoverable_stores(
    conn,
    *,
    q: str | None = None,
    category: str | None = None,
    open_only: bool = False,
    lat: float | None = None,
    lng: float | None = None,
    limit: int = DEFAULT_DISCOVER_LIMIT,
    radius_km: float | None = DEFAULT_NEARBY_RADIUS_KM,
) -> list[dict[str, Any]]:
    """Active stores opted into public discover listing."""
    query = (q or "").strip().lower()
    category_filter = (category or "").strip() or None

    rows = conn.execute(
        """SELECT * FROM stores
           WHERE COALESCE(status, 'active') = 'active'
             AND COALESCE(discoverable, 0) = 1
           ORDER BY name COLLATE NOCASE
           LIMIT ?""",
        (max(1, min(limit, 200)),),
    ).fetchall()

    origin_lat = origin_lng = None
    if lat is not None and lng is not None:
        try:
            origin_lat = float(lat)
            origin_lng = float(lng)
        except (TypeError, ValueError):
            origin_lat = origin_lng = None

    apply_radius = origin_lat is not None and origin_lng is not None and not query and not category_filter

    out: list[dict[str, Any]] = []
    for row in rows:
        store = dict(row)
        item = _store_discover_payload(conn, store, origin_lat=origin_lat, origin_lng=origin_lng)

        if query and query not in item["search_text"]:
            continue
        if category_filter and (item.get("category") or "") != category_filter:
            continue
        if open_only and item.get("is_open") is not True:
            continue
        if apply_radius and item["distance_km"] is not None and radius_km is not None:
            if item["distance_km"] > radius_km:
                continue
        if apply_radius and item["distance_km"] is None and item["lat"] is None:
            continue

        out.append(item)

    if origin_lat is not None and origin_lng is not None:
        out.sort(
            key=lambda item: (
                item["distance_km"] is None,
                item["distance_km"] if item["distance_km"] is not None else 9999.0,
                item["name"].lower(),
            )
        )
    else:
        out.sort(key=lambda item: item["name"].lower())

    return out


def discover_listing_readiness(store: dict[str, Any]) -> dict[str, Any]:
    """Owner checklist for appearing on Discover."""
    has_address = bool((store.get("address") or "").strip())
    discoverable = bool(store.get("discoverable"))
    has_coords = store.get("latitude") is not None and store.get("longitude") is not None
    hours_raw = store.get("business_hours_json")
    has_hours = bool(hours_raw and str(hours_raw).strip() not in ("", "{}"))
    checks = [
        {"key": "address", "label": "Store address", "ok": has_address},
        {"key": "discoverable", "label": "List in Discover enabled", "ok": discoverable},
        {"key": "location", "label": "Location on map", "ok": has_coords},
        {"key": "hours", "label": "Business hours", "ok": has_hours},
    ]
    ready = discoverable and has_address
    return {
        "ready": ready,
        "checks": checks,
        "completed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
    }
