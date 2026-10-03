"""Kernel invoke event log. Created via init_db / desktop schema stamp."""

from __future__ import annotations

import json

from builder_kernel.limits import KERNEL_EVENTS_MAX_PER_PROJECT

KERNEL_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS builder_kernel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    action_id TEXT NOT NULL DEFAULT '',
    node_key TEXT DEFAULT '',
    action_key TEXT DEFAULT '',
    record_key TEXT DEFAULT '',
    status TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES builder_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_builder_kernel_events_project
    ON builder_kernel_events(project_id, id DESC);
"""


def migrate_kernel_events(conn) -> None:
    conn.executescript(KERNEL_EVENTS_SQL)


def log_kernel_event(
    conn,
    *,
    project_id: int,
    event_id: str,
    action_id: str = "",
    node_key: str = "",
    action_key: str = "",
    record_key: str = "",
    status: str = "ok",
    payload: dict | None = None,
) -> None:
    conn.execute(
        """INSERT INTO builder_kernel_events
           (project_id, event_id, action_id, node_key, action_key, record_key, status, payload)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            int(project_id),
            str(event_id),
            str(action_id or ""),
            str(node_key or ""),
            str(action_key or ""),
            str(record_key or ""),
            str(status),
            json.dumps(payload or {}),
        ),
    )
    prune_kernel_events(conn, int(project_id))


def prune_kernel_events(conn, project_id: int) -> None:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM builder_kernel_events WHERE project_id=?",
        (project_id,),
    ).fetchone()
    count = int(row[0])
    extra = count - KERNEL_EVENTS_MAX_PER_PROJECT
    if extra <= 0:
        return
    conn.execute(
        """DELETE FROM builder_kernel_events WHERE id IN (
             SELECT id FROM builder_kernel_events WHERE project_id=?
             ORDER BY id ASC LIMIT ?
           )""",
        (project_id, extra),
    )
