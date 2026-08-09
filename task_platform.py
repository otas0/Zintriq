"""Task Platform — universal execution layer for Business OS."""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timezone
from pathlib import Path

from flask import abort, jsonify, request, session

TASK_STATUSES = ("not_started", "in_progress", "blocked", "completed", "archived")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
RELATED_TYPES = ("customer", "feedback", "order", "catalog", "document", "asset", "event", "store")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    store_id INTEGER,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'not_started',
    priority TEXT DEFAULT 'medium',
    due_date TEXT,
    due_time TEXT,
    related_object_type TEXT,
    related_object_id INTEGER,
    created_by INTEGER NOT NULL,
    updated_by INTEGER,
    archived_by INTEGER,
    completed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(workspace_id, due_date);

CREATE TABLE IF NOT EXISTS task_assignees (
    task_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    assigned_by INTEGER,
    assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id, user_id),
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_task_assignees_user ON task_assignees(user_id);

CREATE TABLE IF NOT EXISTS task_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    parent_id INTEGER,
    body TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(parent_id) REFERENCES task_comments(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id, created_at);

CREATE TABLE IF NOT EXISTS task_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,
    size_bytes INTEGER DEFAULT 0,
    uploaded_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_task_attachments_task ON task_attachments(task_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_task_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    from bos.permissions import init_permissions_tables
    init_permissions_tables(conn)


def create_task_record(
    conn,
    *,
    workspace_id: int,
    title: str,
    created_by: int,
    description: str = "",
    status: str = "not_started",
    priority: str = "medium",
    due_date: str | None = None,
    due_time: str | None = None,
    store_id: int | None = None,
    related_object_type: str | None = None,
    related_object_id: int | None = None,
    assignee_id: int | None = None,
    emit: bool = True,
) -> int:
    """Create a task row — used by API and workflow engine."""
    cur = conn.execute(
        """INSERT INTO tasks
           (workspace_id, store_id, title, description, status, priority, due_date, due_time,
            related_object_type, related_object_id, created_by, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            workspace_id, store_id, title.strip(), description or "", status, priority,
            due_date, due_time, related_object_type, related_object_id,
            created_by, created_by, _now(),
        ),
    )
    task_id = int(cur.lastrowid)
    if assignee_id:
        conn.execute(
            "INSERT OR IGNORE INTO task_assignees (task_id, user_id, assigned_by) VALUES (?, ?, ?)",
            (task_id, assignee_id, created_by),
        )
    if emit:
        _emit_task(conn, "task.created", task_id, workspace_id, created_by, f"Task created: {title}")
        if assignee_id:
            _emit_task(conn, "task.assigned", task_id, workspace_id, created_by,
                       f"Task assigned", metadata={"assignee_id": assignee_id})
    return task_id


def _emit_task(conn, event_type, task_id, workspace_id, user_id, title, **kw):
    from bos.events import emit
    emit(conn, event_type, "task", task_id, workspace_id=workspace_id, user_id=user_id,
         actor="member", title=title, href="/app/operations", **kw)


def _due_bucket(due_date: str | None) -> str | None:
    if not due_date:
        return None
    try:
        d = date.fromisoformat(due_date[:10])
        today = date.today()
        if d < today:
            return "overdue"
        if d == today:
            return "today"
        return "upcoming"
    except ValueError:
        return None


def _related_href(conn, obj_type: str | None, obj_id: int | None) -> str | None:
    if not obj_type or not obj_id:
        return None
    if obj_type in ("customer", "contact"):
        return "/app/contacts"
    if obj_type == "feedback":
        return "/app/feedback"
    if obj_type == "order":
        return "/app/transactions"
    if obj_type == "catalog":
        return "/app/catalog"
    if obj_type == "document":
        return "/app/documents"
    if obj_type == "asset":
        return "/app/assets"
    if obj_type == "store":
        row = conn.execute("SELECT slug FROM stores WHERE id=?", (obj_id,)).fetchone()
        return f"/manage/{row['slug']}" if row else None
    return None


def _related_label(conn, obj_type: str | None, obj_id: int | None) -> str | None:
    if not obj_type or not obj_id:
        return None
    queries = {
        "customer": ("SELECT full_name, email FROM customer_profiles WHERE id=?", lambda r: r["full_name"] or r["email"]),
        "contact": ("SELECT full_name, email FROM customer_profiles WHERE id=?", lambda r: r["full_name"] or r["email"]),
        "feedback": ("SELECT comment FROM feedback_records WHERE id=?", lambda r: (r["comment"] or "")[:40]),
        "order": ("SELECT reference FROM orders WHERE id=?", lambda r: r["reference"]),
        "catalog": ("SELECT name FROM items WHERE id=?", lambda r: r["name"]),
        "store": ("SELECT name FROM stores WHERE id=?", lambda r: r["name"]),
    }
    spec = queries.get(obj_type or "")
    if not spec:
        return f"{obj_type} #{obj_id}"
    sql, fn = spec
    row = conn.execute(sql, (obj_id,)).fetchone()
    return fn(row) if row else None


def _task_to_api(conn, row, viewer_id: int | None = None) -> dict:
    d = dict(row)
    tid = d["id"]
    assignees = conn.execute(
        """SELECT ta.user_id, u.email, u.display_name FROM task_assignees ta
           JOIN users u ON u.id = ta.user_id WHERE ta.task_id=?""",
        (tid,),
    ).fetchall()
    creator = conn.execute(
        "SELECT email, display_name FROM users WHERE id=?", (d["created_by"],),
    ).fetchone()
    comment_count = conn.execute(
        "SELECT COUNT(*) AS c FROM task_comments WHERE task_id=?", (tid,),
    ).fetchone()["c"]
    attach_count = conn.execute(
        "SELECT COUNT(*) AS c FROM task_attachments WHERE task_id=?", (tid,),
    ).fetchone()["c"]
    rel_type = d.get("related_object_type")
    rel_id = d.get("related_object_id")
    return {
        "id": tid,
        "workspace_id": d["workspace_id"],
        "store_id": d.get("store_id"),
        "title": d["title"],
        "description": d.get("description") or "",
        "status": d.get("status") or "not_started",
        "priority": d.get("priority") or "medium",
        "due_date": d.get("due_date"),
        "due_time": d.get("due_time"),
        "due_bucket": _due_bucket(d.get("due_date")),
        "related_object_type": rel_type,
        "related_object_id": rel_id,
        "related_label": _related_label(conn, rel_type, rel_id),
        "related_href": _related_href(conn, rel_type, rel_id),
        "created_by": d["created_by"],
        "created_by_name": (creator["display_name"] or creator["email"]) if creator else None,
        "updated_by": d.get("updated_by"),
        "assignees": [
            {"user_id": a["user_id"], "email": a["email"], "display_name": a["display_name"] or a["email"]}
            for a in assignees
        ],
        "assignee_ids": [a["user_id"] for a in assignees],
        "comment_count": comment_count,
        "attachment_count": attach_count,
        "completed_at": d.get("completed_at"),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
        "is_mine": viewer_id in [a["user_id"] for a in assignees] if viewer_id else False,
    }


def register_task_platform(app) -> None:
    from app import UPLOAD_DIR, current_user, db, login_required
    from bos.permissions import has_permission, member_role, require_permission

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def active_ws_id(user_id: int) -> int:
        ws_id = session.get("active_workspace_id")
        if ws_id:
            with db() as conn:
                if member_role(conn, user_id, int(ws_id)):
                    return int(ws_id)
        with db() as conn:
            row = conn.execute(
                """SELECT workspace_id FROM workspace_members
                   WHERE user_id=? AND status='active' ORDER BY joined_at LIMIT 1""",
                (user_id,),
            ).fetchone()
        if not row:
            abort(404)
        session["active_workspace_id"] = row["workspace_id"]
        return int(row["workspace_id"])

    def ws_param(user_id: int) -> int:
        ws = request.args.get("workspace_id", type=int)
        if not ws:
            body = request.get_json(silent=True) or {}
            ws = body.get("workspace_id")
        return int(ws or active_ws_id(user_id))

    def guard(user_id: int, ws_id: int):
        with db() as conn:
            if not member_role(conn, user_id, ws_id):
                abort(403)

    def get_task(conn, task_id: int, ws_id: int):
        row = conn.execute("SELECT * FROM tasks WHERE id=? AND workspace_id=?", (task_id, ws_id)).fetchone()
        if not row:
            abort(404)
        return row

    @app.get("/api/tasks/context")
    @login_required
    def api_tasks_context():
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            from bos.permissions import permissions_for_role
            role = member_role(conn, user_id, ws_id)
            perms = sorted(permissions_for_role(conn, role or ""))
        return jsonify({"workspace_id": ws_id, "permissions": perms})

    @app.get("/api/tasks/summary")
    @login_required
    def api_tasks_summary():
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.read")
            open_count = conn.execute(
                """SELECT COUNT(*) AS c FROM tasks WHERE workspace_id=?
                   AND status NOT IN ('completed', 'archived')""",
                (ws_id,),
            ).fetchone()["c"]
            mine = conn.execute(
                """SELECT COUNT(*) AS c FROM tasks t
                   JOIN task_assignees ta ON ta.task_id = t.id
                   WHERE t.workspace_id=? AND ta.user_id=? AND t.status NOT IN ('completed', 'archived')""",
                (ws_id, user_id),
            ).fetchone()["c"]
            overdue = conn.execute(
                """SELECT COUNT(*) AS c FROM tasks WHERE workspace_id=?
                   AND status NOT IN ('completed', 'archived') AND due_date < date('now')""",
                (ws_id,),
            ).fetchone()["c"]
        return jsonify({"open": open_count, "mine": mine, "overdue": overdue})

    @app.get("/api/tasks")
    @login_required
    def api_tasks_list():
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        view = request.args.get("view", "all")
        q = request.args.get("q", "").strip().lower()
        status = request.args.get("status", "").strip()
        priority = request.args.get("priority", "").strip()
        assignee_id = request.args.get("assignee_id", type=int)
        created_by = request.args.get("created_by", type=int)
        store_id = request.args.get("store_id", type=int)
        rel_type = request.args.get("related_object_type", "").strip()
        rel_id = request.args.get("related_object_id", type=int)
        due_bucket = request.args.get("due_bucket", "").strip()
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.read")
            sql = "SELECT DISTINCT t.* FROM tasks t"
            joins = []
            params: list = [ws_id]
            if view == "mine":
                joins.append("JOIN task_assignees ta ON ta.task_id = t.id AND ta.user_id = ?")
                params.insert(0, user_id)
            elif view == "assigned_by_me":
                sql += " LEFT JOIN task_assignees ta ON ta.task_id = t.id"
            elif assignee_id:
                joins.append("JOIN task_assignees ta ON ta.task_id = t.id AND ta.user_id = ?")
                params.insert(0, assignee_id)
            if joins:
                sql = "SELECT DISTINCT t.* FROM tasks t " + " ".join(joins)
            sql += " WHERE t.workspace_id=?"
            if view == "completed":
                sql += " AND t.status='completed'"
            elif view == "archived":
                sql += " AND t.status='archived'"
            elif view == "all":
                sql += " AND t.status != 'archived'"
            elif view not in ("mine", "assigned_by_me"):
                sql += " AND t.status NOT IN ('archived')"
            if view == "assigned_by_me":
                sql += " AND t.created_by=? AND EXISTS (SELECT 1 FROM task_assignees x WHERE x.task_id=t.id)"
                params.append(user_id)
            if status and status in TASK_STATUSES:
                sql += " AND t.status=?"
                params.append(status)
            if priority and priority in TASK_PRIORITIES:
                sql += " AND t.priority=?"
                params.append(priority)
            if created_by:
                sql += " AND t.created_by=?"
                params.append(created_by)
            if store_id:
                sql += " AND t.store_id=?"
                params.append(store_id)
            if rel_type:
                sql += " AND t.related_object_type=?"
                params.append(rel_type)
            if rel_id:
                sql += " AND t.related_object_id=?"
                params.append(rel_id)
            if q:
                sql += " AND (LOWER(t.title) LIKE ? OR LOWER(t.description) LIKE ?)"
                params.extend([f"%{q}%", f"%{q}%"])
            if due_bucket == "overdue":
                sql += " AND t.due_date < date('now') AND t.status NOT IN ('completed','archived')"
            elif due_bucket == "today":
                sql += " AND t.due_date = date('now') AND t.status NOT IN ('completed','archived')"
            elif due_bucket == "upcoming":
                sql += " AND t.due_date > date('now') AND t.status NOT IN ('completed','archived')"
            sql += " ORDER BY CASE t.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, t.due_date ASC, t.updated_at DESC"
            rows = conn.execute(sql, params).fetchall()
            return jsonify([_task_to_api(conn, r, user_id) for r in rows])

    @app.post("/api/tasks")
    @login_required
    def api_tasks_create():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        guard(user_id, ws_id)
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Title required"}), 400
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.create")
            task_id = create_task_record(
                conn, workspace_id=ws_id, title=title, created_by=user_id,
                description=data.get("description") or "",
                status=data.get("status") or "not_started",
                priority=data.get("priority") or "medium",
                due_date=data.get("due_date"), due_time=data.get("due_time"),
                store_id=data.get("store_id"),
                related_object_type=data.get("related_object_type"),
                related_object_id=data.get("related_object_id"),
                assignee_id=data.get("assignee_id"),
            )
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return jsonify(_task_to_api(conn, row, user_id)), 201

    @app.get("/api/tasks/<int:task_id>")
    @login_required
    def api_tasks_detail(task_id):
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.read")
            row = get_task(conn, task_id, ws_id)
            activity = conn.execute(
                """SELECT event_type, title, detail, created_at, user_id
                   FROM domain_events WHERE object_type='task' AND object_id=?
                   ORDER BY created_at DESC LIMIT 30""",
                (task_id,),
            ).fetchall()
            payload = _task_to_api(conn, row, user_id)
            payload["activity"] = [dict(a) for a in activity]
        return jsonify(payload)

    @app.patch("/api/tasks/<int:task_id>")
    @login_required
    def api_tasks_update(task_id):
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or ws_param(user_id))
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.update")
            row = get_task(conn, task_id, ws_id)
            fields, params = [], []
            for col in ("title", "description", "status", "priority", "due_date", "due_time", "store_id"):
                if col in data:
                    val = data[col]
                    if col == "status" and val not in TASK_STATUSES:
                        continue
                    if col == "priority" and val not in TASK_PRIORITIES:
                        continue
                    fields.append(f"{col}=?")
                    params.append(val)
            if "related_object_type" in data:
                fields.append("related_object_type=?")
                params.append(data["related_object_type"])
            if "related_object_id" in data:
                fields.append("related_object_id=?")
                params.append(data["related_object_id"])
            if fields:
                fields.extend(["updated_by=?", "updated_at=?"])
                params.extend([user_id, _now(), task_id, ws_id])
                conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=? AND workspace_id=?", params)
                if data.get("status") == "completed":
                    conn.execute(
                        "UPDATE tasks SET completed_at=?, updated_by=? WHERE id=?",
                        (_now(), user_id, task_id),
                    )
                    _emit_task(conn, "task.completed", task_id, ws_id, user_id, f"Task completed: {row['title']}")
                elif "status" in data:
                    _emit_task(conn, "task.updated", task_id, ws_id, user_id,
                               f"Task status → {data['status']}", metadata={"status": data["status"]})
                else:
                    _emit_task(conn, "task.updated", task_id, ws_id, user_id, f"Task updated: {row['title']}")
            if "assignee_id" in data:
                require_permission(conn, user_id, ws_id, "task.assign")
                aid = data["assignee_id"]
                conn.execute("DELETE FROM task_assignees WHERE task_id=?", (task_id,))
                if aid:
                    conn.execute(
                        "INSERT INTO task_assignees (task_id, user_id, assigned_by) VALUES (?, ?, ?)",
                        (task_id, aid, user_id),
                    )
                    _emit_task(conn, "task.assigned", task_id, ws_id, user_id,
                               "Task reassigned", metadata={"assignee_id": aid})
            updated = get_task(conn, task_id, ws_id)
        return jsonify(_task_to_api(conn, updated, user_id))

    @app.post("/api/tasks/<int:task_id>/complete")
    @login_required
    def api_tasks_complete(task_id):
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or ws_param(user_id))
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.complete")
            row = get_task(conn, task_id, ws_id)
            conn.execute(
                "UPDATE tasks SET status='completed', completed_at=?, updated_by=?, updated_at=? WHERE id=?",
                (_now(), user_id, _now(), task_id),
            )
            _emit_task(conn, "task.completed", task_id, ws_id, user_id, f"Task completed: {row['title']}")
        return jsonify({"ok": True})

    @app.post("/api/tasks/<int:task_id>/archive")
    @login_required
    def api_tasks_archive(task_id):
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or ws_param(user_id))
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.archive")
            row = get_task(conn, task_id, ws_id)
            conn.execute(
                "UPDATE tasks SET status='archived', archived_by=?, updated_by=?, updated_at=? WHERE id=?",
                (user_id, user_id, _now(), task_id),
            )
            _emit_task(conn, "task.archived", task_id, ws_id, user_id, f"Task archived: {row['title']}")
        return jsonify({"ok": True})

    @app.delete("/api/tasks/<int:task_id>")
    @login_required
    def api_tasks_delete(task_id):
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.delete")
            row = get_task(conn, task_id, ws_id)
            conn.execute("DELETE FROM task_comments WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM task_attachments WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM task_assignees WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            _emit_task(conn, "task.deleted", task_id, ws_id, user_id, f"Task deleted: {row['title']}")
        return jsonify({"ok": True})

    @app.post("/api/tasks/batch")
    @login_required
    def api_tasks_batch():
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_ws_id(user_id))
        guard(user_id, ws_id)
        action = data.get("action")
        ids = [int(i) for i in (data.get("ids") or [])]
        if not ids:
            return jsonify({"error": "No tasks selected"}), 400
        count = 0
        with db() as conn:
            ph = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT id, title FROM tasks WHERE workspace_id=? AND id IN ({ph})", [ws_id, *ids],
            ).fetchall()
            for row in rows:
                tid = row["id"]
                if action == "complete" and has_permission(conn, user_id, ws_id, "task.complete"):
                    conn.execute(
                        "UPDATE tasks SET status='completed', completed_at=?, updated_by=?, updated_at=? WHERE id=?",
                        (_now(), user_id, _now(), tid),
                    )
                    _emit_task(conn, "task.completed", tid, ws_id, user_id, f"Task completed: {row['title']}")
                    count += 1
                elif action == "archive" and has_permission(conn, user_id, ws_id, "task.archive"):
                    conn.execute(
                        "UPDATE tasks SET status='archived', archived_by=?, updated_by=?, updated_at=? WHERE id=?",
                        (user_id, user_id, _now(), tid),
                    )
                    count += 1
                elif action == "delete" and has_permission(conn, user_id, ws_id, "task.delete"):
                    conn.execute("DELETE FROM task_comments WHERE task_id=?", (tid,))
                    conn.execute("DELETE FROM task_attachments WHERE task_id=?", (tid,))
                    conn.execute("DELETE FROM task_assignees WHERE task_id=?", (tid,))
                    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
                    count += 1
                elif action == "priority" and has_permission(conn, user_id, ws_id, "task.update"):
                    pri = data.get("priority")
                    if pri in TASK_PRIORITIES:
                        conn.execute("UPDATE tasks SET priority=?, updated_by=?, updated_at=? WHERE id=?",
                                     (pri, user_id, _now(), tid))
                        count += 1
                elif action == "assign" and has_permission(conn, user_id, ws_id, "task.assign"):
                    aid = data.get("assignee_id")
                    if aid:
                        conn.execute("DELETE FROM task_assignees WHERE task_id=?", (tid,))
                        conn.execute(
                            "INSERT INTO task_assignees (task_id, user_id, assigned_by) VALUES (?, ?, ?)",
                            (tid, aid, user_id),
                        )
                        count += 1
        return jsonify({"ok": True, "count": count})

    @app.get("/api/tasks/<int:task_id>/comments")
    @login_required
    def api_task_comments_list(task_id):
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.read")
            get_task(conn, task_id, ws_id)
            rows = conn.execute(
                """SELECT tc.*, u.email, u.display_name FROM task_comments tc
                   JOIN users u ON u.id = tc.user_id WHERE tc.task_id=? ORDER BY tc.created_at""",
                (task_id,),
            ).fetchall()
        return jsonify([{
            **dict(r),
            "author_name": r["display_name"] or r["email"],
        } for r in rows])

    @app.post("/api/tasks/<int:task_id>/comments")
    @login_required
    def api_task_comments_create(task_id):
        user_id = uid()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or ws_param(user_id))
        body = (data.get("body") or "").strip()
        if not body:
            return jsonify({"error": "Comment body required"}), 400
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.update")
            row = get_task(conn, task_id, ws_id)
            cur = conn.execute(
                "INSERT INTO task_comments (task_id, user_id, parent_id, body) VALUES (?, ?, ?, ?)",
                (task_id, user_id, data.get("parent_id"), body),
            )
            _emit_task(conn, "task.comment_added", task_id, ws_id, user_id,
                       f"Comment on: {row['title']}", metadata={"comment_id": cur.lastrowid})
            comment = conn.execute(
                """SELECT tc.*, u.email, u.display_name FROM task_comments tc
                   JOIN users u ON u.id = tc.user_id WHERE tc.id=?""",
                (cur.lastrowid,),
            ).fetchone()
        return jsonify({**dict(comment), "author_name": comment["display_name"] or comment["email"]}), 201

    @app.get("/api/tasks/<int:task_id>/attachments")
    @login_required
    def api_task_attachments_list(task_id):
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.read")
            get_task(conn, task_id, ws_id)
            rows = conn.execute(
                "SELECT * FROM task_attachments WHERE task_id=? ORDER BY created_at DESC", (task_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/tasks/<int:task_id>/attachments")
    @login_required
    def api_task_attachments_upload(task_id):
        user_id = uid()
        ws_id = request.form.get("workspace_id", type=int) or active_ws_id(user_id)
        guard(user_id, ws_id)
        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify({"error": "File required"}), 400
        suffix = Path(upload.filename).suffix.lower()
        allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".doc", ".docx", ".txt", ".csv", ".xlsx"}
        if suffix not in allowed:
            return jsonify({"error": "File type not allowed"}), 400
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        stored = f"{secrets.token_hex(8)}{suffix}"
        path = UPLOAD_DIR / stored
        upload.save(path)
        size = path.stat().st_size
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.update")
            get_task(conn, task_id, ws_id)
            cur = conn.execute(
                """INSERT INTO task_attachments (task_id, filename, file_path, file_type, size_bytes, uploaded_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, upload.filename, f"static/uploads/{stored}", upload.content_type or suffix, size, user_id),
            )
            row = conn.execute("SELECT * FROM task_attachments WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201

    @app.delete("/api/tasks/<int:task_id>/attachments/<int:attachment_id>")
    @login_required
    def api_task_attachment_delete(task_id, attachment_id):
        user_id = uid()
        ws_id = ws_param(user_id)
        guard(user_id, ws_id)
        with db() as conn:
            require_permission(conn, user_id, ws_id, "task.update")
            get_task(conn, task_id, ws_id)
            conn.execute(
                "DELETE FROM task_attachments WHERE id=? AND task_id=?", (attachment_id, task_id),
            )
        return jsonify({"ok": True})

    app.init_task_tables = init_task_tables
    app.create_task_record = create_task_record
