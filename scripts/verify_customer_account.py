#!/usr/bin/env python3
"""Verify shopper account auth — guest default, customer login, no 2FA on customer path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash


def main() -> None:
    from app import app, db
    from customer_account_platform import ACCOUNT_KIND_CUSTOMER, migrate_customer_account_tables
    from guest_platform import ensure_visitor_key, migrate_guest_tables

    email = "verify-customer-auth@test.local"
    password = "TestPassword1234!"
    client = app.test_client()

    with app.app_context():
        with db() as conn:
            migrate_guest_tables(conn)
            migrate_customer_account_tables(conn)
            conn.execute("DELETE FROM users WHERE email = ?", (email,))
            conn.execute("DELETE FROM users WHERE email = ?", ("verify-merchant-other@test.local",))
            conn.execute("DELETE FROM customer_account_profiles WHERE username = ?", ("verify_shopper",))

    with client.session_transaction() as sess:
        sess.clear()

    r = client.get("/store/bcdeiohu")
    if r.status_code not in (200, 404):
        pass
    with client.session_transaction() as sess:
        assert sess.get("visitor_key"), "first visit should create guest visitor_key"
        assert not sess.get("customer_user_id"), "first visit should not auto-login customer"

    r_guest = client.get("/account")
    assert r_guest.status_code == 200
    assert b"customer-auth-root" in r_guest.data
    assert b"ig-profile--guest" in r_guest.data

    r_login_redirect = client.get("/account/login", follow_redirects=False)
    assert r_login_redirect.status_code in (302, 303)
    assert "open=login" in (r_login_redirect.headers.get("Location") or "")

    with app.app_context():
        with db() as conn:
            uid = conn.execute(
                """INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, ?)""",
                (email, generate_password_hash(password, method="pbkdf2:sha256:600000"), ACCOUNT_KIND_CUSTOMER),
            ).lastrowid
            conn.execute(
                """INSERT INTO customer_account_profiles (user_id, username, display_name, updated_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                (uid, "verify_shopper", email.split("@")[0]),
            )
            merchant_uid = conn.execute(
                """INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, ?)""",
                (
                    "verify-merchant-other@test.local",
                    generate_password_hash(password, method="pbkdf2:sha256:600000"),
                    "merchant",
                ),
            ).lastrowid

    with client.session_transaction() as sess:
        sess["user_id"] = merchant_uid

    r = client.post(
        "/account/login",
        data={
            "csrf_token": _csrf(client, "/account"),
            "email": email,
            "password": password,
            "next": "/app/store",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.status_code
    assert (r.headers.get("Location") or "").endswith("/home")

    with client.session_transaction() as sess:
        assert sess.get("customer_user_id") == uid
        assert sess.get("visitor_key"), "visitor_key kept alongside customer login"
        assert not sess.get("user_id"), "customer login must clear merchant session"
        saved = dict(sess)

    client2 = app.test_client()
    with client2.session_transaction() as sess:
        sess.update(saved)
    r_persist = client2.get("/account")
    assert r_persist.status_code == 200
    assert b"verify_shopper" in r_persist.data or email.encode() in r_persist.data

    r5 = client.get("/app/store", follow_redirects=False)
    assert r5.status_code in (302, 303)
    assert "home" in (r5.headers.get("Location") or "")

    r2 = client.get("/account")
    assert r2.status_code == 200
    assert b"verify_shopper" in r2.data or email.encode() in r2.data

    r3 = client.post(
        "/login",
        data={"csrf_token": _csrf(client, "/login"), "email": email, "password": password},
        follow_redirects=True,
    )
    assert b"shopper account" in r3.data.lower() or b"shop menu" in r3.data.lower()

    with app.app_context():
        with db() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            conn.execute("DELETE FROM users WHERE id = ?", (merchant_uid,))

    print("verify_customer_account: all checks passed")


def _csrf(client, path: str = "/account"):
    r = client.get(path)
    assert r.status_code == 200, f"expected 200 from {path}, got {r.status_code}"
    import re

    m = re.search(rb'name="csrf_token" value="([^"]+)"', r.data)
    assert m, "csrf token missing on page"
    return m.group(1).decode()


if __name__ == "__main__":
    main()
