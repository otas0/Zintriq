"""Zintriq Workflow Engine — trigger, conditions, actions, execution.

Human spec: docs/bos/WORKFLOW_ENGINE.md
Frontend mirror: static/bos/platform/workflow-engine.js

Workflows connect platforms via the Event Bus. Platforms never hard-code automation.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

WORKFLOW_STATUSES = ("draft", "active", "paused", "archived")
RUN_STATUSES = ("running", "completed", "failed", "cancelled")

TRIGGER_TYPES = (
    "event",           # domain event from event bus
    "manual",          # user-started
    "scheduled",       # future
    "api",             # future
)

ACTION_TYPES = (
    "send_notification",
    "create_task",
    "assign_employee",
    "add_tag",
    "update_status",
    "move_object",
    "generate_document",
    "send_email",      # future
    "call_api",        # future
)

CONDITION_OPS = frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "exists"})

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    is_template INTEGER DEFAULT 0,
    trigger_type TEXT NOT NULL DEFAULT 'event',
    trigger_config TEXT DEFAULT '{}',
    conditions TEXT DEFAULT '[]',
    actions TEXT DEFAULT '[]',
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflows_ws ON workflows(workspace_id, status);

CREATE TABLE IF NOT EXISTS workflow_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    status TEXT DEFAULT 'running',
    trigger_type TEXT NOT NULL,
    trigger_event_id TEXT,
    object_type TEXT,
    object_id INTEGER,
    context TEXT DEFAULT '{}',
    actions_executed TEXT DEFAULT '[]',
    result TEXT DEFAULT '{}',
    error TEXT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_ws ON workflow_executions(workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_wf ON workflow_executions(workflow_id, started_at DESC);

CREATE TABLE IF NOT EXISTS workflow_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    execution_id INTEGER,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    object_type TEXT,
    object_id INTEGER,
    assignee_id INTEGER,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(execution_id) REFERENCES workflow_executions(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_tasks_ws ON workflow_tasks(workspace_id, status);
"""

DEFAULT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "name": "Negative feedback follow-up",
        "description": "When feedback rating is below 3, notify team and create a follow-up task.",
        "status": "active",
        "is_template": 1,
        "trigger_type": "event",
        "trigger_config": {"event_type": "feedback.submitted"},
        "conditions": [{"field": "metadata.rating", "op": "lt", "value": 3}],
        "actions": [
            {"type": "send_notification", "title": "Low rating feedback", "body": "Follow up required", "priority": "warning"},
            {"type": "create_task", "title": "Follow up on negative feedback", "description": "Contact customer about low rating"},
        ],
    },
    {
        "name": "New customer welcome",
        "description": "Welcome workflow when a customer joins the workspace.",
        "status": "active",
        "is_template": 1,
        "trigger_type": "event",
        "trigger_config": {"event_type": "customer.joined"},
        "conditions": [],
        "actions": [
            {"type": "send_notification", "title": "New customer", "body": "Review new customer profile", "priority": "info"},
        ],
    },
    {
        "name": "Customer onboarding",
        "description": "Manual onboarding checklist for new customers.",
        "status": "active",
        "is_template": 1,
        "trigger_type": "manual",
        "trigger_config": {"object_type": "customer"},
        "conditions": [],
        "actions": [
            {"type": "create_task", "title": "Complete customer profile", "description": "Verify contact details and tags"},
            {"type": "create_task", "title": "Send welcome message", "description": "Introduce your business to the customer"},
        ],
    },
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_id() -> str:
    return secrets.token_hex(12)


def init_workflow_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    _seed_default_workflows(conn)


