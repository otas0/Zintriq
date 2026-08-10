#!/usr/bin/env python3
"""Verify Phase 8C — place tenant apply polish (metrics, directory CTA)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash

from app import app, db
from place_platform import (
    approve_tenant_application,
    create_place,
    migrate_place_tables,
    place_insights,
    submit_tenant_application,
)


def main() -> None:
    with db() as conn:
        migrate_place_tables(conn)
        venue_email = "verify-8c-venue@test.local"
        tenant_email = "verify-8c-tenant@test.local"
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
            print("place Phase 8C: OK (no store)")
            conn.execute("DELETE FROM users WHERE id IN (?, ?)", (venue_id, tenant_id))
            return

        orig_owner = store["owner_id"]
        store_id = store["id"]
        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (tenant_id, store_id))
        place = create_place(conn, venue_id, name="8C Polish Hall")
        place_id = place["id"]
        place_slug = place["slug"]

        submit_tenant_application(conn, place_id, store_id, tenant_id, unit_label="#1")
        metrics = place_insights(conn, place_id, period="30d")
        assert metrics["applications_submitted"] >= 1
        assert metrics["applications_pending"] >= 1

        app_row = conn.execute(
            "SELECT id FROM place_tenant_applications WHERE place_id = ? AND status = 'pending'",
            (place_id,),
        ).fetchone()
        assert approve_tenant_application(conn, app_row["id"], venue_id)
        metrics2 = place_insights(conn, place_id, period="30d")
        assert metrics2["applications_approved"] >= 1
        assert metrics2["application_approval_rate"] == 100

        conn.execute("DELETE FROM place_analytics_events WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM place_tenant_applications WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM place_stores WHERE place_id = ?", (place_id,))
        conn.execute("DELETE FROM places WHERE id = ?", (place_id,))
        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (orig_owner, store_id))
        conn.commit()

    client = app.test_client()

    with db() as conn:
        place = create_place(conn, venue_id, name="8C HTTP Hall")
        http_slug = place["slug"]
        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (tenant_id, store_id))
        conn.commit()

    r = client.get(f"/place/{http_slug}")
    assert r.status_code == 200
    assert b"Shop owner" in r.data
    assert b"Sign in to apply" in r.data

    with client.session_transaction() as sess:
        sess["user_id"] = tenant_id
    r2 = client.get(f"/place/{http_slug}")
    assert r2.status_code == 200
    assert b"Apply to list here" in r2.data

    with client.session_transaction() as sess:
        sess["user_id"] = venue_id
    r3 = client.get(f"/manage/places/{http_slug}")
    assert r3.status_code == 200
    assert b"Tenant apply link" in r3.data
    assert b"Pending now" in r3.data

    with db() as conn:
        conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (orig_owner, store_id))
        conn.execute("DELETE FROM places WHERE slug = ?", (http_slug,))
        conn.execute("DELETE FROM users WHERE id IN (?, ?)", (venue_id, tenant_id))
        conn.commit()

    print("place Phase 8C: OK")


if __name__ == "__main__":
    main()
