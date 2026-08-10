#!/usr/bin/env python3
"""Verify unified customer QR wizard API."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from werkzeug.security import generate_password_hash


def ok(msg):
    print(f"  OK  {msg}")


def fail(msg):
    print(f"  FAIL  {msg}")
    sys.exit(1)


def login_client(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-cqr-csrf"


def api_post(client, url, body, user_id):
    login_client(client, user_id)
    return client.post(
        url,
        json={**(body or {}), "csrf_token": "verify-cqr-csrf"},
        headers={"X-CSRF-Token": "verify-cqr-csrf", "Content-Type": "application/json"},
    )


def main():
    from app import app, db

    owner_email = "verify-cqr-wizard@test.local"
    owner_id = None
    store_id = None
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

    client = app.test_client()
    try:
        res = api_post(
            client,
            f"/api/stores/{store_id}/customer-qr",
            {"kind": "shop", "name": "Wizard test shop QR"},
            owner_id,
        )
        if res.status_code != 201:
            fail(f"shop qr status {res.status_code}: {res.get_data(as_text=True)}")
        data = res.get_json()
        if data.get("kind") != "shop" or "qr-codes" not in data.get("redirect", ""):
            fail(f"shop qr bad payload: {data}")
        ok("shop QR created")

        res = api_post(
            client,
            f"/api/stores/{store_id}/customer-qr",
            {"kind": "product", "name": "Wizard test product"},
            owner_id,
        )
        if res.status_code != 201:
            fail(f"product qr status {res.status_code}: {res.get_data(as_text=True)}")
        data = res.get_json()
        if data.get("kind") != "product" or "product-qr" not in data.get("redirect", ""):
            fail(f"product qr bad payload: {data}")
        ok("product QR created")

        res = api_post(client, f"/api/stores/{store_id}/customer-qr", {"kind": "nope", "name": "x"}, owner_id)
        if res.status_code != 400:
            fail(f"invalid kind expected 400, got {res.status_code}")
        ok("invalid kind rejected")
    finally:
        with app.app_context():
            with db() as conn:
                conn.execute("DELETE FROM qr_codes WHERE store_id = ? AND name LIKE 'Wizard test%'", (store_id,))
                conn.execute("DELETE FROM qr_products WHERE store_id = ? AND name LIKE 'Wizard test%'", (store_id,))
                if orig_owner is not None:
                    conn.execute("UPDATE stores SET owner_id = ? WHERE id = ?", (orig_owner, store_id))
                conn.execute("DELETE FROM users WHERE id = ?", (owner_id,))

    print("verify_customer_qr_wizard: all checks passed")


if __name__ == "__main__":
    main()
