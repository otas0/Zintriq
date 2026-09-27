"""Immutable draft and published snapshots for QR Experience Builder."""

from __future__ import annotations

import json
import logging
from datetime import datetime

_log = logging.getLogger("app.qr_experience")


REVISION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experience_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    revision_number INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'draft',
    snapshot TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE,
    UNIQUE(experience_id, revision_number)
);
CREATE INDEX IF NOT EXISTS idx_qrx_revision_experience
ON qr_experience_revisions(experience_id, revision_number DESC);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_revision_tables(conn) -> None:
    conn.executescript(REVISION_SCHEMA_SQL)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(qr_experiences)")}
    if "draft_revision_id" not in columns:
        conn.execute("ALTER TABLE qr_experiences ADD COLUMN draft_revision_id INTEGER")
    if "published_revision_id" not in columns:
        conn.execute("ALTER TABLE qr_experiences ADD COLUMN published_revision_id INTEGER")


def capture_snapshot(conn, experience_row) -> dict:
    from qr_experience_builder import list_actions, list_blocks
    from qr_experience_workflow import get_workflow_for_experience, workflow_to_api

    try:
        config = json.loads(experience_row["experience_config"] or "{}")
    except (TypeError, json.JSONDecodeError):
        config = {}
    workflow = get_workflow_for_experience(
        conn, int(experience_row["id"]), int(experience_row["workspace_id"])
    )
    return {
        "schema_version": 1,
        "name": experience_row["name"],
        "type": experience_row["type"],
        "destination": experience_row["destination"] or "",
        "experience_config": config,
        "blocks": list_blocks(conn, int(experience_row["id"])),
        "actions": list_actions(conn, int(experience_row["id"])),
        "workflow": workflow_to_api(workflow) if workflow else None,
    }


def create_revision(
    conn,
    experience_row,
    *,
    kind: str = "draft",
    created_by: int | None = None,
    note: str = "",
) -> dict:
    kind = "published" if kind == "published" else "draft"
    number = int(
        conn.execute(
            "SELECT COALESCE(MAX(revision_number), 0) + 1 AS n FROM qr_experience_revisions WHERE experience_id=?",
            (experience_row["id"],),
        ).fetchone()["n"]
    )
    snapshot = capture_snapshot(conn, experience_row)
    cur = conn.execute(
        """INSERT INTO qr_experience_revisions
           (experience_id, workspace_id, revision_number, kind, snapshot, note, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            experience_row["id"], experience_row["workspace_id"], number, kind,
            json.dumps(snapshot), note.strip(), created_by, _now(),
        ),
    )
    revision_id = int(cur.lastrowid)
    pointer = "published_revision_id" if kind == "published" else "draft_revision_id"
    conn.execute(
        f"UPDATE qr_experiences SET {pointer}=?, updated_at=? WHERE id=?",
        (revision_id, _now(), experience_row["id"]),
    )
    return get_revision(conn, revision_id, int(experience_row["workspace_id"]), include_snapshot=True)


def revision_to_api(row, *, include_snapshot: bool = False) -> dict:
    result = {
        "id": row["id"],
        "experience_id": row["experience_id"],
        "workspace_id": row["workspace_id"],
        "revision_number": row["revision_number"],
        "kind": row["kind"],
        "note": row["note"] or "",
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }
    if include_snapshot:
        try:
            result["snapshot"] = json.loads(row["snapshot"] or "{}")
        except json.JSONDecodeError:
            result["snapshot"] = {}
    return result


def get_revision(conn, revision_id: int, workspace_id: int, *, include_snapshot: bool = False) -> dict:
    row = conn.execute(
        "SELECT * FROM qr_experience_revisions WHERE id=? AND workspace_id=?",
        (revision_id, workspace_id),
    ).fetchone()
    if not row:
        from flask import abort
        abort(404)
    return revision_to_api(row, include_snapshot=include_snapshot)


def list_revisions(conn, experience_id: int, workspace_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM qr_experience_revisions
           WHERE experience_id=? AND workspace_id=? ORDER BY revision_number DESC""",
        (experience_id, workspace_id),
    ).fetchall()
    return [revision_to_api(row) for row in rows]


def published_snapshot(conn, experience_row) -> dict | None:
    revision_id = experience_row["published_revision_id"] if "published_revision_id" in experience_row.keys() else None
    if not revision_id:
        return None
    row = conn.execute(
        "SELECT snapshot FROM qr_experience_revisions WHERE id=? AND experience_id=?",
        (revision_id, experience_row["id"]),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["snapshot"] or "{}")
    except json.JSONDecodeError:
        _log.debug("revision_snapshot_parse_failed", exc_info=True, extra={"op": "published_snapshot"})
        return None


def restore_revision(conn, experience_row, revision_id: int, user_id: int) -> dict:
    from qr_experience_builder import replace_actions, replace_blocks
    from qr_experience_workflow import get_workflow_for_experience, validate_steps

    revision = get_revision(conn, revision_id, int(experience_row["workspace_id"]), include_snapshot=True)
    if int(revision["experience_id"]) != int(experience_row["id"]):
        from flask import abort
        abort(404)
    snapshot = revision.get("snapshot") or {}
    config = snapshot.get("experience_config")
    if not isinstance(config, dict):
        config = {}
    config_json = json.dumps(config)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(qr_experiences)")}
    content_sql = ", content=?" if "content" in columns else ""
    values = [
        snapshot.get("name") or experience_row["name"],
        snapshot.get("type") or experience_row["type"],
        config_json,
    ]
    if content_sql:
        values.append(config_json)
    values.extend([_now(), experience_row["id"], experience_row["workspace_id"]])
    conn.execute(
        f"""UPDATE qr_experiences SET name=?, type=?, experience_config=?{content_sql}, updated_at=?
            WHERE id=? AND workspace_id=?""",
        values,
    )
    replace_blocks(conn, int(experience_row["id"]), snapshot.get("blocks") or [])
    replace_actions(conn, int(experience_row["id"]), snapshot.get("actions") or [])
    workflow = snapshot.get("workflow")
    if isinstance(workflow, dict):
        current = get_workflow_for_experience(conn, int(experience_row["id"]), int(experience_row["workspace_id"]))
        steps = validate_steps(workflow.get("steps") or [])
        if current:
            conn.execute(
                "UPDATE qr_experience_workflows SET name=?, steps=?, updated_at=? WHERE id=?",
                (workflow.get("name") or current["name"], json.dumps(steps), _now(), current["id"]),
            )
    restored = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (experience_row["id"],)).fetchone()
    return create_revision(
        conn, restored, kind="draft", created_by=user_id,
        note=f"Restored from revision {revision['revision_number']}",
    )
