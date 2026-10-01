"""UserProfile — Zintriq identity layer (separate from auth provider)."""

from __future__ import annotations

from datetime import datetime

USER_PROFILE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    auth_provider TEXT NOT NULL DEFAULT 'local',
    auth_provider_id TEXT,
    email TEXT NOT NULL COLLATE NOCASE,
    full_name TEXT DEFAULT '',
    avatar_url TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_provider
    ON user_profiles(auth_provider, auth_provider_id)
    WHERE auth_provider_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_user_profile_tables(conn) -> None:
    conn.executescript(USER_PROFILE_SCHEMA_SQL)


def upsert_user_profile(
    conn,
    user_id: int,
    *,
    auth_provider: str,
    auth_provider_id: str | None,
    email: str,
    full_name: str | None = None,
    avatar_url: str | None = None,
) -> int:
    """Link external auth identity to Zintriq user."""
    email = email.strip().lower()
    existing = conn.execute("SELECT id FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    now = _now()
    if existing:
        conn.execute(
            """UPDATE user_profiles SET auth_provider=?, auth_provider_id=?, email=?,
               full_name=COALESCE(?, full_name), avatar_url=COALESCE(?, avatar_url), updated_at=? WHERE user_id=?""",
            (auth_provider, auth_provider_id, email, full_name, avatar_url, now, user_id),
        )
        return int(existing["id"])
    cur = conn.execute(
        """INSERT INTO user_profiles
           (user_id, auth_provider, auth_provider_id, email, full_name, avatar_url, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, auth_provider, auth_provider_id, email, full_name or "", avatar_url or "", now, now),
    )
    return int(cur.lastrowid)


def get_user_profile(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    return profile_to_api(row) if row else None


def profile_to_api(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "auth_provider": row["auth_provider"],
        "auth_provider_id": row["auth_provider_id"],
        "authProviderId": row["auth_provider_id"],
        "email": row["email"],
        "full_name": row["full_name"] or "",
        "name": row["full_name"] or "",
        "avatar_url": row["avatar_url"] if "avatar_url" in row.keys() else "",
        "avatarUrl": row["avatar_url"] if "avatar_url" in row.keys() else "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def sync_profile_from_user_row(conn, user_row, *, auth_provider: str = "local") -> dict:
    """Ensure profile exists for a users-table row."""
    provider_id = str(user_row["id"]) if auth_provider == "local" else None
    pid = upsert_user_profile(
        conn,
        int(user_row["id"]),
        auth_provider=auth_provider,
        auth_provider_id=provider_id,
        email=user_row["email"],
    )
    row = conn.execute("SELECT * FROM user_profiles WHERE id=?", (pid,)).fetchone()
    return profile_to_api(row)
