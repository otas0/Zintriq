"""Execute a snapshot action by node_key + action_key. Clients never pick an action id."""

from __future__ import annotations

import json
from typing import Any

from builder_kernel.events import log_kernel_event
from builder_kernel.ids import new_record_key
from builder_kernel.limits import (
    COMPOSE_MAX_DEPTH,
    COMPOSE_MAX_STEPS,
    PUBLIC_INVOKE_MAX_BYTES,
    PUBLIC_INVOKE_MAX_FIELD_BYTES,
)
from builder_kernel.registry import kernel
from builder_kernel.validate import prepare_record_write

CREATE_IDS = frozenset({"core/create_record", "core/submit_form"})
UPDATE_IDS = frozenset({"core/update_record"})
DELETE_IDS = frozenset({"core/delete_record"})
NAV_IDS = frozenset({"core/open_page", "core/external_link", "core/navigate_to_page"})
SUBMIT_EVENTS = frozenset({"on_submit", "submit"})

# Client may echo these; model/target/action config come only from the snapshot action.
CLIENT_CONTROL_KEYS = frozenset({
    "csrf_token",
    "node_key",
    "action_key",
    "record_key",
    "model_key",
    "target_model",
    "data",
    "document_key",
    "configuration",
    "action_type",
    "action_id",
    "compose",
})

INVOKE_MESSAGES = {
    "not_found": "Not found.",
    "forbidden": "Not allowed.",
    "payload_too_large": "Request is too large.",
    "workflow_unavailable": "Workflows are not available.",
    "action_unavailable": "This action cannot run yet.",
    "unknown_action": "Unknown action.",
    "validation_error": "Some fields are invalid.",
    "adapter_unsupported": "This collection cannot be written.",
    "compose_limit": "This action is too complex to run.",
}


def error_body(code: str, *, fields: list | None = None, message: str | None = None) -> dict:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message or INVOKE_MESSAGES.get(code, INVOKE_MESSAGES["not_found"]),
            "fields": fields or [],
        },
    }


def http_status_for(code: str) -> int:
    return {
        "not_found": 404,
        "forbidden": 403,
        "payload_too_large": 413,
        "workflow_unavailable": 501,
        "action_unavailable": 501,
        "adapter_unsupported": 409,
        "compose_limit": 400,
        "unknown_action": 400,
        "validation_error": 400,
    }.get(code, 400)


def check_public_invoke_size(content_length: int | None, raw: bytes, payload: dict) -> dict | None:
    if content_length is not None and int(content_length) > PUBLIC_INVOKE_MAX_BYTES:
        return error_body("payload_too_large")
    if len(raw) > PUBLIC_INVOKE_MAX_BYTES:
        return error_body("payload_too_large")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data, dict) and _field_bytes(data) > PUBLIC_INVOKE_MAX_FIELD_BYTES:
        return error_body("payload_too_large")
    return None


def _field_bytes(data: dict) -> int:
    total = 0
    for key, value in data.items():
        if str(key) in {"csrf_token", "node_key", "action_key", "record_key"}:
            continue
        total += len(str(key).encode("utf-8"))
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
        else:
            total += len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    return total


def _json_obj(value: Any, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def is_project_member(conn, project: dict, user_id: int | None) -> bool:
    if not user_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=? AND status='active'",
        (int(project["workspace_id"]), int(user_id)),
    ).fetchone()
    return bool(row)


def _model_from_snapshot(snapshot: dict, model_key: str) -> dict | None:
    for item in snapshot.get("data_models") or []:
        if item.get("model_key") == model_key:
            return item
    return None


def _document(snapshot: dict, document_key: str) -> dict | None:
    for item in snapshot.get("documents") or []:
        if (item.get("key") or item.get("document_key")) == document_key:
            return item
    return None


def find_snapshot_action(snapshot: dict, document_key: str, node_key: str, action_key: str) -> dict | None:
    document = _document(snapshot, document_key)
    if not document:
        return None
    document_id = document.get("id")
    for item in snapshot.get("actions") or []:
        if str(item.get("action_key") or "") != str(action_key):
            continue
        if str(item.get("node_key") or "") != str(node_key):
            continue
        if item.get("document_id") not in (None, document_id):
            continue
        return item
    return None


