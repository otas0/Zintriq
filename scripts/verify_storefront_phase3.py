#!/usr/bin/env python3
"""Smoke test storefront Phase 3 — polish."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db, init_db
from storefront_platform import (
    build_location_profile,
    build_store_profile,
    deal_schedule_status,
    format_distance_km,
    haversine_km,
    maps_embed_url,
    migrate_storefront_columns,
    save_deal_from_form,
    save_store_inquiry,
)


class FakeForm(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeRow(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)

    def keys(self):
        return super().keys()


def main() -> int:
    init_db()
    conn = __import__("sqlite3").connect(ROOT / "marketqr.db")
    conn.row_factory = __import__("sqlite3").Row
    migrate_storefront_columns(conn)

    assert haversine_km(0, 0, 0, 1) > 110
    assert "km away" in format_distance_km(2.4)
    assert "m away" in format_distance_km(0.4)

    url = maps_embed_url(1.3521, 103.8198)
    assert "openstreetmap.org" in url

    future = (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    row = FakeRow({"status": "active", "starts_at": future, "ends_at": None})
    assert deal_schedule_status(row) == "scheduled"

    past = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    row = FakeRow({"status": "active", "starts_at": None, "ends_at": past})
    assert deal_schedule_status(row) == "expired"

    store = conn.execute("SELECT * FROM stores LIMIT 1").fetchone()
    if store:
        conn.execute(
            "UPDATE stores SET latitude=1.3521, longitude=103.8198 WHERE id=?",
            (store["id"],),
        )
        conn.commit()
        store = conn.execute("SELECT * FROM stores WHERE id=?", (store["id"],)).fetchone()
        profile = build_store_profile(conn, store)
        assert profile["location"]["lat"] == 1.3521
        assert profile["location"]["map_embed_url"]

        loc = build_location_profile(store)
        assert loc["map_embed_url"]

        item = conn.execute(
            "SELECT id FROM items WHERE store_id=? LIMIT 1", (store["id"],)
        ).fetchone()
        if item:
            save_deal_from_form(conn, store["id"], item["id"], FakeForm({
                f"deal_enabled_{item['id']}": "1",
                f"deal_type_{item['id']}": "percent",
                f"deal_value_{item['id']}": "10",
                f"deal_starts_{item['id']}": future,
            }))
            conn.commit()

        inquiry_id = save_store_inquiry(
            conn,
            store["id"],
            customer_name="Test Shopper",
            customer_email="test@example.com",
            message="Phase 3 verify",
        )
        conn.commit()
        assert inquiry_id > 0

    with app.test_client() as c:
        if store:
            slug = store["slug"]
            r = c.get(f"/store/{slug}")
            assert r.status_code == 200
            assert b"sf-search" in r.data
            assert b"sf-inquiry" in r.data or b"Send request" in r.data

            r2 = c.post(
                f"/store/{slug}/inquire",
                data={
                    "csrf_token": "test",
                    "customer_name": "Buyer",
                    "message": "Hello",
                },
                follow_redirects=False,
            )
            assert r2.status_code in (302, 400)

    print("storefront Phase 3: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
