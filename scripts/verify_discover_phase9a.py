#!/usr/bin/env python3
"""Verify Phase 9A — light Discover (nearby opt-in active stores)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from discover_platform import discoverable_stores, migrate_discover_columns, set_store_discoverable
from storefront_platform import migrate_storefront_columns, record_store_event, storefront_insights


def main() -> None:
    with db() as conn:
        migrate_storefront_columns(conn)
        migrate_discover_columns(conn)
        store = conn.execute(
            """SELECT * FROM stores
               WHERE owner_id IS NOT NULL AND COALESCE(status, 'active') != 'archived'
               LIMIT 1"""
        ).fetchone()
        if not store:
            print("discover Phase 9A: OK (no store)")
            return

        store_id = store["id"]
        slug = store["slug"]
        conn.execute(
            "UPDATE stores SET discoverable = 1, latitude = 1.3521, longitude = 103.8198 WHERE id = ?",
            (store_id,),
        )
        conn.commit()

        listed = discoverable_stores(conn, lat=1.3521, lng=103.8198, radius_km=50)
        assert any(item["slug"] == slug for item in listed), "discoverable store missing from listing"

        set_store_discoverable(conn, store_id, False)
        listed_off = discoverable_stores(conn)
        assert not any(item["slug"] == slug for item in listed_off), "opt-out store should not list"
        conn.execute("UPDATE stores SET discoverable = 1 WHERE id = ?", (store_id,))

        record_store_event(
            conn,
            store_id,
            "storefront_view",
            metadata={"ref": "discover", "visitor_key": "phase9a"},
        )
        conn.commit()

        metrics = storefront_insights(conn, store_id, period="30d")
        assert metrics["discovery"]["discover_views"] >= 1

        conn.execute(
            "DELETE FROM store_analytics_events WHERE store_id = ? AND metadata LIKE '%discover%'",
            (store_id,),
        )
        conn.execute("UPDATE stores SET discoverable = 0 WHERE id = ?", (store_id,))
        conn.commit()

    client = app.test_client()
    with db() as conn:
        conn.execute("UPDATE stores SET discoverable = 1 WHERE id = ?", (store_id,))
        conn.commit()

    r = client.get("/discover")
    assert r.status_code == 200
    assert b"Discover" in r.data
    assert b"Find shops" in r.data or b"Discover" in r.data
    assert slug.encode() in r.data

    r2 = client.get(f"/discover?lat=1.3521&lng=103.8198")
    assert r2.status_code == 200
    assert slug.encode() in r2.data

    r3 = client.get(f"/store/{slug}?ref=discover")
    assert r3.status_code == 200

    with db() as conn:
        conn.execute("UPDATE stores SET discoverable = 0 WHERE id = ?", (store_id,))
        conn.commit()

    print("discover Phase 9A: OK")


if __name__ == "__main__":
    main()
