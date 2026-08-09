"""Workflow Platform — API and Event Bus integration."""

from __future__ import annotations

import json

from flask import abort, jsonify, request, session

from bos.events import subscribe
from bos.workflows import (
    WORKFLOW_STATUSES,
    execution_to_api,
    execute_workflow,
    init_workflow_tables,
    workflow_subscriber,
    workflow_to_api,
)


def register_workflow_platform(app) -> None:
    from app import current_user, db, login_required

    subscribe(workflow_subscriber)

    def user_id():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def active_workspace_id(uid: int) -> int:
        ws_id = session.get("active_workspace_id")
        if ws_id:
            with db() as conn:
                row = conn.execute(
                    """SELECT 1 FROM workspace_members
                       WHERE user_id=? AND workspace_id=? AND status='active'""",
                    (uid, ws_id),
                ).fetchone()
                if row:
                    return int(ws_id)
        with db() as conn:
            row = conn.execute(
                """SELECT w.id FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   WHERE wm.user_id=? AND wm.status='active' ORDER BY w.id LIMIT 1""",
                (uid,),
            ).fetchone()
        if not row:
            abort(404)
        return int(row["id"])

    def _can_access_workspace(conn, uid: int, workspace_id: int) -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM workspace_members WHERE user_id=? AND workspace_id=? AND status='active'",
            (uid, workspace_id),
        ).fetchone())

    @app.get("/api/workflows")
    @login_required
    def api_workflows_list():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        status = request.args.get("status")
        with db() as conn:
            if not _can_access_workspace(conn, uid, ws_id):
                abort(403)
            q = "SELECT * FROM workflows WHERE workspace_id=?"
            params: list = [ws_id]
            if status:
                q += " AND status=?"
                params.append(status)
            q += " ORDER BY name"
            rows = conn.execute(q, params).fetchall()
        return jsonify([workflow_to_api(r) for r in rows])

    @app.get("/api/workflows/templates")
    @login_required
    def api_workflow_templates():
        uid = user_id()
        ws_id = active_workspace_id(uid)
        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM workflows WHERE workspace_id=? AND is_template=1 ORDER BY name",
                (ws_id,),
            ).fetchall()
        return jsonify([workflow_to_api(r) for r in rows])

    @app.post("/api/workflows")
    @login_required
    def api_workflow_create():
        uid = user_id()
        data = request.get_json(silent=True) or {}
        ws_id = int(data.get("workspace_id") or active_workspace_id(uid))
        with db() as conn:
            if not _can_access_workspace(conn, uid, ws_id):
                abort(403)
            cur = conn.execute(
                """INSERT INTO workflows
                   (workspace_id, name, description, status, is_template,
                    trigger_type, trigger_config, conditions, actions, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ws_id,
                    (data.get("name") or "New workflow").strip(),
                    data.get("description") or "",
                    data.get("status") or "draft",
                    1 if data.get("is_template") else 0,
                    data.get("trigger_type") or "manual",
                    json.dumps(data.get("trigger_config") or {}),
                    json.dumps(data.get("conditions") or []),
                    json.dumps(data.get("actions") or []),
                    uid,
                ),
            )
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(workflow_to_api(row)), 201

    @app.get("/api/workflows/<int:workflow_id>")
    @login_required
    def api_workflow_detail(workflow_id):
        uid = user_id()
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row or not _can_access_workspace(conn, uid, row["workspace_id"]):
                abort(404)
        return jsonify(workflow_to_api(row))

    @app.patch("/api/workflows/<int:workflow_id>")
    @login_required
    def api_workflow_update(workflow_id):
        uid = user_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row or not _can_access_workspace(conn, uid, row["workspace_id"]):
                abort(404)
            fields = {
                "name": data.get("name"),
                "description": data.get("description"),
                "status": data.get("status"),
                "trigger_type": data.get("trigger_type"),
                "trigger_config": json.dumps(data["trigger_config"]) if "trigger_config" in data else None,
                "conditions": json.dumps(data["conditions"]) if "conditions" in data else None,
                "actions": json.dumps(data["actions"]) if "actions" in data else None,
            }
            updates = []
            params = []
            for key, val in fields.items():
                if val is not None:
                    updates.append(f"{key}=?")
                    params.append(val)
            if updates:
                from bos.workflows import _now
                updates.append("updated_at=?")
                params.append(_now())
                params.append(workflow_id)
                conn.execute(f"UPDATE workflows SET {', '.join(updates)} WHERE id=?", params)
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return jsonify(workflow_to_api(row))

    @app.post("/api/workflows/<int:workflow_id>/start")
    @login_required
    def api_workflow_start(workflow_id):
        uid = user_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row or not _can_access_workspace(conn, uid, row["workspace_id"]):
                abort(404)
            if row["trigger_type"] not in ("manual", "event"):
                return jsonify({"error": "Workflow is not manually startable"}), 400
            tc = _parse_json(row["trigger_config"], {})
            context = {
                "event_type": "workflow.manual",
                "object_type": data.get("object_type") or tc.get("object_type"),
                "object_id": data.get("object_id"),
                "metadata": data.get("metadata") or {},
                "title": data.get("title") or row["name"],
                "workspace_id": row["workspace_id"],
                "user_id": uid,
                "actor": "owner",
            }
            eid = execute_workflow(
                conn, workflow_id, trigger_type="manual", context=context,
            )
            if not eid:
                return jsonify({"error": "Workflow did not run (inactive or conditions not met)"}), 422
            ex = conn.execute("SELECT * FROM workflow_executions WHERE id=?", (eid,)).fetchone()
        return jsonify(execution_to_api(ex)), 201

    @app.post("/api/workflows/<int:workflow_id>/<action>")
    @login_required
    def api_workflow_lifecycle(workflow_id, action):
        if action not in ("activate", "pause", "archive"):
            abort(404)
        uid = user_id()
        status_map = {"activate": "active", "pause": "paused", "archive": "archived"}
        with db() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row or not _can_access_workspace(conn, uid, row["workspace_id"]):
                abort(404)
            if status_map[action] not in WORKFLOW_STATUSES:
                abort(400)
            from bos.workflows import _now
            conn.execute(
                "UPDATE workflows SET status=?, updated_at=? WHERE id=?",
                (status_map[action], _now(), workflow_id),
            )
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return jsonify(workflow_to_api(row))

    @app.get("/api/workflows/executions")
    @login_required
    def api_workflow_executions():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        limit = min(request.args.get("limit", 50, type=int), 200)
        workflow_id = request.args.get("workflow_id", type=int)
        with db() as conn:
            if not _can_access_workspace(conn, uid, ws_id):
                abort(403)
            q = "SELECT * FROM workflow_executions WHERE workspace_id=?"
            params: list = [ws_id]
            if workflow_id:
                q += " AND workflow_id=?"
                params.append(workflow_id)
            q += " ORDER BY started_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
        return jsonify([execution_to_api(r) for r in rows])

    @app.get("/api/workflows/tasks")
    @login_required
    def api_workflow_tasks():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        with db() as conn:
            if not _can_access_workspace(conn, uid, ws_id):
                abort(403)
            rows = conn.execute(
                """SELECT * FROM workflow_tasks WHERE workspace_id=? AND status='open'
                   ORDER BY created_at DESC LIMIT 100""",
                (ws_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    app.init_workflow_tables = init_workflow_tables
