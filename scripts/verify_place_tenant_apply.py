#!/usr/bin/env python3
"""Verify place tenant self-apply and venue approval flow."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash

from app import app, db
from place_platform import (
    applications_for_place,
    approve_tenant_application,
    create_place,
    get_place_by_slug,
    migrate_place_tables,
    submit_tenant_application,
    tenants_for_place,
)


def main() -> None:
    with db() as conn:
        migrate_place_tables(conn)
        venue_email = "verify-venue@test.local"
        tenant_email = "verify-tenant@test.local"
        for email in (venue_email, tenant_email):
            conn.execute("DELETE FROM users WHERE email = ?", (email,))

        venue_id = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (venue_email, generate_password_hash("test", method="pbkdf2:sha256:600000")),
        ).lastrowid
        tenant_id = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (tenant_email, generate_password_hash("test", method="pbkdf2:sha256:600000")),
        ).lastrowid

        store = conn.execute(
            """SELECT * FROM stores WHERE owner_id IS NOT NULL
               AND COALESCE(status, 'active') != 'archived' LIMIT 1"""
        ).fetchone()
        if not store:
            print("place tenant apply: OK (no store)")
            conn.execute("DELETE FROM users WHERE id IN (?, ?)", (venue_id, tenant_id))
            return

        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (tenant_id, store["id"]))
        original_owner = store["owner_id"]
        place = create_place(conn, venue_id, name="Apply Test Hall", address="Test")
        place_id = place["id"]
        place_slug = place["slug"]
        store_id = store["id"]
        store_slug = store["slug"]

        result, app_id = submit_tenant_application(
            conn, place_id, store_id, tenant_id, unit_label="#A1", message="Please list us"
        )
        assert result == "submitted" and app_id
        pending = applications_for_place(conn, place_id, status="pending")
        assert len(pending) == 1

        assert approve_tenant_application(conn, app_id, venue_id)
        assert len(tenants_for_place(conn, place_id, public_only=True)) == 1
        assert len(applications_for_place(conn, place_id, status="pending")) == 0

        conn.execute("DELETE FROM place_analytics_events WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM place_tenant_applications WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM place_stores WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM places WHERE id = ?", (place_id,))
        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (original_owner, store_id))
        conn.execute("DELETE FROM users WHERE id IN (?, ?)", (venue_id, tenant_id))
        conn.commit()

    client = app.test_client()

    with db() as conn:
        venue_id = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("verify-venue-http@test.local", generate_password_hash("x", method="pbkdf2:sha256:600000")),
        ).lastrowid
        tenant_id = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("verify-tenant-http@test.local", generate_password_hash("x", method="pbkdf2:sha256:600000")),
        ).lastrowid
        store = conn.execute(
            "SELECT * FROM stores WHERE COALESCE(status, 'active') != 'archived' LIMIT 1"
        ).fetchone()
        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (tenant_id, store["id"]))
        place = create_place(conn, venue_id, name="HTTP Apply Hall")
        conn.commit()
        place_slug = place["slug"]
        store_slug = store["slug"]
        store_id = store["id"]

    def _csrf():
        with client.session_transaction() as sess:
            if not sess.get("csrf_token"):
                with app.test_request_context():
                    from app import csrf_token
                    sess["csrf_token"] = csrf_token()
            return sess["csrf_token"]

    with client.session_transaction() as sess:
        sess["user_id"] = tenant_id

    r = client.post(
        f"/manage/{store_slug}/place-membership",
        data={
            "csrf_token": _csrf(),
            "place_slug": place_slug,
            "unit_label": "L1-05",
            "message": "HTTP test",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"pending" in r.data.lower() or b"Application" in r.data

    with client.session_transaction() as sess:
        sess["user_id"] = venue_id

    r2 = client.get(f"/manage/places/{place_slug}")
    assert r2.status_code == 200
    assert b"Pending applications" in r2.data

    with db() as conn:
        app_row = conn.execute(
            "SELECT id FROM place_tenant_applications WHERE place_id = ? AND store_id = ?",
            (place["id"], store_id),
        ).fetchone()
        app_id = app_row["id"]

    r3 = client.post(
        f"/manage/places/{place_slug}",
        data={"csrf_token": _csrf(), "action": "approve_application", "application_id": app_id},
        follow_redirects=True,
    )
    assert r3.status_code == 200

    with db() as conn:
        assert len(tenants_for_place(conn, place["id"])) == 1
        conn.execute("DELETE FROM place_tenant_applications WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM place_stores WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM place_analytics_events WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM places WHERE id = ?", (place["id"],))
        conn.execute("DELETE FROM users WHERE id IN (?, ?)", (venue_id, tenant_id))
        conn.commit()

    print("place tenant apply: OK")


if __name__ == "__main__":
    main()
