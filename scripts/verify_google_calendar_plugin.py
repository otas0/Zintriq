#!/usr/bin/env python3
"""Verify Google Calendar plugin integration layer (no live Google API)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bos.integration_crypto import decrypt_token, encrypt_token
from integration_platform import init_integration_tables, get_plugin_by_slug, get_user_connection


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    sys.exit(1)


def main() -> None:
    print("Integration platform verification")
    print("=" * 40)

    # Crypto round-trip
    token = encrypt_token("access-token-xyz", "test-secret-key")
    if decrypt_token(token, "test-secret-key") != "access-token-xyz":
        fail("token encrypt/decrypt")
    ok("token encryption round-trip")

    # Schema + seed
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        init_integration_tables(conn)
        plugin = get_plugin_by_slug(conn, "google_calendar")
        if not plugin:
            fail("google_calendar plugin seed")
        ok("integration_plugins seeded")

        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT
            )"""
        )
        conn.execute(
            """INSERT INTO users (id, email, password_hash) VALUES (1, 'test@example.com', 'x')"""
        )
        conn.execute(
            """INSERT INTO user_integration_connections
               (user_id, plugin_id, external_account_email, access_token_enc, refresh_token_enc, status)
               VALUES (1, ?, 'user@gmail.com', ?, '', 'connected')""",
            (plugin["id"], encrypt_token("tok", "test-secret-key")),
        )
        row = get_user_connection(conn, 1, "google_calendar")
        if not row or row["external_account_email"] != "user@gmail.com":
            fail("user connection isolation")
        ok("per-user connection lookup")

        conn.execute(
            """INSERT INTO calendar_connections (connection_id, google_calendar_id, calendar_name)
               VALUES (?, 'primary', 'My Calendar')""",
            (row["id"],),
        )
        conn.execute(
            """INSERT INTO external_references
               (workspace_id, user_id, object_type, business_object_id, external_provider, external_object_id)
               VALUES (1, 1, 'booking', 99, 'google_calendar', 'evt_abc')"""
        )
        ref = conn.execute(
            "SELECT * FROM external_references WHERE business_object_id=99"
        ).fetchone()
        if ref["external_object_id"] != "evt_abc":
            fail("external_references mapping")
        ok("external reference storage")

    # Flask routes registered
    os.environ.setdefault("SECRET_KEY", "verify-secret")
    from app import app

    rules = {r.rule for r in app.url_map.iter_rules()}
    required = {
        "/api/integrations/plugins",
        "/api/integrations/google-calendar/oauth/start",
        "/api/integrations/google-calendar/oauth/callback",
        "/api/integrations/google-calendar/calendars",
        "/api/integrations/google-calendar/calendar",
        "/api/integrations/google-calendar/disconnect",
        "/api/integrations/google-calendar/status",
    }
    missing = required - rules
    if missing:
        fail(f"missing routes: {missing}")
    ok("Google Calendar API routes registered")

    print("=" * 40)
    print("PASSED")


if __name__ == "__main__":
    main()
