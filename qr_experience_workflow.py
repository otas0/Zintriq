"""QR Experience Workflow Engine — customer journey configuration and execution."""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime

_log = logging.getLogger("app.qr_experience")

WORKFLOW_STATUSES = ("draft", "active", "paused")
WORKFLOW_TRIGGERS = ("qr_scanned",)
STEP_TYPES = (
    "display_content",
    "customer_input",
    "survey",
    "feedback",
    "booking",
    "check_in",
)

WORKFLOW_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experience_workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL UNIQUE,
    workspace_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    trigger_type TEXT NOT NULL DEFAULT 'qr_scanned',
    steps TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qrx_wf_exp ON qr_experience_workflows(experience_id);
CREATE INDEX IF NOT EXISTS idx_qrx_wf_ws ON qr_experience_workflows(workspace_id, status);

CREATE TABLE IF NOT EXISTS qr_experience_workflow_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    workflow_id INTEGER NOT NULL,
    experience_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    current_step_index INTEGER NOT NULL DEFAULT 0,
    step_states TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(workflow_id) REFERENCES qr_experience_workflows(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qrx_wf_prog_sess ON qr_experience_workflow_progress(session_id);
"""

# Preset step sequences keyed by template / experience type
DEFAULT_WORKFLOW_STEPS = {
    "restaurant": [
        {"type": "display_content", "label": "Welcome Page", "config": {"content_type": "header", "title": "Welcome"}},
        {"type": "display_content", "label": "Menu", "config": {"content_type": "info", "title": "Menu"}},
        {"type": "feedback", "label": "Feedback", "config": {}},
        {"type": "display_content", "label": "Thank You", "config": {"content_type": "text", "body": "Thank you for visiting!"}},
    ],
    "event": [
        {"type": "display_content", "label": "Event Information", "config": {"content_type": "info", "title": "Event"}},
        {"type": "check_in", "label": "Check-in", "config": {}},
        {"type": "survey", "label": "Survey", "config": {}},
        {"type": "display_content", "label": "Completion", "config": {"content_type": "text", "body": "You're all set!"}},
    ],
    "service": [
        {"type": "display_content", "label": "Welcome", "config": {"content_type": "header", "title": "Book your visit"}},
        {"type": "booking", "label": "Booking", "config": {}},
        {"type": "check_in", "label": "Check-in", "config": {}},
        {"type": "feedback", "label": "Feedback", "config": {}},
    ],
    "feedback_only": [
        {"type": "display_content", "label": "Welcome", "config": {"content_type": "header", "title": "We value your feedback"}},
        {"type": "feedback", "label": "Feedback", "config": {}},
        {"type": "display_content", "label": "Thank You", "config": {"content_type": "text", "body": "Thank you!"}},
    ],
    "check_in_only": [
        {"type": "display_content", "label": "Welcome", "config": {"content_type": "header", "title": "Check-in"}},
        {"type": "check_in", "label": "Check-in", "config": {}},
    ],
    "default": [
        {"type": "display_content", "label": "Welcome Page", "config": {"content_type": "header", "title": "Welcome"}},
        {"type": "display_content", "label": "Information", "config": {"content_type": "info", "title": "About us"}},
        {"type": "survey", "label": "Customer Action", "config": {}},
        {"type": "display_content", "label": "Thank You", "config": {"content_type": "text", "body": "Thank you!"}},
    ],
}


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _new_step_id() -> str:
    return f"step_{secrets.token_hex(4)}"


def init_workflow_tables(conn) -> None:
    conn.executescript(WORKFLOW_SCHEMA_SQL)


def _parse_steps(raw) -> list[dict]:
    if isinstance(raw, list):
        return raw
    try:
        steps = json.loads(raw or "[]")
        return steps if isinstance(steps, list) else []
    except json.JSONDecodeError:
        _log.debug("workflow_steps_parse_failed", exc_info=True, extra={"op": "parse_steps"})
        return []


def normalize_step(step: dict, index: int = 0) -> dict:
    stype = step.get("type") or "display_content"
    if stype not in STEP_TYPES:
        stype = "display_content"
    return {
        "id": step.get("id") or _new_step_id(),
        "type": stype,
        "label": (step.get("label") or f"Step {index + 1}").strip(),
        "config": step.get("config") if isinstance(step.get("config"), dict) else {},
        "condition": step.get("condition") if isinstance(step.get("condition"), dict) else None,
        "order": int(step.get("order", index)),
    }


def validate_steps(steps: list) -> list[dict]:
    out = []
    for i, s in enumerate(steps or []):
        if not isinstance(s, dict):
            continue
        out.append(normalize_step(s, i))
    out.sort(key=lambda x: x["order"])
    for i, s in enumerate(out):
        s["order"] = i
    return out


def default_steps_for_template(template_id: str | None) -> list[dict]:
    key = (template_id or "default").strip().lower()
    raw = DEFAULT_WORKFLOW_STEPS.get(key) or DEFAULT_WORKFLOW_STEPS["default"]
    return validate_steps([{**s, "id": _new_step_id()} for s in raw])


def workflow_to_api(row) -> dict:
    steps = _parse_steps(row["steps"])
    return {
        "id": row["id"],
        "experience_id": row["experience_id"],
        "workspace_id": row["workspace_id"],
        "name": row["name"],
        "status": row["status"],
        "trigger": row["trigger_type"],
        "trigger_label": "QR Scanned",
        "steps": steps,
        "step_count": len(steps),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_workflow_for_experience(conn, experience_id: int, workspace_id: int | None = None):
    q = "SELECT * FROM qr_experience_workflows WHERE experience_id=?"
    params: list = [experience_id]
    if workspace_id is not None:
        q += " AND workspace_id=?"
        params.append(workspace_id)
    return conn.execute(q, params).fetchone()


def get_workflow(conn, workflow_id: int, workspace_id: int):
    row = conn.execute(
        "SELECT * FROM qr_experience_workflows WHERE id=? AND workspace_id=?",
        (workflow_id, workspace_id),
    ).fetchone()
    if not row:
        from flask import abort
        abort(404)
    return row


def create_default_workflow(conn, experience_id: int, workspace_id: int, name: str, template_id: str | None = None) -> int:
    existing = get_workflow_for_experience(conn, experience_id)
    if existing:
        return int(existing["id"])
    steps = default_steps_for_template(template_id)
    cur = conn.execute(
        """INSERT INTO qr_experience_workflows
           (experience_id, workspace_id, name, status, trigger_type, steps, created_at, updated_at)
           VALUES (?, ?, ?, 'draft', 'qr_scanned', ?, ?, ?)""",
        (experience_id, workspace_id, name or "Customer Workflow", json.dumps(steps), _now(), _now()),
    )
    return int(cur.lastrowid)


def evaluate_condition(condition: dict | None, step_states: dict) -> bool:
    """Simple yes/no and completed/not-completed conditions only."""
    if not condition:
        return True
    when = (condition.get("when") or "always").lower()
    if when == "always":
        return True
    ref = condition.get("step_id")
    state = step_states.get(ref) or {}
    completed = bool(state.get("completed"))
    if when in ("completed", "yes"):
        return completed
    if when in ("not_completed", "no"):
        return not completed
    return True


def visible_steps(steps: list[dict], step_states: dict) -> list[dict]:
    visible = []
    for step in steps:
        if evaluate_condition(step.get("condition"), step_states):
            visible.append(step)
    return visible


def sync_workflow_to_builder(conn, experience_id: int, steps: list[dict], ctx: dict | None = None) -> None:
    """Map workflow steps to landing page blocks and actions."""
    from qr_experience_builder import replace_blocks, replace_actions

    ctx = ctx or {}
    name = ctx.get("name") or "Experience"
    description = ctx.get("description") or ""
    business = ctx.get("business_name") or name

    blocks = []
    actions = []
    order = 0

    for step in steps:
        stype = step["type"]
        cfg = step.get("config") or {}
        label = step.get("label") or ""
        step_key = str(step.get("id") or f"step-{order}")
        block_key = f"blk_step_{step_key}"
        action_key = f"act_step_{step_key}"

        if stype == "display_content":
            ctype = cfg.get("content_type") or "text"
            if ctype == "header":
                blocks.append({
                    "key": block_key,
                    "type": "header",
                    "content": {
                        "title": cfg.get("title") or label or name,
                        "subtitle": cfg.get("subtitle") or business,
                    },
                    "order": order,
                })
            elif ctype == "image":
                blocks.append({
                    "key": block_key,
                    "type": "image",
                    "content": {"src": cfg.get("src") or "", "alt": label},
                    "order": order,
                })
            elif ctype == "info":
                blocks.append({
                    "key": block_key,
                    "type": "info",
                    "content": {
                        "title": cfg.get("title") or label,
                        "body": cfg.get("body") or description,
                    },
                    "order": order,
                })
            else:
                blocks.append({
                    "key": block_key,
                    "type": "text",
                    "content": {"body": cfg.get("body") or label},
                    "order": order,
                })
            order += 1
        elif stype == "customer_input":
            fields = cfg.get("fields") or ["name", "email"]
            blocks.append({
                "key": block_key,
                "type": "info",
                "content": {
                    "title": label or "Your details",
                    "body": ", ".join(fields),
                },
                "order": order,
            })
            order += 1
        elif stype == "survey":
            blocks.append({"key": block_key, "type": "survey", "content": {"title": label or "Survey"}, "order": order})
            actions.append({"key": action_key, "type": "start_survey", "label": label or "Start Survey", "configuration": cfg, "order": len(actions)})
            order += 1
        elif stype == "feedback":
            blocks.append({"key": block_key, "type": "survey", "content": {"title": label or "Feedback"}, "order": order})
            actions.append({"key": action_key, "type": "start_survey", "label": label or "Leave Feedback", "configuration": cfg, "order": len(actions)})
            order += 1
        elif stype == "booking":
            blocks.append({"key": block_key, "type": "booking", "content": {"title": label or "Booking"}, "order": order})
            actions.append({"key": action_key, "type": "create_booking", "label": label or "Book Now", "configuration": cfg, "order": len(actions)})
            order += 1
        elif stype == "check_in":
            blocks.append({"key": block_key, "type": "check_in", "content": {"title": label or "Check-in"}, "order": order})
            actions.append({"key": action_key, "type": "start_checkin", "label": label or "Check-in", "configuration": cfg, "order": len(actions)})
            order += 1

    if actions:
        blocks.append({"key": "blk_workflow_actions", "type": "actions", "content": {"title": "Next steps"}, "order": order})

    replace_blocks(conn, experience_id, blocks)
    replace_actions(conn, experience_id, actions)

    # Update customer_flow metadata on experience
    flow = [{"id": s["id"], "label": s["label"], "type": s["type"]} for s in steps]
    exp = conn.execute("SELECT experience_config FROM qr_experiences WHERE id=?", (experience_id,)).fetchone()
    config = {}
    if exp and exp["experience_config"]:
        try:
            config = json.loads(exp["experience_config"])
        except json.JSONDecodeError:
            config = {}
    config["customer_flow"] = flow
    config["workflow_synced_at"] = _now()
    conn.execute(
        "UPDATE qr_experiences SET experience_config=?, updated_at=? WHERE id=?",
        (json.dumps(config), _now(), experience_id),
    )


def record_workflow_analytics(conn, experience_id: int, session_id: str, event_type: str, metadata: dict | None = None) -> None:
    from qr_experience_analytics import insert_analytics_event
    insert_analytics_event(conn, {
        "experience_id": experience_id,
        "session_id": session_id,
        "event_type": event_type,
        "metadata": metadata or {},
    })


def emit_workflow_activity(conn, event_type: str, workflow_id: int, experience_id: int, workspace_id: int, title: str, metadata: dict | None = None) -> None:
    from bos.events import emit
    from customer_qr_platform import manage_landing_qr_href

    emit(
        conn, event_type, "qr_experience_workflow", workflow_id,
        workspace_id=int(workspace_id), actor="customer",
        title=title,
        metadata={"experience_id": experience_id, **(metadata or {})},
        href=manage_landing_qr_href(conn, experience_id),
    )


def start_workflow_run(conn, workflow_row, session_row, *, from_scan: bool = False, analytics_app=None) -> dict:
    steps = _parse_steps(workflow_row["steps"])
    step_states = {s["id"]: {"completed": False, "data": {}} for s in steps}
    conn.execute(
        """INSERT INTO qr_experience_workflow_progress
           (session_id, workflow_id, experience_id, workspace_id, current_step_index, step_states, status, started_at)
           VALUES (?, ?, ?, ?, 0, ?, 'running', ?)""",
        (
            session_row["session_id"], workflow_row["id"], workflow_row["experience_id"],
            workflow_row["workspace_id"], json.dumps(step_states), _now(),
        ),
    )
    meta = {"workflow_id": workflow_row["id"], "step_count": len(steps)}
    record_workflow_analytics(conn, workflow_row["experience_id"], session_row["session_id"], "workflow_started", meta)
    emit_workflow_activity(
        conn, "qr_experience.workflow_started", int(workflow_row["id"]),
        int(workflow_row["experience_id"]), int(workflow_row["workspace_id"]),
        f"Workflow started: {workflow_row['name']}", meta,
    )
    if from_scan:
        pass  # scan recorded by runtime before workflow start
    return workflow_progress_payload(conn, session_row["session_id"], workflow_row, steps, step_states, 0)


def get_workflow_progress(conn, session_id: str):
    return conn.execute(
        "SELECT * FROM qr_experience_workflow_progress WHERE session_id=?",
        (session_id,),
    ).fetchone()


def workflow_progress_payload(conn, session_id: str, workflow_row, steps: list, step_states: dict, current_index: int) -> dict:
    visible = visible_steps(steps, step_states)
    current = visible[current_index] if current_index < len(visible) else None
    return {
        "workflow_id": workflow_row["id"],
        "session_id": session_id,
        "status": workflow_row["status"],
        "trigger": workflow_row["trigger_type"],
        "steps": steps,
        "visible_steps": visible,
        "current_step_index": current_index,
        "current_step": current,
        "step_states": step_states,
        "advance_api": f"/api/runtime/sessions/{session_id}/workflow/advance",
        "preview_api": f"/api/qr-experiences/{workflow_row['experience_id']}/workflow/preview",
    }


def advance_workflow_step(conn, session_id: str, data: dict | None = None, analytics_app=None) -> dict:
    from flask import abort
    from qr_experience_runtime import complete_session, get_session

    progress = get_workflow_progress(conn, session_id)
    if not progress:
        abort(404)
    if progress["status"] != "running":
        abort(400, description="Workflow is not running")

    workflow_row = conn.execute(
        "SELECT * FROM qr_experience_workflows WHERE id=?", (progress["workflow_id"],)
    ).fetchone()
    if not workflow_row or workflow_row["status"] != "active":
        abort(400, description="Workflow is not active")

    steps = _parse_steps(workflow_row["steps"])
    step_states = json.loads(progress["step_states"] or "{}")
    visible = visible_steps(steps, step_states)
    idx = int(progress["current_step_index"])
    if idx >= len(visible):
        abort(400, description="Workflow already completed")

    current = visible[idx]
    step_states[current["id"]] = {
        "completed": True,
        "data": (data or {}).get("data") or {},
    }
    record_workflow_analytics(
        conn, progress["experience_id"], session_id, "workflow_step_completed",
        {"step_id": current["id"], "step_type": current["type"], "step_label": current["label"]},
    )

    next_index = idx + 1
    if next_index >= len(visible):
        conn.execute(
            """UPDATE qr_experience_workflow_progress
               SET step_states=?, current_step_index=?, status='completed', completed_at=?
               WHERE session_id=?""",
            (json.dumps(step_states), next_index, _now(), session_id),
        )
        record_workflow_analytics(
            conn, progress["experience_id"], session_id, "workflow_completed",
            {"workflow_id": workflow_row["id"]},
        )
        emit_workflow_activity(
            conn, "qr_experience.workflow_completed", int(workflow_row["id"]),
            int(progress["experience_id"]), int(progress["workspace_id"]),
            f"Workflow completed: {workflow_row['name']}",
        )
        session_row = get_session(conn, session_id)
        if session_row:
            complete_session(conn, session_row)
        return workflow_progress_payload(conn, session_id, workflow_row, steps, step_states, next_index) | {"completed": True}

    conn.execute(
        """UPDATE qr_experience_workflow_progress
           SET step_states=?, current_step_index=?
           WHERE session_id=?""",
        (json.dumps(step_states), next_index, session_id),
    )
    return workflow_progress_payload(conn, session_id, workflow_row, steps, step_states, next_index)


def abandon_workflow(conn, session_id: str) -> None:
    progress = get_workflow_progress(conn, session_id)
    if not progress or progress["status"] != "running":
        return
    conn.execute(
        "UPDATE qr_experience_workflow_progress SET status='abandoned', completed_at=? WHERE session_id=?",
        (_now(), session_id),
    )
    record_workflow_analytics(
        conn, progress["experience_id"], session_id, "workflow_abandoned",
        {"workflow_id": progress["workflow_id"]},
    )


def register_qr_experience_workflow(app) -> None:
    from flask import abort, jsonify, request, session
    from app import current_user, db, login_required
    from bos.permissions import has_permission

    def _get_experience(conn, experience_id: int, workspace_id: int):
        row = conn.execute(
            "SELECT * FROM qr_experiences WHERE id=? AND workspace_id=?",
            (experience_id, workspace_id),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def ws_id() -> int | None:
        return session.get("active_workspace_id")

    def _guard(conn, permission: str):
        ws = ws_id()
        if not ws:
            abort(400)
        if has_permission(conn, uid(), int(ws), permission):
            return
        fallback = {
            "workflow.read": "qr_experience.read",
            "workflow.create": "qr_experience.create",
            "workflow.update": "qr_experience.update",
            "workflow.publish": "qr_experience.publish",
            "workflow.delete": "qr_experience.delete",
        }.get(permission)
        if fallback and has_permission(conn, uid(), int(ws), fallback):
            return
        abort(403)

    @app.get("/api/qr-experiences/<int:experience_id>/workflow")
    @login_required
    def api_workflow_get(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "workflow.read")
            _get_experience(conn, experience_id, int(ws))
            row = get_workflow_for_experience(conn, experience_id, int(ws))
            if not row:
                exp = conn.execute("SELECT name, experience_config FROM qr_experiences WHERE id=?", (experience_id,)).fetchone()
                config = json.loads(exp["experience_config"] or "{}") if exp else {}
                wf_id = create_default_workflow(
                    conn, experience_id, int(ws),
                    f"{exp['name']} Workflow" if exp else "Customer Workflow",
                    config.get("template_id"),
                )
                row = conn.execute("SELECT * FROM qr_experience_workflows WHERE id=?", (wf_id,)).fetchone()
            return jsonify(workflow_to_api(row))

    @app.put("/api/qr-experiences/<int:experience_id>/workflow")
    @login_required
    def api_workflow_save(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "workflow.update")
            exp = _get_experience(conn, experience_id, int(ws))
            row = get_workflow_for_experience(conn, experience_id, int(ws))
            steps = validate_steps(data.get("steps") or [])
            name = (data.get("name") or (row["name"] if row else f"{exp['name']} Workflow")).strip()
            if row:
                conn.execute(
                    """UPDATE qr_experience_workflows
                       SET name=?, steps=?, updated_at=?
                       WHERE id=?""",
                    (name, json.dumps(steps), _now(), row["id"]),
                )
                wf_id = int(row["id"])
            else:
                wf_id = create_default_workflow(conn, experience_id, int(ws), name)
                conn.execute(
                    "UPDATE qr_experience_workflows SET steps=?, updated_at=? WHERE id=?",
                    (json.dumps(steps), _now(), wf_id),
                )
            config = json.loads(exp["experience_config"] or "{}")
            sync_workflow_to_builder(conn, experience_id, steps, {
                "name": exp["name"],
                "description": config.get("description") or "",
                "business_name": (config.get("branding") or {}).get("business_name") or exp["name"],
            })
            updated = conn.execute("SELECT * FROM qr_experience_workflows WHERE id=?", (wf_id,)).fetchone()
            return jsonify(workflow_to_api(updated))

    @app.post("/api/qr-experiences/<int:experience_id>/workflow/publish")
    @login_required
    def api_workflow_publish(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "workflow.publish")
            _get_experience(conn, experience_id, int(ws))
            row = get_workflow_for_experience(conn, experience_id, int(ws))
            if not row:
                abort(404, description="No workflow configured")
            steps = _parse_steps(row["steps"])
            if not steps:
                abort(400, description="Workflow must have at least one step")
            conn.execute(
                "UPDATE qr_experience_workflows SET status='active', updated_at=? WHERE id=?",
                (_now(), row["id"]),
            )
            from bos.events import emit
            from customer_qr_platform import manage_landing_qr_href

            emit(
                conn, "qr_experience.workflow_published", "qr_experience_workflow", row["id"],
                workspace_id=int(ws), user_id=uid(), actor="member",
                title=f"Workflow published: {row['name']}",
                href=manage_landing_qr_href(conn, experience_id),
            )
            updated = conn.execute("SELECT * FROM qr_experience_workflows WHERE id=?", (row["id"],)).fetchone()
            return jsonify(workflow_to_api(updated))

    @app.post("/api/qr-experiences/<int:experience_id>/workflow/pause")
    @login_required
    def api_workflow_pause(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "workflow.update")
            _get_experience(conn, experience_id, int(ws))
            row = get_workflow_for_experience(conn, experience_id, int(ws))
            if not row:
                abort(404)
            conn.execute(
                "UPDATE qr_experience_workflows SET status='paused', updated_at=? WHERE id=?",
                (_now(), row["id"]),
            )
            updated = conn.execute("SELECT * FROM qr_experience_workflows WHERE id=?", (row["id"],)).fetchone()
            return jsonify(workflow_to_api(updated))

    @app.get("/api/qr-experiences/<int:experience_id>/workflow/preview")
    @login_required
    def api_workflow_preview(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "workflow.read")
            exp = _get_experience(conn, experience_id, int(ws))
            row = get_workflow_for_experience(conn, experience_id, int(ws))
            if not row:
                abort(404)
            steps = _parse_steps(row["steps"])
            return jsonify({
                "experience": {"id": exp["id"], "name": exp["name"], "status": exp["status"]},
                "workflow": workflow_to_api(row),
                "journey": [{"order": i + 1, **s} for i, s in enumerate(steps)],
            })

    @app.post("/api/runtime/sessions/<session_id>/workflow/advance")
    def runtime_workflow_advance(session_id: str):
        data = request.get_json(silent=True) or {}
        with db() as conn:
            result = advance_workflow_step(conn, session_id, data, analytics_app=app)
        return jsonify(result)

    @app.post("/api/runtime/sessions/<session_id>/workflow/abandon")
    def runtime_workflow_abandon(session_id: str):
        with db() as conn:
            abandon_workflow(conn, session_id)
        return jsonify({"ok": True})
