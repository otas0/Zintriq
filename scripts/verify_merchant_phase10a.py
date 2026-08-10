#!/usr/bin/env python3
"""Verify Phase 10A — merchant closure (inbox, discover funnel, inquiry email)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash

from app import app, db
from discover_platform import discover_listing_readiness, migrate_discover_columns
from storefront_platform import (
    migrate_storefront_columns,
    notify_owner_new_inquiry,
    remember_storefront_ref,
    save_store_inquiry,
    storefront_insights,
)


def _csrf(client):
    with client.session_transaction() as sess:
        return sess.get("csrf_token") or ""


def main() -> None:
    owner_email = "verify-10a-owner@test.local"
    owner_id = None
    store_id = None
    slug = None
    orig_owner = None

    with db() as conn:
        migrate_storefront_columns(conn)
        migrate_discover_columns(conn)
        conn.execute("DELETE FROM users WHERE email = ?", (owner_email,))
        owner_id = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (owner_email, generate_password_hash("test", method="pbkdf2:sha256:600000")),
        ).lastrowid

        store = conn.execute(
            """SELECT * FROM stores WHERE COALESCE(status, 'active') != 'archived' LIMIT 1"""
        ).fetchone()
        if not store:
            print("merchant Phase 10A: OK (no store)")
            conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))
            return

        store_id = store["id"]
        slug = store["slug"]
        orig_owner = store["owner_id"]
        conn.execute(
            """UPDATE stores SET owner_id = ?, discoverable = 1, address = '1 Test St',
               latitude = 1.35, longitude = 103.82, business_hours_json = '{"mon":{"open":"09:00","close":"18:00"}}'
               WHERE id = ?""",
            (owner_id, store_id),
        )

        inquiry_id = save_store_inquiry(
            conn,
            store_id,
            customer_name="Phase 10A",
            customer_email="customer@test.local",
            message="Hello from discover",
            source_ref="discover",
        )

        readiness = discover_listing_readiness(
            dict(conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone())
        )
        assert readiness["ready"] is True

        assert notify_owner_new_inquiry(
            conn,
            store_id,
            inquiry_id,
            inbox_url="http://localhost/manage/test/inbox",
        ) is False

        metrics = storefront_insights(conn, store_id, period="30d")
        assert metrics["discovery"]["discover_inquiries"] >= 1

        conn.execute("DELETE FROM store_inquiries WHERE id = ?", (inquiry_id,))
        conn.commit()

    client = app.test_client()

    with client.session_transaction() as sess:
        remember_storefront_ref(sess, store_id, "discover")
        if not sess.get("csrf_token"):
            with app.test_request_context():
                from app import csrf_token
                sess["csrf_token"] = csrf_token()
        sess["visitor_key"] = "phase10a"

    r = client.post(
        f"/store/{slug}/inquire",
        data={
            "csrf_token": _csrf(client),
            "customer_name": "10A HTTP",
            "customer_email": "http@test.local",
            "message": "From discover session",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200

    with db() as conn:
        row = conn.execute(
            "SELECT source_ref FROM store_inquiries WHERE store_id = ? ORDER BY id DESC LIMIT 1",
            (store_id,),
        ).fetchone()
        assert row and row["source_ref"] == "discover"

    with client.session_transaction() as sess:
        sess["user_id"] = owner_id

    assert client.get(f"/manage/{slug}/insights/requests").status_code == 200
    assert client.get(f"/manage/{slug}/settings").status_code == 200
    r_ins = client.get(f"/manage/{slug}/insights")
    assert r_ins.status_code == 200
    assert b"Discover" in r_ins.data or b"Discovery" in r_ins.data

    with db() as conn:
        conn.execute(
            "DELETE FROM store_inquiries WHERE store_id = ? AND customer_name = '10A HTTP'",
            (store_id,),
        )
        conn.execute(
            "UPDATE stores SET owner_id = ?, discoverable = 0 WHERE id = ?",
            (orig_owner, store_id),
        )
        conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))
        conn.commit()

    print("merchant Phase 10A: OK")


if __name__ == "__main__":
    main()