def _seed_workspace_workflows(conn: sqlite3.Connection, ws_id: int) -> None:
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM workflows WHERE workspace_id=?", (ws_id,),
    ).fetchone()["c"]
    if count:
        return
    for tpl in DEFAULT_TEMPLATES:
        conn.execute(
            """INSERT INTO workflows
               (workspace_id, name, description, status, is_template,
                trigger_type, trigger_config, conditions, actions, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ws_id, tpl["name"], tpl["description"], tpl["status"], tpl["is_template"],
                tpl["trigger_type"], json.dumps(tpl["trigger_config"]),
                json.dumps(tpl["conditions"]), json.dumps(tpl["actions"]), _now(),
            ),
        )


def _seed_default_workflows(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id FROM workspaces").fetchall():
        _seed_workspace_workflows(conn, int(row["id"]))


def _parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _get_field(context: dict[str, Any], path: str) -> Any:
    cur: Any = context
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def evaluate_conditions(conditions: list[dict], context: dict[str, Any]) -> bool:
    if not conditions:
        return True
    for rule in conditions:
        field = rule.get("field", "")
        op = rule.get("op", "eq")
        expected = rule.get("value")
        actual = _get_field(context, field)
        if op == "lt" or op == "lte" or op == "gt" or op == "gte":
            try:
                actual = float(actual) if actual is not None else None
                expected = float(expected)
            except (TypeError, ValueError):
                return False
        if op == "eq" and actual != expected:
            return False
        if op == "ne" and actual == expected:
            return False
        if op == "lt" and not (actual is not None and actual < expected):
            return False
        if op == "lte" and not (actual is not None and actual <= expected):
            return False
        if op == "gt" and not (actual is not None and actual > expected):
            return False
        if op == "gte" and not (actual is not None and actual >= expected):
            return False
        if op == "in" and actual not in (expected or []):
            return False
        if op == "contains" and expected not in str(actual or ""):
            return False
        if op == "exists" and (actual is None or actual == ""):
            return False
    return True


def _workspace_member_ids(conn: sqlite3.Connection, workspace_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT user_id FROM workspace_members WHERE workspace_id=? AND status='active'",
        (workspace_id,),
    ).fetchall()
    return [int(r["user_id"]) for r in rows]


def _execute_action(
    conn: sqlite3.Connection,
    action: dict[str, Any],
    *,
    workspace_id: int,
    execution_id: int,
    context: dict[str, Any],
) -> dict[str, Any]:
    atype = action.get("type", "")
    result: dict[str, Any] = {"type": atype, "ok": True}

    if atype == "send_notification":
        title = action.get("title") or "Workflow notification"
        body = action.get("body") or context.get("title") or ""
        priority = action.get("priority") or "info"
        event_id = context.get("event_id") or _run_id()
        members = _workspace_member_ids(conn, workspace_id)
        for uid in members:
            conn.execute(
                """INSERT INTO event_notifications
                   (event_id, user_id, title, body, priority, object_type, object_id, href)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, uid, title, body, priority,
                    context.get("object_type"), context.get("object_id"), context.get("href"),
                ),
            )
        result["notifications"] = len(members)

    elif atype == "create_task":
        from task_platform import create_task_record
        actor_id = context.get("user_id")
        if not actor_id:
            owner = conn.execute(
                """SELECT o.owner_id FROM workspaces w JOIN organizations o ON o.id=w.organization_id
                   WHERE w.id=?""", (workspace_id,),
            ).fetchone()
            actor_id = owner["owner_id"] if owner else None
        if actor_id:
            task_id = create_task_record(
                conn,
                workspace_id=workspace_id,
                title=action.get("title") or "Workflow task",
                created_by=int(actor_id),
                description=action.get("description") or "",
                related_object_type=context.get("object_type"),
                related_object_id=context.get("object_id"),
            )
            result["task_id"] = task_id

    elif atype == "add_tag":
        customer_id = context.get("metadata", {}).get("customer_id") or (
            context.get("object_id") if context.get("object_type") == "customer" else None
        )
        tag_name = action.get("tag_name") or action.get("tag")
        if customer_id and tag_name:
            tag = conn.execute(
                "SELECT id FROM customer_tags WHERE owner_id=(SELECT o.owner_id FROM workspaces w JOIN organizations o ON o.id=w.organization_id WHERE w.id=?) AND name=? LIMIT 1",
                (workspace_id, tag_name),
            ).fetchone()
            if tag:
                conn.execute(
                    "INSERT OR IGNORE INTO customer_tag_links (customer_id, tag_id) VALUES (?, ?)",
                    (int(customer_id), tag["id"]),
                )
                result["tag_id"] = tag["id"]
            else:
                result["ok"] = False
                result["error"] = f"Tag not found: {tag_name}"
        else:
            result["ok"] = False
            result["error"] = "No customer for add_tag"

    elif atype == "update_status":
        obj_type = action.get("object_type") or context.get("object_type")
        obj_id = action.get("object_id") or context.get("object_id")
        new_status = action.get("status")
        table_map = {"customer": "customer_profiles", "feedback": "feedback_records"}
        if obj_type in table_map and obj_id and new_status:
            conn.execute(
                f"UPDATE {table_map[obj_type]} SET status=?, updated_at=? WHERE id=?",
                (new_status, _now(), int(obj_id)),
            )
            result["status"] = new_status
        else:
            result["ok"] = False
            result["error"] = "update_status: unsupported object"

    elif atype in ("assign_employee", "move_object", "generate_document", "send_email", "call_api"):
        result["ok"] = True
        result["deferred"] = True
        result["note"] = f"{atype} registered — execution stub for future integration"

    else:
        result["ok"] = False
        result["error"] = f"Unknown action type: {atype}"

    return result