def _access_create_allowed(schema: dict, *, member: bool) -> tuple[str | None, int]:
    adapter_ok, status = None, 200
    if member:
        return None, 200
    access = schema.get("x-access") if isinstance(schema.get("x-access"), dict) else {}
    if access.get("public_create") is True:
        return None, 200
    return "forbidden", 403


def _ensure_native(model: dict) -> str | None:
    adapter = str(model.get("adapter") or "native")
    if adapter != "native":
        return "adapter_unsupported"
    return None


def _run_compose(steps: list, ctx: dict, *, depth: int, counter: list[int]) -> dict | None:
    if depth > COMPOSE_MAX_DEPTH:
        return error_body("compose_limit")
    if not isinstance(steps, list):
        return error_body("compose_limit")
    last = None
    for step in steps:
        counter[0] += 1
        if counter[0] > COMPOSE_MAX_STEPS:
            return error_body("compose_limit")
        if not isinstance(step, dict):
            return error_body("compose_limit")
        nested = step.get("compose")
        if nested:
            last = _run_compose(nested, ctx, depth=depth + 1, counter=counter)
            if last and not last.get("ok"):
                return last
            continue
        step_id = kernel.resolve_action_id(step.get("id") or step.get("action_id"))
        if not step_id:
            return error_body("unknown_action")
        last = _dispatch_action(step_id, ctx)
        if last and not last.get("ok"):
            return last
    return last or {"ok": True}


def _dispatch_action(action_id: str, ctx: dict) -> dict:
    if action_id == "core/start_workflow":
        return error_body("workflow_unavailable")
    spec = kernel.action(action_id) or {}
    compose = spec.get("compose")
    if compose:
        return _run_compose(compose, ctx, depth=1, counter=[0]) or {"ok": True}
    if action_id in NAV_IDS:
        return {"ok": True, "navigate": True}
    handler = spec.get("handler")
    if action_id in CREATE_IDS | UPDATE_IDS | DELETE_IDS:
        return _run_record_action(action_id, ctx)
    if handler is None or getattr(handler, "__name__", "") == "_not_wired":
        return error_body("action_unavailable")
    result = handler(ctx)
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return result if isinstance(result, dict) else {"ok": True}


def _run_record_action(action_id: str, ctx: dict) -> dict:
    conn = ctx["conn"]
    project_id = int(ctx["project_id"])
    model = ctx["model"]
    schema = ctx["schema"]
    payload = ctx.get("record_payload") or {}
    denied = _ensure_native(model)
    if denied:
        return error_body(denied)
    member = bool(ctx.get("member"))
    if action_id in CREATE_IDS:
        code, _status = _access_create_allowed(schema, member=member)
        if code:
            return error_body(code)
        write = prepare_record_write(model.get("adapter") or "native", schema, payload)
        if not write.ok:
            return write.to_dict()
        record_key = new_record_key()
        conn.execute(
            """INSERT INTO builder_data_records(project_id,model_key,record_key,data,status,updated_at)
               VALUES (?,?,?,?,?,datetime('now'))""",
            (project_id, model["model_key"], record_key, json.dumps(payload), "active"),
        )
        log_kernel_event(
            conn,
            project_id=project_id,
            event_id="core/record.created",
            action_id=action_id,
            node_key=ctx.get("node_key") or "",
            action_key=ctx.get("action_key") or "",
            record_key=record_key,
            status="ok",
        )
        return {"ok": True, "record_key": record_key}
    if not member:
        return error_body("forbidden")
    record_key = str(ctx.get("record_key") or "")
    if action_id in UPDATE_IDS:
        if not record_key:
            return error_body("validation_error", fields=[{"path": "record_key", "code": "required"}])
        write = prepare_record_write(model.get("adapter") or "native", schema, payload)
        if not write.ok:
            return write.to_dict()
        row = conn.execute(
            "SELECT id FROM builder_data_records WHERE project_id=? AND model_key=? AND record_key=?",
            (project_id, model["model_key"], record_key),
        ).fetchone()
        if not row:
            return error_body("not_found")
        conn.execute(
            "UPDATE builder_data_records SET data=?,updated_at=datetime('now') WHERE id=?",
            (json.dumps(payload), row["id"]),
        )
        log_kernel_event(
            conn,
            project_id=project_id,
            event_id="core/record.updated",
            action_id=action_id,
            node_key=ctx.get("node_key") or "",
            action_key=ctx.get("action_key") or "",
            record_key=record_key,
            status="ok",
        )
        return {"ok": True, "record_key": record_key}
    if action_id in DELETE_IDS:
        if not record_key:
            return error_body("validation_error", fields=[{"path": "record_key", "code": "required"}])
        row = conn.execute(
            "SELECT id FROM builder_data_records WHERE project_id=? AND model_key=? AND record_key=?",
            (project_id, model["model_key"], record_key),
        ).fetchone()
        if not row:
            return error_body("not_found")
        conn.execute(
            "UPDATE builder_data_records SET status='archived',updated_at=datetime('now') WHERE id=?",
            (row["id"],),
        )
        log_kernel_event(
            conn,
            project_id=project_id,
            event_id="core/record.deleted",
            action_id=action_id,
            node_key=ctx.get("node_key") or "",
            action_key=ctx.get("action_key") or "",
            record_key=record_key,
            status="ok",
        )
        return {"ok": True, "record_key": record_key}
    return error_body("action_unavailable")


