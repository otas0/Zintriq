#!/usr/bin/env python3
"""Smoke test Phase 8 — place directory (venue QR, tenant listing)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from place_platform import (
    add_place_tenant,
    create_place,
    get_place_by_slug,
    migrate_place_tables,
    place_insights,
    tenants_for_place,
)


def main() -> None:
    with db() as conn:
        migrate_place_tables(conn)
        store = conn.execute(
            "SELECT * FROM stores WHERE owner_id IS NOT NULL AND COALESCE(status, 'active') != 'archived' LIMIT 1"
        ).fetchone()
        if not store:
            print("place Phase 8: OK (logic only, no store)")
            return

        owner_id = store["owner_id"]
        orig_owner_id = owner_id
        place = create_place(
            conn,
            owner_id,
            name="Test Food Hall Phase8",
            description="Verify directory",
            address="1 Test Way",
        )
        assert add_place_tenant(conn, place["id"], store["id"], unit_label="#01")
        tenants = tenants_for_place(conn, place["id"], public_only=True)
        assert len(tenants) == 1
        assert tenants[0]["slug"] == store["slug"]
        metrics = place_insights(conn, place["id"], period="30d")
        assert "views" in metrics

        conn.execute("DELETE FROM place_analytics_events WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM place_stores WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM places WHERE id = ?", (place["id"],))
        conn.commit()

    client = app.test_client()
    slug = store["slug"]

    with db() as conn:
        place = create_place(conn, owner_id, name="HTTP Test Hall")
        add_place_tenant(conn, place["id"], store["id"], unit_label="L2")
        place_slug = place["slug"]
        conn.commit()

    r = client.get(f"/place/{place_slug}")
    assert r.status_code == 200, r.status_code
    assert store["name"].encode() in r.data

    r2 = client.get(f"/place/{place_slug}/go/{slug}", follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert "place_directory" in (r2.headers.get("Location") or "")

    from werkzeug.security import generate_password_hash

    owner_email = "verify-place8-owner@test.local"
    temp_owner_id = None
    with db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (owner_id,)).fetchone()
        if not user:
            conn.execute("DELETE FROM users WHERE email = ?", (owner_email,))
            temp_owner_id = int(
                conn.execute(
                    "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (owner_email, generate_password_hash("test", method="pbkdf2:sha256:600000")),
                ).lastrowid
            )
            conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (temp_owner_id, store["id"]))
            owner_id = temp_owner_id
            conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = owner_id

    r3 = client.get("/manage/places")
    assert r3.status_code == 200
    assert b"Place directories" in r3.data or b"HTTP Test Hall" in r3.data

    r4 = client.get(f"/manage/places/{place_slug}")
    assert r4.status_code == 200
    assert b"Venue QR" in r4.data

    with db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM place_analytics_events WHERE place_id = ? AND event_type = 'place_view'",
            (place["id"],),
        ).fetchone()
        assert int(row["c"] or 0) >= 1
        conn.execute("DELETE FROM place_analytics_events WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM place_stores WHERE place_id = ?", (place["id"],))
        conn.execute("DELETE FROM places WHERE id = ?", (place["id"],))
        if temp_owner_id:
            conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (orig_owner_id, store["id"]))
            conn.execute("DELETE FROM users WHERE email = ?", (owner_email,))
        conn.commit()

    print("place Phase 8: OK")


if __name__ == "__main__":
    main()
