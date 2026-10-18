"""Trusted creator devices — 90-day cookie after new-device SMS."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from flask import request

COOKIE_NAME = "zintriq_device"
TTL_DAYS = 90

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trusted_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    label TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_trusted_devices_user ON trusted_devices(user_id);
"""


def _now() -> datetime:
    return datetime.utcnow()


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def migrate_trusted_devices(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "session_version" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1")
    if "email_verified_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")
    if "display_name" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT")


def hash_device_token(token: str) -> str:
    secret = (os.environ.get("SECRET_KEY") or "dev").encode()
    return hmac.new(secret, token.encode(), hashlib.sha256).hexdigest()


def cookie_kwargs(app) -> dict:
    return {
        "max_age": TTL_DAYS * 24 * 3600,
        "httponly": True,
        "samesite": app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        "secure": bool(app.config.get("SESSION_COOKIE_SECURE", False)),
        "path": "/",
    }


def find_trusted_device(conn, user_id: int, token: str | None) -> bool:
    if not token:
        return False
    digest = hash_device_token(token)
    row = conn.execute(
        """SELECT id FROM trusted_devices
           WHERE user_id = ? AND token_hash = ? AND expires_at > ?""",
        (int(user_id), digest, _fmt(_now())),
    ).fetchone()
    return bool(row)


def issue_trusted_device(conn, user_id: int, *, label: str = "") -> str:
    token = secrets.token_urlsafe(32)
    expires = _now() + timedelta(days=TTL_DAYS)
    conn.execute(
        """INSERT INTO trusted_devices (user_id, token_hash, label, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (int(user_id), hash_device_token(token), (label or "")[:120], _fmt(_now()), _fmt(expires)),
    )
    return token


def revoke_user_devices(conn, user_id: int) -> None:
    conn.execute("DELETE FROM trusted_devices WHERE user_id = ?", (int(user_id),))


def bump_session_version(conn, user_id: int) -> int:
    conn.execute(
        "UPDATE users SET session_version = COALESCE(session_version, 1) + 1 WHERE id = ?",
        (int(user_id),),
    )
    row = conn.execute("SELECT session_version FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return int(row["session_version"] if row else 1)


def user_agent_label() -> str:
    return (request.user_agent.string or "device")[:80]
