#!/usr/bin/env python3
"""Verify shopper OTP signup (email + phone) and legacy password login."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash


def main() -> None:
    from app import app, db
    from customer_account_platform import ACCOUNT_KIND_CUSTOMER, migrate_customer_account_tables
    from customer_verification import migrate_verification_tables, phone_placeholder_email
    from guest_platform import migrate_guest_tables

    email = "verify-otp-email@test.local"
    legacy_email = "verify-legacy-login@test.local"
    phone = "+60198765432"
    phone_email = phone_placeholder_email(phone)
    password = "TestPassword1234!"
    client = app.test_client()

    with app.app_context():
        with db() as conn:
            migrate_guest_tables(conn)
            migrate_customer_account_tables(conn)
            migrate_verification_tables(conn)
            for target in (email, phone_email, legacy_email):
                conn.execute("DELETE FROM users WHERE email = ?", (target,))
            conn.execute("DELETE FROM users WHERE phone = ?", (phone,))
            for uname in ("legacy_shopper", "otp_email_user", "otp_phone_user", "merchant_shopper", "owner_shopper"):
                prow = conn.execute(
                    "SELECT user_id FROM customer_account_profiles WHERE username = ?", (uname,),
                ).fetchone()
                if prow:
                    conn.execute("DELETE FROM users WHERE id = ?", (prow["user_id"],))
                conn.execute("DELETE FROM customer_account_profiles WHERE username = ?", (uname,))

    with client.session_transaction() as sess:
        sess.clear()

    with app.app_context():
        with db() as conn:
            uid = conn.execute(
                """INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, ?)""",
                (legacy_email, generate_password_hash(password, method="pbkdf2:sha256:600000"), ACCOUNT_KIND_CUSTOMER),
            ).lastrowid
            conn.execute(
                """INSERT INTO customer_account_profiles (user_id, username, updated_at)
                   VALUES (?, ?, datetime('now'))""",
                (uid, "legacy_shopper"),
            )

    r = client.post(
        "/account/login",
        data={"csrf_token": _csrf(client), "email": legacy_email, "password": password, "next": "/home"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.status_code
    with client.session_transaction() as sess:
        sess.clear()

    _otp_signup(client, channel="email", target=email, username="otp_email_user")
    _otp_signup(client, channel="phone", target=phone, username="otp_phone_user")
    _merchant_activate_shopper(client)

    with app.app_context():
        with db() as conn:
            conn.execute("DELETE FROM users WHERE email = ?", (legacy_email,))
            conn.execute("DELETE FROM users WHERE email = ?", (phone_email,))

    print("verify_customer_otp: all checks passed")


def _merchant_activate_shopper(client) -> None:
    from app import app, db
    from customer_account_platform import migrate_customer_account_tables
    from customer_verification import _latest_code_row, hash_otp
    from werkzeug.security import generate_password_hash

    merchant_email = "verify-merchant-activate@test.local"
    password = "TestPassword1234!"
    owner_email = "verify-store-owner@test.local"

    with app.app_context():
        with db() as conn:
            migrate_customer_account_tables(conn)
            conn.execute("DELETE FROM stores WHERE slug = 'verify-owner-store'")
            conn.execute("DELETE FROM customer_verification_codes")
            conn.execute("DELETE FROM users WHERE email IN (?, ?)", (merchant_email, owner_email))
            for uname in ("merchant_shopper", "owner_shopper"):
                prow = conn.execute(
                    "SELECT user_id FROM customer_account_profiles WHERE username = ?", (uname,),
                ).fetchone()
                if prow:
                    conn.execute("DELETE FROM users WHERE id = ?", (prow["user_id"],))
                conn.execute("DELETE FROM customer_account_profiles WHERE username = ?", (uname,))
            merchant_uid = conn.execute(
                """INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, 'merchant')""",
                (merchant_email, generate_password_hash(password, method="pbkdf2:sha256:600000")),
            ).lastrowid
            owner_uid = conn.execute(
                """INSERT INTO users (email, password_hash, account_kind) VALUES (?, ?, 'merchant')""",
                (owner_email, generate_password_hash(password, method="pbkdf2:sha256:600000")),
            ).lastrowid
            conn.execute(
                """INSERT INTO stores (owner_id, name, slug, created_at) VALUES (?, 'Test', 'verify-owner-store', datetime('now'))""",
                (owner_uid,),
            )

    client.post("/account/logout", data={"csrf_token": _csrf(client), "next": "/home"})
    with client.session_transaction() as sess:
        sess.clear()

    headers = {
        "X-Customer-Auth": "1",
        "Content-Type": "application/json",
        "X-CSRF-Token": _csrf(client),
    }

    r_owner_send = client.post(
        "/account/verify/send",
        data=json.dumps({"channel": "email", "target": owner_email, "purpose": "signup"}),
        headers=headers,
    )
    assert r_owner_send.status_code == 200, r_owner_send.data
    assert r_owner_send.get_json().get("mode") == "activate"

    with app.app_context():
        with db() as conn:
            row = _latest_code_row(conn, "email", owner_email, "signup")
            conn.execute(
                "UPDATE customer_verification_codes SET code_hash = ? WHERE id = ?",
                (hash_otp("654321"), row["id"]),
            )

    client.post(
        "/account/verify/check",
        data=json.dumps({"channel": "email", "target": owner_email, "code": "654321", "purpose": "signup"}),
        headers=headers,
    )
    r_owner = client.post(
        "/account/onboarding/complete",
        data={
            "csrf_token": _csrf(client),
            "username": "owner_shopper",
            "display_name": "Owner Shopper",
            "next": "/home",
        },
        headers={"X-Customer-Auth": "1", "X-CSRF-Token": _csrf(client)},
    )
    assert r_owner.status_code == 200, r_owner.data
    with client.session_transaction() as sess:
        assert int(sess.get("customer_user_id")) == int(owner_uid)
    with app.app_context():
        with db() as conn:
            prow = conn.execute(
                "SELECT username FROM customer_account_profiles WHERE user_id = ?",
                (owner_uid,),
            ).fetchone()
            assert prow and prow["username"] == "owner_shopper"


    client.post(
        "/account/logout",
        data={"csrf_token": _csrf(client), "next": "/home"},
    )
    with client.session_transaction() as sess:
        sess.clear()

    headers["X-CSRF-Token"] = _csrf(client)
    r_send = client.post(
        "/account/verify/send",
        data=json.dumps({"channel": "email", "target": merchant_email, "purpose": "signup"}),
        headers=headers,
    )
    assert r_send.status_code == 200, r_send.data
    assert r_send.get_json().get("mode") == "activate"

    with app.app_context():
        with db() as conn:
            row = _latest_code_row(conn, "email", merchant_email, "signup")
            conn.execute(
                "UPDATE customer_verification_codes SET code_hash = ? WHERE id = ?",
                (hash_otp("123456"), row["id"]),
            )

    r_check = client.post(
        "/account/verify/check",
        data=json.dumps({"channel": "email", "target": merchant_email, "code": "123456", "purpose": "signup"}),
        headers=headers,
    )
    assert r_check.get_json().get("skip_password") is True

    r_done = client.post(
        "/account/onboarding/complete",
        data={
            "csrf_token": _csrf(client),
            "username": "merchant_shopper",
            "display_name": "Merchant Shopper",
            "next": "/home",
        },
        headers={"X-Customer-Auth": "1", "X-CSRF-Token": _csrf(client)},
    )
    assert r_done.status_code == 200, r_done.data

    with client.session_transaction() as sess:
        assert int(sess.get("customer_user_id")) == int(merchant_uid)

    r_acct = client.get("/account")
    assert b"merchant_shopper" in r_acct.data

    with app.app_context():
        with db() as conn:
            conn.execute("DELETE FROM stores WHERE slug = 'verify-owner-store'")
            conn.execute("DELETE FROM users WHERE email IN (?, ?)", (merchant_email, owner_email))


def _otp_signup(client, *, channel: str, target: str, username: str) -> None:
    from app import app, db
    from customer_verification import _latest_code_row, hash_otp

    client.post(
        "/account/logout",
        data={"csrf_token": _csrf(client), "next": "/home"},
    )

    headers = {
        "X-Customer-Auth": "1",
        "Content-Type": "application/json",
        "X-CSRF-Token": _csrf(client),
    }

    r_send = client.post(
        "/account/verify/send",
        data=json.dumps({"channel": channel, "target": target, "purpose": "signup"}),
        headers=headers,
    )
    assert r_send.status_code == 200, r_send.data
    assert r_send.get_json()["ok"] is True

    with app.app_context():
        with db() as conn:
            row = _latest_code_row(conn, channel, target, "signup")
            assert row, "verification row missing"
            code = "123456"
            conn.execute(
                "UPDATE customer_verification_codes SET code_hash = ? WHERE id = ?",
                (hash_otp(code), row["id"]),
            )

    r_check = client.post(
        "/account/verify/check",
        data=json.dumps({"channel": channel, "target": target, "code": "123456", "purpose": "signup"}),
        headers=headers,
    )
    assert r_check.status_code == 200, r_check.data
    body = r_check.get_json()
    assert body["ok"] and body.get("verified")

    r_done = client.post(
        "/account/onboarding/complete",
        data={
            "csrf_token": _csrf(client),
            "username": username,
            "password": "TestPassword1234!",
            "confirm_password": "TestPassword1234!",
            "display_name": "OTP Tester",
            "next": "/home",
        },
        headers={"X-Customer-Auth": "1", "X-CSRF-Token": _csrf(client)},
    )
    assert r_done.status_code == 200, r_done.data
    assert r_done.get_json()["ok"] is True

    with client.session_transaction() as sess:
        assert sess.get("customer_user_id"), "should be signed in after onboarding"

    r_acct = client.get("/account")
    assert r_acct.status_code == 200
    assert username.encode() in r_acct.data


def _csrf(client, path: str = "/account"):
    r = client.get(path)
    m = re.search(rb'name="csrf_token" value="([^"]+)"', r.data)
    assert m, "csrf token missing"
    return m.group(1).decode()


if __name__ == "__main__":
    main()
