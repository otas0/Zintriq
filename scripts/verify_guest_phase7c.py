#!/usr/bin/env python3
"""Smoke test Phase 7C — guest magic link remember-me."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app, db
from guest_platform import (
    apply_guest_remember_link,
    create_guest_remember_token,
    guest_remembered_email,
    merge_visitor_keys,
    migrate_guest_tables,
    recent_store_count,
    record_store_visit,
)


def main() -> None:
    with db() as conn:
        migrate_guest_tables(conn)
        store = conn.execute(
            "SELECT * FROM stores WHERE owner_id IS NOT NULL AND COALESCE(status, 'active') != 'archived' LIMIT 1"
        ).fetchone()
        if not store:
            print("guest Phase 7C: OK (logic only, no owned store)")
            return

        key_a = "test-visitor-7c-a"
        key_b = "test-visitor-7c-b"
        email = "guest-7c@test.local"

        record_store_visit(conn, key_a, store["id"], path="/store/test-a")
        token = create_guest_remember_token(conn, email, key_a)
        row = conn.execute(
            "SELECT * FROM guest_remember_tokens WHERE email = ?", (email,)
        ).fetchone()
        assert row

        canonical = apply_guest_remember_link(conn, row, key_b)
        session_key = canonical
        assert recent_store_count(conn, session_key) >= 1
        assert guest_remembered_email(conn, session_key) == email

        key_c = "test-visitor-7c-c"
        record_store_visit(conn, key_c, store["id"], path="/store/test-c")
        merged = merge_visitor_keys(conn, session_key, key_c)
        assert recent_store_count(conn, merged) >= 1

        conn.execute("DELETE FROM guest_email_identities WHERE email = ?", (email,))
        conn.execute("DELETE FROM guest_remember_tokens WHERE email = ?", (email,))
        conn.execute("DELETE FROM guest_store_visits WHERE visitor_key IN (?, ?, ?)", (key_a, key_b, key_c))
        conn.execute("DELETE FROM guest_store_visits WHERE visitor_key = ?", (session_key,))
        conn.execute(
            "DELETE FROM guest_visitor_profiles WHERE visitor_key IN (?, ?, ?, ?)",
            (key_a, key_b, key_c, session_key),
        )
        conn.commit()

    client = app.test_client()
    slug = store["slug"]
    flow_email = "guest-7c-flow@test.local"

    with client.session_transaction() as sess:
        sess["visitor_key"] = "phase7c-device-a"

    visit = client.get(f"/store/{slug}")
    assert visit.status_code == 200

    with db() as conn:
        token = create_guest_remember_token(conn, flow_email, "phase7c-device-a")
        conn.commit()

    with client.session_transaction() as sess:
        sess["visitor_key"] = "phase7c-device-b"

    signin_url = f"/guest/remember/{token}"

    r2 = client.get(signin_url, follow_redirects=True)
    assert r2.status_code == 200
    assert b"Remembered on this device" in r2.data or b"My Places" in r2.data

    with client.session_transaction() as sess:
        restored_key = sess.get("visitor_key")
        assert restored_key

    with db() as conn:
        assert recent_store_count(conn, restored_key) >= 1
        assert guest_remembered_email(conn, restored_key) == flow_email
        conn.execute("DELETE FROM guest_email_identities WHERE email = ?", (flow_email,))
        conn.execute("DELETE FROM guest_remember_tokens WHERE email = ?", (flow_email,))
        for vk in ("phase7c-device-a", "phase7c-device-b", restored_key):
            conn.execute("DELETE FROM guest_store_visits WHERE visitor_key = ?", (vk,))
        conn.execute(
            "DELETE FROM guest_visitor_profiles WHERE visitor_key IN (?, ?, ?)",
            ("phase7c-device-a", "phase7c-device-b", restored_key),
        )
        conn.commit()

    print("guest Phase 7C: OK")


if __name__ == "__main__":
    main()