def invoke_snapshot_action(
    conn,
    *,
    snapshot: dict,
    project: dict,
    document_key: str,
    body: dict,
    user_id: int | None,
    public: bool,
) -> tuple[int, dict]:
    kernel.ensure_core()
    node_key = str(body.get("node_key") or "")
    action_key = str(body.get("action_key") or "")
    if not node_key or not action_key:
        return http_status_for("not_found"), error_body("not_found")
    action = find_snapshot_action(snapshot, document_key, node_key, action_key)
    if not action:
        return http_status_for("not_found"), error_body("not_found")
    action_id = kernel.resolve_action_id(action.get("action_type"))
    if not action_id:
        return http_status_for("unknown_action"), error_body("unknown_action")
    if action_id == "core/start_workflow":
        log_kernel_event(
            conn,
            project_id=int(project["id"]),
            event_id="core/workflow.rejected",
            action_id=action_id,
            node_key=node_key,
            action_key=action_key,
            status="workflow_unavailable",
        )
        return http_status_for("workflow_unavailable"), error_body("workflow_unavailable")

    configuration = _json_obj(action.get("configuration"), {})
    # Model/target only from server-side action configuration (never client body).
    model_key = str(
        configuration.get("model_key")
        or configuration.get("target_model")
        or ""
    )
    model = _model_from_snapshot(snapshot, model_key) if model_key else None
    schema = _json_obj((model or {}).get("schema"), {}) if model else {}
    member = is_project_member(conn, project, user_id)
    record_payload = body.get("data") if isinstance(body.get("data"), dict) else {}
    if not record_payload and action_id in CREATE_IDS:
        record_payload = {
            key: value
            for key, value in body.items()
            if key not in CLIENT_CONTROL_KEYS
        }
    else:
        record_payload = {
            key: value
            for key, value in (record_payload or {}).items()
            if key not in CLIENT_CONTROL_KEYS
        }
    # Create always mints a server key; update/delete may take record_key from body.
    client_record_key = "" if action_id in CREATE_IDS else str(body.get("record_key") or "")
    ctx = {
        "conn": conn,
        "project_id": int(project["id"]),
        "model": model or {"model_key": model_key, "adapter": "native"},
        "schema": schema,
        "member": member,
        "public": public,
        "record_payload": record_payload,
        "record_key": client_record_key,
        "node_key": node_key,
        "action_key": action_key,
        "configuration": configuration,
    }
    if action_id in CREATE_IDS | UPDATE_IDS | DELETE_IDS:
        if not model:
            return http_status_for("not_found"), error_body("not_found")
    result = _dispatch_action(action_id, ctx)
    if not result.get("ok"):
        code = (result.get("error") or {}).get("code") or "validation_error"
        if code in {"validation_error", "adapter_unsupported", "forbidden"}:
            log_kernel_event(
                conn,
                project_id=int(project["id"]),
                event_id="core/invoke.rejected",
                action_id=action_id,
                node_key=node_key,
                action_key=action_key,
                status=code,
            )
        return http_status_for(code), result
    return 200, result
