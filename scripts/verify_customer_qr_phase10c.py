#!/usr/bin/env python3
"""Verify Phase 10C — unified Customer QR hub and owner-facing naming."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    sys.exit(1)


def main() -> None:
    from app import app, db
    from customer_qr_platform import manage_landing_qr_href, manage_qr_hub_path

    owner_email = "verify-10c-owner@test.local"
    owner_id = None
    store_id = None
    slug = None
    orig_owner = None

    with app.app_context():
        with db() as conn:
            conn.execute("DELETE FROM users WHERE email = ?", (owner_email,))
            owner_id = int(
                conn.execute(
                    "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                    (owner_email, generate_password_hash("test", method="pbkdf2:sha256:600000")),
                ).lastrowid
            )
            row = conn.execute(
                """SELECT s.id, s.slug, s.owner_id FROM stores s
                   WHERE COALESCE(s.status, 'active') != 'archived' LIMIT 1"""
            ).fetchone()
            if not row:
                conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))
                fail("no store in database")
            store_id, slug, orig_owner = int(row["id"]), row["slug"], row["owner_id"]
            conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (owner_id, store_id))

            exp = conn.execute(
                """SELECT id FROM qr_experiences
                   WHERE store_id=? AND status!='archived' LIMIT 1""",
                (store_id,),
            ).fetchone()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = owner_id

    try:
        hub = client.get(f"/manage/{slug}/qr")
        if hub.status_code != 200:
            fail(f"hub status {hub.status_code}")
        body = hub.get_data(as_text=True)
        if "Customer QR" not in body or "Shop QR" not in body or "Landing QR" not in body:
            fail("hub missing unified sections")
        ok("Customer QR hub page")

        shop = client.get(f"/manage/{slug}/qr-codes")
        if shop.status_code != 200 or "Shop QR" not in shop.get_data(as_text=True):
            fail("shop QR page")
        ok("Shop QR sub-page")

        landing = client.get(f"/manage/{slug}/landing-qr")
        if landing.status_code != 200 or "Landing QR" not in landing.get_data(as_text=True):
            fail("landing QR page")
        ok("Landing QR sub-page")

        legacy = client.get("/app/qr", follow_redirects=False)
        if legacy.status_code not in (301, 302, 303, 307, 308):
            fail(f"/app/qr expected redirect, got {legacy.status_code}")
        loc = legacy.headers.get("Location", "")
        if "experiences" not in loc and "/manage/" not in loc:
            fail(f"/app/qr bad redirect: {loc}")
        ok("/app/qr redirects to unified entry")

        if exp:
            with app.app_context():
                with db() as conn:
                    href = manage_landing_qr_href(conn, int(exp["id"]))
            if f"/manage/{slug}/landing-qr" not in href:
                fail(f"landing href wrong: {href}")
            ok("manage_landing_qr_href resolves store path")

            deep = client.get(f"/app/qr?experience={exp['id']}", follow_redirects=False)
            if deep.status_code not in (301, 302, 303, 307, 308):
                fail(f"deep link status {deep.status_code}")
            deep_loc = deep.headers.get("Location", "")
            if f"/manage/{slug}/landing-qr" not in deep_loc:
                fail(f"deep link redirect wrong: {deep_loc}")
            ok("/app/qr?experience= redirects to store landing QR")

        expected_hub = manage_qr_hub_path(slug)
        if expected_hub != f"/manage/{slug}/qr":
            fail("manage_qr_hub_path")
        ok("hub path helper")
    finally:
        with app.app_context():
            with db() as conn:
                if store_id is not None and orig_owner is not None:
                    conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (orig_owner, store_id))
                if owner_id is not None:
                    conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))

    print("verify_customer_qr_phase10c: all checks passed")


if __name__ == "__main__":
    main()
