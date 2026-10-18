"""Login failure lockout for creator password auth."""

from __future__ import annotations

from datetime import datetime, timedelta

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS login_lockouts (
    key TEXT PRIMARY KEY,
    fail_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);
"""

FAIL_BEFORE_TURNSTILE = 5
LOCK_AFTER = 8
LOCK_MINUTES = 15


def migrate_lockouts(conn) -> None:
    conn.executescript(SCHEMA_SQL)


def _now() -> datetime:
    return datetime.utcnow()


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _key(identifier: str, ip: str) -> str:
    return f"{(identifier or '').strip().lower()}|{ip or ''}"


def lockout_status(conn, identifier: str, ip: str) -> dict:
    migrate_lockouts(conn)
    key = _key(identifier, ip)
    row = conn.execute("SELECT * FROM login_lockouts WHERE key = ?", (key,)).fetchone()
    if not row:
        return {"locked": False, "need_turnstile": False, "fail_count": 0, "minutes": LOCK_MINUTES}
    until = row["locked_until"]
    if until and until > _fmt(_now()):
        return {"locked": True, "need_turnstile": True, "fail_count": row["fail_count"], "minutes": LOCK_MINUTES}
    count = int(row["fail_count"] or 0)
    return {
        "locked": False,
        "need_turnstile": count >= FAIL_BEFORE_TURNSTILE,
        "fail_count": count,
        "minutes": LOCK_MINUTES,
    }


def record_login_failure(conn, identifier: str, ip: str) -> dict:
    migrate_lockouts(conn)
    key = _key(identifier, ip)
    status = lockout_status(conn, identifier, ip)
    count = int(status["fail_count"]) + 1
    locked_until = None
    if count >= LOCK_AFTER:
        locked_until = _fmt(_now() + timedelta(minutes=LOCK_MINUTES))
        count = LOCK_AFTER
    conn.execute(
        """INSERT INTO login_lockouts (key, fail_count, locked_until, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             fail_count = excluded.fail_count,
             locked_until = excluded.locked_until,
             updated_at = excluded.updated_at""",
        (key, count, locked_until, _fmt(_now())),
    )
    return lockout_status(conn, identifier, ip)


def clear_login_failures(conn, identifier: str, ip: str) -> None:
    migrate_lockouts(conn)
    conn.execute("DELETE FROM login_lockouts WHERE key = ?", (_key(identifier, ip),))
