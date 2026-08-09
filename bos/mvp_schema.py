"""Business OS MVP database schema — six core tables and migrations."""

from __future__ import annotations

import json

# MVP QR Experience types (spec v1.0)
MVP_QR_TYPES = ("information", "feedback", "survey")

# MVP QR statuses — `paused` is legacy alias for `disabled`
MVP_QR_STATUSES = ("draft", "active", "disabled", "archived")
LEGACY_QR_STATUS_ALIASES = {"paused": "disabled"}

# MVP team roles exposed in product UI
MVP_ROLES = ("owner", "admin", "member")
MVP_ROLE_ALIASES = {
    "administrator": "admin",
    "manager": "member",
    "viewer": "member",
    "staff": "member",
}

# Map legacy QR types to MVP types for API/UI
MVP_QR_TYPE_ALIASES = {
    "menu": "information",
    "product_info": "information",
    "business_card": "information",
    "storefront": "information",
    "information": "information",
    "restaurant": "information",
    "clinic": "information",
    "feedback": "feedback",
    "survey": "survey",
}

MVP_RESPONSE_TYPES = ("feedback", "survey")

RESPONSES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    experience_id INTEGER,
    type TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    legacy_feedback_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_responses_workspace ON responses(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_responses_experience ON responses(experience_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_responses_legacy_feedback
    ON responses(legacy_feedback_id)
    WHERE legacy_feedback_id IS NOT NULL;
"""


def _column_exists(conn, table: str, col: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
    ).fetchone() is not None



def _migrate_user_profiles(conn) -> None:
    if not _column_exists(conn, "user_profiles", "avatar_url"):
        conn.execute("ALTER TABLE user_profiles ADD COLUMN avatar_url TEXT DEFAULT ''")


def _migrate_workspaces(conn) -> None:
    for col, typedef in (
        ("description", "TEXT DEFAULT ''"),
        ("logo_url", "TEXT DEFAULT ''"),
        ("created_by", "INTEGER"),
    ):
        if not _column_exists(conn, "workspaces", col):
            conn.execute(f"ALTER TABLE workspaces ADD COLUMN {col} {typedef}")


def _migrate_qr_experiences(conn) -> None:
    if not _table_exists(conn, "qr_experiences"):
        return
    for col, typedef in (
        ("content", "TEXT DEFAULT '{}'"),
        ("public_url", "TEXT DEFAULT ''"),
    ):
        if not _column_exists(conn, "qr_experiences", col):
            conn.execute(f"ALTER TABLE qr_experiences ADD COLUMN {col} {typedef}")
    rows = conn.execute(
        """SELECT id, experience_config, content FROM qr_experiences
           WHERE (content IS NULL OR content = '' OR content = '{}')"""
    ).fetchall()
    for row in rows:
        cfg = row["experience_config"] or "{}"
        conn.execute("UPDATE qr_experiences SET content=? WHERE id=?", (cfg, row["id"]))


def normalize_qr_status(status: str | None) -> str:
    if not status:
        return "draft"
    return LEGACY_QR_STATUS_ALIASES.get(status, status)


def storage_qr_status(status: str | None) -> str:
    """Map MVP API status to SQLite storage (disabled → paused)."""
    if status == "disabled":
        return "paused"
    return status or "draft"


def accepted_qr_statuses() -> frozenset[str]:
    return frozenset(MVP_QR_STATUSES) | frozenset(LEGACY_QR_STATUS_ALIASES.keys())


def accepted_qr_types() -> frozenset[str]:
    return frozenset(MVP_QR_TYPES) | frozenset(MVP_QR_TYPE_ALIASES.keys())


def resolve_mvp_experience_type(raw_type: str | None, template: dict | None = None) -> str:
    """Map API/template types to MVP storage types: information, feedback, survey."""
    if not raw_type and template:
        raw_type = template.get("type") or template.get("experience_type")
    if not raw_type:
        return "information"
    if raw_type in MVP_QR_TYPES:
        return raw_type
    return MVP_QR_TYPE_ALIASES.get(raw_type, "information")


def normalize_qr_type_for_mvp(qr_type: str | None) -> str:
    if not qr_type:
        return "information"
    return MVP_QR_TYPE_ALIASES.get(qr_type, "information")


def normalize_mvp_role(role: str | None) -> str:
    if not role:
        return "member"
    role = role.strip().lower()
    if role in MVP_ROLES:
        return role
    return MVP_ROLE_ALIASES.get(role, "member")


def experience_content_from_row(row) -> dict:
    raw = row["content"] if "content" in row.keys() and row["content"] else None
    if not raw and "experience_config" in row.keys():
        raw = row["experience_config"]
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def backfill_responses_from_feedback(conn) -> int:
    """Copy legacy feedback_records into unified responses table."""
    from bos.responses import record_response_from_feedback

    rows = conn.execute(
        """SELECT fr.*, (
               SELECT i.experience_id FROM qr_customer_interactions i
               WHERE i.related_object_type='feedback' AND i.related_object_id=fr.id
               ORDER BY i.created_at DESC LIMIT 1
           ) AS experience_id
           FROM feedback_records fr
           WHERE fr.id NOT IN (
               SELECT legacy_feedback_id FROM responses WHERE legacy_feedback_id IS NOT NULL
           )
           ORDER BY fr.id"""
    ).fetchall()
    count = 0
    for row in rows:
        record_response_from_feedback(conn, row, experience_id=row["experience_id"])
        count += 1
    return count


def init_mvp_schema(conn) -> None:
    """Create MVP tables and apply column migrations."""
    conn.executescript(RESPONSES_SCHEMA_SQL)
    _migrate_user_profiles(conn)
    _migrate_workspaces(conn)
    _migrate_qr_experiences(conn)
    backfill_responses_from_feedback(conn)
