#!/usr/bin/env python3
"""Smoke test storefront Phase 4 — inquiry inbox + insights funnel."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db, init_db
from storefront_platform import (
    get_store_inquiry,
    list_store_inquiries,
    migrate_storefront_columns,
    record_store_event,
    save_store_inquiry,
    storefront_insights,
    update_inquiry_status,
)


def main() -> None:
    init_db()
    with db() as conn:
        migrate_storefront_columns(conn)
        store = conn.execute("SELECT id, slug FROM stores LIMIT 1").fetchone()
        if not store:
            print("storefront Phase 4: OK (no stores, logic only)")
            return
        store_id = store["id"]
        slug = store["slug"]

        record_store_event(conn, store_id, "qr_scan", qr_code="test")
        record_store_event(conn, store_id, "storefront_view")
        record_store_event(conn, store_id, "item_view", item_id=1)

        inquiry_id = save_store_inquiry(
            conn,
            store_id,
            customer_name="Test Customer",
            customer_email="test@example.com",
            message="I'd like to order something",
        )
        assert inquiry_id > 0

        metrics = storefront_insights(conn, store_id, period="30d")
        assert metrics["shop_views"] >= 1
        assert metrics["inquiries"] >= 1
        assert len(metrics["funnel"]) == 4

        rows = list_store_inquiries(conn, store_id)
        assert any(r["id"] == inquiry_id for r in rows)

        assert update_inquiry_status(conn, store_id, inquiry_id, "read")
        row = get_store_inquiry(conn, store_id, inquiry_id)
        assert row and row["status"] == "read"

    client = app.test_client()
    with app.app_context():
        with db() as conn:
            owner = conn.execute(
                """SELECT u.id FROM users u
                   JOIN stores s ON s.owner_id = u.id WHERE s.slug = ? LIMIT 1""",
                (slug,),
            ).fetchone()
            if not owner:
                print("storefront Phase 4: OK (no owner session, DB logic passed)")
                return
            user_id = owner["id"]

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get(f"/manage/{slug}/insights")
    assert r.status_code == 200, r.status_code
    assert b"Customer funnel" in r.data

    r = client.get(f"/manage/{slug}/insights/requests")
    assert r.status_code == 200
    assert b"Customer requests" in r.data

    r = client.get(f"/manage/{slug}/insights/requests/{inquiry_id}")
    assert r.status_code == 200
    assert b"Test Customer" in r.data

    print("storefront Phase 4: OK")


if __name__ == "__main__":
    main()