def execute_workflow(
    conn: sqlite3.Connection,
    workflow_id: int,
    *,
    trigger_type: str,
    context: dict[str, Any],
    trigger_event_id: str | None = None,
) -> int | None:
    """Run a workflow. Returns execution id or None if skipped."""
    row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    if not row or row["status"] != "active":
        return None

    conditions = _parse_json(row["conditions"], [])
    if not evaluate_conditions(conditions, context):
        return None

    workspace_id = int(row["workspace_id"])
    cur = conn.execute(
        """INSERT INTO workflow_executions
           (workflow_id, workspace_id, status, trigger_type, trigger_event_id,
            object_type, object_id, context, started_at)
           VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?)""",
        (
            workflow_id, workspace_id, trigger_type, trigger_event_id,
            context.get("object_type"), context.get("object_id"),
            json.dumps(context), _now(),
        ),
    )
    execution_id = int(cur.lastrowid)
    actions = _parse_json(row["actions"], [])
    executed: list[dict] = []
    error_msg: str | None = None
    final_status = "completed"

    for action in actions:
        try:
            step_result = _execute_action(
                conn, action, workspace_id=workspace_id,
                execution_id=execution_id, context=context,
            )
            executed.append(step_result)
            if not step_result.get("ok", True):
                final_status = "failed"
                error_msg = step_result.get("error") or "Action failed"
                break
        except Exception as exc:
            executed.append({"type": action.get("type"), "ok": False, "error": str(exc)})
            final_status = "failed"
            error_msg = str(exc)
            break

    conn.execute(
        """UPDATE workflow_executions
           SET status=?, actions_executed=?, result=?, error=?, ended_at=?
           WHERE id=?""",
        (final_status, json.dumps(executed), json.dumps({"steps": len(executed)}), error_msg, _now(), execution_id),
    )
    return execution_id


def process_domain_event(conn: sqlite3.Connection, event: Any) -> list[int]:
    """Match active event-triggered workflows and execute. Returns execution ids."""
    if not event.workspace_id:
        return []

    rows = conn.execute(
        """SELECT * FROM workflows
           WHERE workspace_id=? AND status='active' AND trigger_type='event'""",
        (event.workspace_id,),
    ).fetchall()

    context = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    execution_ids: list[int] = []

    for row in rows:
        trigger = _parse_json(row["trigger_config"], {})
        event_type = trigger.get("event_type", "")
        current = context.get("event_type", "")
        if event_type and current != event_type:
            continue
        eid = execute_workflow(
            conn, int(row["id"]),
            trigger_type="event",
            context=context,
            trigger_event_id=context.get("event_id"),
        )
        if eid:
            execution_ids.append(eid)

    return execution_ids


def workflow_subscriber(conn: sqlite3.Connection, event: Any) -> None:
    """Event Bus subscriber — runs matching automatic workflows."""
    try:
        process_domain_event(conn, event)
    except Exception:
        pass  # workflows must not break emit


def workflow_to_api(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "is_template": bool(row["is_template"]),
        "trigger_type": row["trigger_type"],
        "trigger_config": _parse_json(row["trigger_config"], {}),
        "conditions": _parse_json(row["conditions"], []),
        "actions": _parse_json(row["actions"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def execution_to_api(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "workflow_id": row["workflow_id"],
        "workspace_id": row["workspace_id"],
        "status": row["status"],
        "trigger_type": row["trigger_type"],
        "trigger_event_id": row["trigger_event_id"],
        "object_type": row["object_type"],
        "object_id": row["object_id"],
        "context": _parse_json(row["context"], {}),
        "actions_executed": _parse_json(row["actions_executed"], []),
        "result": _parse_json(row["result"], {}),
        "error": row["error"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
    }
