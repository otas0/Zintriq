#!/usr/bin/env python3
"""Verify remember-device session + long-lived customer cookie."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flask import session

from app import app
from session_remember import (
    CUSTOMER_REMEMBER_COOKIE,
    REMEMBER_SESSION_KEY,
    apply_remember_device,
    customer_id_from_remember_token,
    customer_remember_token,
    refresh_session_persistence,
)


def main() -> int:
    with app.test_request_context("/"):
        apply_remember_device(session, True)
        assert session.get(REMEMBER_SESSION_KEY) is True
        session.permanent = False
        refresh_session_persistence(session)
        assert session.permanent is True

    token = customer_remember_token(app.secret_key, 42)
    assert customer_id_from_remember_token(app.secret_key, token) == 42

    client = app.test_client()
    with client.session_transaction() as sess:
        apply_remember_device(sess, True)
        sess["customer_user_id"] = 7

    r = client.get("/home")
    assert r.status_code == 200
    set_cookie = r.headers.get("Set-Cookie") or ""
    assert CUSTOMER_REMEMBER_COOKIE in set_cookie, set_cookie[:120]

    print("verify_session_remember: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
