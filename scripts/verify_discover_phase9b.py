#!/usr/bin/env python3
"""Verify Phase 9B — Discover map + search."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from discover_platform import discoverable_stores, migrate_discover_columns
from storefront_platform import migrate_storefront_columns


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
            print("discover Phase 9B: OK (no store)")
            return

        store_id = store["id"]
        slug = store["slug"]
        conn.execute(
            """UPDATE stores SET discoverable = 1, latitude = 1.3521, longitude = 103.8198,
               owner_name = '9B Test Brand', name = ?
               WHERE id = ?""",
            (store["name"], store_id),
        )
        conn.commit()

        by_name = discoverable_stores(conn, q=store["name"][:4].lower())
        assert any(s["slug"] == slug for s in by_name), "search should match store name"

        by_brand = discoverable_stores(conn, category="9B Test Brand")
        assert any(s["slug"] == slug for s in by_brand), "category filter should match owner_name"

        listed = discoverable_stores(conn, lat=1.3521, lng=103.8198, radius_km=50)
        assert any(s["slug"] == slug for s in listed)
        assert all("search_text" in s for s in listed)

        conn.execute("UPDATE stores SET discoverable = 0 WHERE id = ?", (store_id,))
        conn.commit()

    client = app.test_client()
    with db() as conn:
        conn.execute("UPDATE stores SET discoverable = 1 WHERE id = ?", (store_id,))
        conn.commit()

    r = client.get("/discover")
    assert r.status_code == 200
    assert b"discover-map" in r.data
    assert b"discover-search" in r.data
    assert b"Map" in r.data
    assert slug.encode() in r.data

    r2 = client.get(f"/discover?q={store['name'][:4]}")
    assert r2.status_code == 200
    assert slug.encode() in r2.data

    r3 = client.get("/api/discover/stores")
    assert r3.status_code == 200
    payload = json.loads(r3.data)
    assert "stores" in payload
    assert any(s["slug"] == slug for s in payload["stores"])

    r4 = client.get("/api/discover/stores?q=zzzznotfound999")
    assert r4.status_code == 200
    payload4 = json.loads(r4.data)
    assert payload4["stores"] == []

    with db() as conn:
        conn.execute("UPDATE stores SET discoverable = 0 WHERE id = ?", (store_id,))
        conn.commit()

    print("discover Phase 9B: OK")


if __name__ == "__main__":
    main()
