#!/usr/bin/env python3
"""Smoke test Phase 7D — discovery polish (remember CTA, insights, brand hub)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from email_delivery import smtp_configured
from guest_platform import migrate_guest_tables, record_store_visit
from storefront_platform import migrate_storefront_columns, record_store_event, storefront_insights


def main() -> None:
    with db() as conn:
        migrate_guest_tables(conn)
        migrate_storefront_columns(conn)
        store = conn.execute(
            "SELECT * FROM stores WHERE owner_id IS NOT NULL AND COALESCE(status, 'active') != 'archived' LIMIT 1"
        ).fetchone()
        if not store:
            print("guest Phase 7D: OK (logic only, no owned store)")
            return

        visitor_key = "test-visitor-7d"
        record_store_visit(conn, visitor_key, store["id"], path="/store/test")
        record_store_visit(conn, visitor_key, store["id"], path="/store/test-again")
        record_store_event(conn, store["id"], "brand_hub_click", metadata={"from_store_slug": "other"})
        conn.commit()

        metrics = storefront_insights(conn, store["id"], period="30d")
        disc = metrics["discovery"]
        assert disc["unique_visitors"] >= 1
        assert disc["returning_visitors"] >= 1
        assert disc["brand_hub_clicks"] >= 1

        conn.execute("DELETE FROM guest_store_visits WHERE visitor_key = ?", (visitor_key,))
        conn.execute(
            "DELETE FROM store_analytics_events WHERE store_id = ? AND event_type = 'brand_hub_click'",
            (store["id"],),
        )
        conn.commit()

    client = app.test_client()
    slug = store["slug"]

    r = client.get("/store/does-not-exist-7d")
    assert r.status_code == 404

    r_header = client.get(f"/store/{slug}")
    assert r_header.status_code == 200
    assert b"Your places" in r_header.data

    r_places = client.get("/places")
    assert r_places.status_code == 200
    assert b"Your places" in r_places.data or b"Remember me" in r_places.data

    with client.session_transaction() as sess:
        sess["visitor_key"] = "phase7d-inquiry"
        if not sess.get("csrf_token"):
            with app.test_request_context():
                from app import csrf_token
                sess["csrf_token"] = csrf_token()

    r_inq = client.post(
        f"/store/{slug}/inquire",
        data={
            "csrf_token": _csrf(client),
            "customer_name": "Phase 7D",
            "customer_email": "phase7d@test.local",
            "message": "Test inquiry",
        },
        follow_redirects=True,
    )
    assert r_inq.status_code == 200
    assert b"Save this shop" in r_inq.data or b"Email me a save link" in r_inq.data

    r_brand = client.get(f"/store/{slug}?ref=brand_hub&from=other-store")
    assert r_brand.status_code == 200

    with db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS c FROM store_analytics_events
               WHERE store_id = ? AND event_type = 'brand_hub_click'""",
            (store["id"],),
        ).fetchone()
        assert int(row["c"] or 0) >= 1
        conn.execute("DELETE FROM store_inquiries WHERE customer_email = ?", ("phase7d@test.local",))
        conn.execute("DELETE FROM guest_store_visits WHERE visitor_key = ?", ("phase7d-inquiry",))
        conn.execute("DELETE FROM guest_visitor_profiles WHERE visitor_key = ?", ("phase7d-inquiry",))
        conn.commit()

    owner_id = None
    orig_owner = None
    with db() as conn:
        row = conn.execute("SELECT owner_id FROM stores WHERE slug = ?", (slug,)).fetchone()
        if row:
            orig_owner = row["owner_id"]
            user = conn.execute("SELECT id FROM users WHERE id = ?", (orig_owner,)).fetchone()
            if not user:
                from werkzeug.security import generate_password_hash
                owner_email = "verify-7d-owner@test.local"
                conn.execute("DELETE FROM users WHERE email = ?", (owner_email,))
                owner_id = int(
                    conn.execute(
                        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                        (owner_email, generate_password_hash("test", method="pbkdf2:sha256:600000")),
                    ).lastrowid
                )
                conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (owner_id, store["id"]))
            else:
                owner_id = orig_owner

    if owner_id:
        with client.session_transaction() as sess:
            sess["user_id"] = owner_id
        r_ins = client.get(f"/manage/{slug}/insights")
        assert r_ins.status_code == 200
        assert b"Guest discovery" in r_ins.data or b"Discovery" in r_ins.data

        if orig_owner != owner_id:
            with db() as conn:
                conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (orig_owner, store["id"]))
                conn.execute("DELETE FROM users WHERE email = ?", ("verify-7d-owner@test.local",))
                conn.commit()

    print(f"guest Phase 7D: OK (smtp_configured={smtp_configured()})")


def _csrf(client):
    with client.session_transaction() as sess:
        if not sess.get("csrf_token"):
            with app.test_request_context():
                from app import csrf_token
                sess["csrf_token"] = csrf_token()
        return sess["csrf_token"]


if __name__ == "__main__":
    main()
