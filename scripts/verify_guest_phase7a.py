#!/usr/bin/env python3
"""Smoke test Phase 7A — guest visitor_key, My Places, inquiry binding."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from guest_platform import (
    bind_inquiry_to_guest,
    ensure_visitor_key,
    guest_contact_hints,
    migrate_guest_tables,
    recent_store_count,
    recent_stores_for_visitor,
    record_store_visit,
)


def main() -> None:
    with db() as conn:
        migrate_guest_tables(conn)
        store = conn.execute(
            "SELECT * FROM stores WHERE owner_id IS NOT NULL AND COALESCE(status, 'active') != 'archived' LIMIT 1"
        ).fetchone()
        if not store:
            print("guest Phase 7A: OK (logic only, no owned store)")
            return

        visitor_key = "test-visitor-phase7a"
        record_store_visit(conn, visitor_key, store["id"], path="/store/test")
        assert recent_store_count(conn, visitor_key) >= 1
        places = recent_stores_for_visitor(conn, visitor_key)
        assert any(p["slug"] == store["slug"] for p in places)

        inquiry_id = conn.execute(
            """INSERT INTO store_inquiries (store_id, customer_name, customer_email, message, status)
               VALUES (?, 'Guest Test', 'guest@test.com', 'Hi', 'new')""",
            (store["id"],),
        ).lastrowid
        cid = bind_inquiry_to_guest(
            conn,
            visitor_key,
            dict(store),
            customer_name="Guest Test",
            customer_email="guest@test.com",
            inquiry_id=int(inquiry_id),
        )
        assert cid
        hints = guest_contact_hints(conn, visitor_key)
        assert hints.get("customer_name") == "Guest Test"
        assert hints.get("customer_email") == "guest@test.com"

        conn.execute("DELETE FROM store_inquiries WHERE id = ?", (inquiry_id,))
        conn.execute(
            "DELETE FROM guest_store_visits WHERE visitor_key = ? AND store_id = ?",
            (visitor_key, store["id"]),
        )
        conn.execute("DELETE FROM guest_visitor_profiles WHERE visitor_key = ?", (visitor_key,))
        conn.commit()

    client = app.test_client()
    slug = store["slug"]

    with client.session_transaction() as sess:
        sess["visitor_key"] = "phase7a-client"

    r = client.get(f"/store/{slug}")
    assert r.status_code == 200, r.status_code
    assert b"Your places" in r.data or b"sf-page" in r.data

    r2 = client.get("/places")
    assert r2.status_code == 200
    assert b"My Places" in r2.data or b"Shops you" in r2.data

    with db() as conn:
        count = recent_store_count(conn, "phase7a-client")
        assert count >= 1
        conn.execute("DELETE FROM guest_store_visits WHERE visitor_key = ?", ("phase7a-client",))
        conn.commit()

    print("guest Phase 7A: OK")


if __name__ == "__main__":
    main()
