"""Unified Response store — customer submissions from QR Experiences."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from bos.mvp_schema import MVP_RESPONSE_TYPES

_log = logging.getLogger("app.bos")

RESPONSE_SCHEMA_SQL = """
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
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _parse_data(raw: str | None) -> dict:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        _log.debug("response_data_parse_failed", exc_info=True, extra={"op": "_parse_data"})
        return {}


def _response_type_from_feedback(row) -> str:
    ftype = (row["feedback_type"] if "feedback_type" in row.keys() else "") or ""
    source = (row["source_type"] if "source_type" in row.keys() else "") or ""
    if "survey" in ftype or "survey" in source:
        return "survey"
    return "feedback"


def _data_from_feedback(row, *, answers: dict | None = None) -> dict:
    data: dict = {
        "rating": row["rating"] if "rating" in row.keys() else None,
        "comment": (row["comment"] if "comment" in row.keys() else "") or "",
        "customer_name": (row["customer_name"] if "customer_name" in row.keys() else "") or "",
        "customer_email": (row["customer_email"] if "customer_email" in row.keys() else "") or "",
        "customer_id": row["customer_id"] if "customer_id" in row.keys() else None,
        "status": (row["status"] if "status" in row.keys() else "new") or "new",
        "feedback_type": row["feedback_type"] if "feedback_type" in row.keys() else "",
        "source": (row["source"] if "source" in row.keys() else row["source_type"]) if "source_type" in row.keys() else "",
    }
    if answers:
        data["answers"] = answers
    return {k: v for k, v in data.items() if v not in (None, "")}


def record_response(
    conn,
    *,
    workspace_id: int,
    response_type: str,
    data: dict,
    experience_id: int | None = None,
    legacy_feedback_id: int | None = None,
) -> int:
    if response_type not in MVP_RESPONSE_TYPES:
        response_type = "feedback"
    if legacy_feedback_id is not None:
        existing = conn.execute(
            "SELECT id FROM responses WHERE legacy_feedback_id=?", (legacy_feedback_id,),
        ).fetchone()
        if existing:
            return int(existing["id"])
    cur = conn.execute(
        """INSERT INTO responses
           (workspace_id, experience_id, type, data, legacy_feedback_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            workspace_id,
            experience_id,
            response_type,
            json.dumps(data or {}),
            legacy_feedback_id,
            _now(),
        ),
    )
    return int(cur.lastrowid)


def record_response_from_feedback(
    conn,
    feedback_row,
    *,
    experience_id: int | None = None,
    answers: dict | None = None,
) -> int:
    ws = feedback_row["workspace_id"] if "workspace_id" in feedback_row.keys() else None
    if not ws and "store_id" in feedback_row.keys() and feedback_row["store_id"]:
        store = conn.execute(
            "SELECT workspace_id FROM stores WHERE id=?", (feedback_row["store_id"],),
        ).fetchone()
        ws = store["workspace_id"] if store else None
    if not ws:
        return 0
    fid = int(feedback_row["id"])
    return record_response(
        conn,
        workspace_id=int(ws),
        response_type=_response_type_from_feedback(feedback_row),
        data=_data_from_feedback(feedback_row, answers=answers),
        experience_id=experience_id,
        legacy_feedback_id=fid,
    )


def response_to_api(row, conn=None) -> dict:
    data = _parse_data(row["data"])
    payload = {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "experience_id": row["experience_id"],
        "type": row["type"],
        "data": data,
        "rating": data.get("rating"),
        "content": data.get("comment") or "",
        "comment": data.get("comment") or "",
        "customer_name": data.get("customer_name") or "",
        "customer_email": data.get("customer_email") or "",
        "customer_id": data.get("customer_id"),
        "status": data.get("status") or "new",
        "feedback_type": data.get("feedback_type") or row["type"],
        "source": data.get("source") or "",
        "legacy_feedback_id": row["legacy_feedback_id"],
        "created_at": row["created_at"],
        "experience_name": "",
    }
    if conn and row["experience_id"]:
        exp = conn.execute(
            "SELECT name FROM qr_experiences WHERE id=?", (row["experience_id"],),
        ).fetchone()
        if exp:
            payload["experience_name"] = exp["name"]
    elif conn and row["legacy_feedback_id"]:
        src = conn.execute(
            """SELECT x.id, x.name FROM qr_customer_interactions i
               JOIN qr_experiences x ON x.id=i.experience_id
               WHERE i.related_object_type='feedback' AND i.related_object_id=?
               ORDER BY i.created_at DESC LIMIT 1""",
            (row["legacy_feedback_id"],),
        ).fetchone()
        if src:
            payload["experience_id"] = src["id"]
            payload["experience_name"] = src["name"]
    return payload


def list_workspace_responses(
    conn,
    workspace_id: int,
    *,
    response_type: str | None = None,
    experience_id: int | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list:
    query = "SELECT * FROM responses WHERE workspace_id=?"
    params: list = [workspace_id]
    if response_type and response_type in MVP_RESPONSE_TYPES:
        query += " AND type=?"
        params.append(response_type)
    if experience_id:
        query += " AND experience_id=?"
        params.append(experience_id)
    if q:
        query += " AND (data LIKE ? OR CAST(id AS TEXT) LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like])
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_workspace_response(conn, response_id: int, workspace_id: int):
    row = conn.execute(
        "SELECT * FROM responses WHERE id=? AND workspace_id=?",
        (response_id, workspace_id),
    ).fetchone()
    return row
