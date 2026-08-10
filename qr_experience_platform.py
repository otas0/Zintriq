"""QR Experience Platform — first-class QR-powered customer interaction layer."""

from __future__ import annotations

import json
import secrets
from datetime import datetime

from flask import abort, jsonify, request, session

EXPERIENCE_TYPES = (
    "information",
    "menu",
    "booking",
    "survey",
    "feedback",
    "check_in",
    "event",
    "product",
    "business_card",
)

EXPERIENCE_STATUSES = ("draft", "active", "paused", "archived")

# Map experience type → legacy pass_type used by /qr/<code> router
TYPE_TO_PASS = {
    "information": "experience",
    "menu": "storefront",
    "booking": "booking",
    "survey": "survey",
    "feedback": "feedback",
    "check_in": "check_in",
    "event": "event_pass",
    "product": "product_info",
    "business_card": "business_card",
}

TYPE_LABELS = {
    "information": "Information",
    "feedback": "Feedback",
    "survey": "Survey",
    "menu": "Information",
    "booking": "Booking Experience",
    "survey": "Survey Experience",
    "feedback": "Feedback Experience",
    "check_in": "Check-in Experience",
    "event": "Event Experience",
    "product": "Product Information Experience",
    "business_card": "Business Card Experience",
}

# Starting templates — industry packs that seed customer_flow in experience_config
EXPERIENCE_TEMPLATES = (
    {
        "id": "restaurant",
        "label": "Restaurant Table",
        "description": "Menu → Reservation → Feedback",
        "default_name": "Restaurant Table Experience",
        "type": "menu",
        "customer_flow": [
            {"id": "menu", "label": "Menu", "role": "first"},
            {"id": "booking", "label": "Reservation", "role": "optional"},
            {"id": "feedback", "label": "Feedback", "role": "completion"},
        ],
        "connected": ["booking", "feedback"],
    },
    {
        "id": "event",
        "label": "Event",
        "description": "Event info → Check-in → Survey",
        "default_name": "Event Experience",
        "type": "event",
        "customer_flow": [
            {"id": "info", "label": "Information", "role": "first"},
            {"id": "check_in", "label": "Check-in", "role": "optional"},
            {"id": "survey", "label": "Survey", "role": "completion"},
        ],
        "connected": ["checkin", "feedback"],
    },
    {
        "id": "product",
        "label": "Product Information",
        "description": "Product page → Information → Feedback",
        "default_name": "Product Information Experience",
        "type": "product",
        "customer_flow": [
            {"id": "product", "label": "Product Information", "role": "first"},
            {"id": "feedback", "label": "Feedback", "role": "completion"},
        ],
        "connected": ["feedback"],
    },
    {
        "id": "service",
        "label": "Service",
        "description": "Booking, arrival check-in, and feedback",
        "default_name": "Service QR",
        "type": "booking",
        "customer_flow": [
            {"id": "booking", "label": "Booking", "role": "first"},
            {"id": "check_in", "label": "Check-in", "role": "optional"},
            {"id": "feedback", "label": "Feedback", "role": "completion"},
        ],
        "connected": ["booking", "checkin", "feedback"],
    },
    {
        "id": "feedback_only",
        "label": "Feedback",
        "description": "Survey → Submit feedback",
        "default_name": "Feedback Experience",
        "type": "feedback",
        "customer_flow": [
            {"id": "feedback", "label": "Feedback", "role": "first"},
            {"id": "survey", "label": "Survey", "role": "completion"},
        ],
        "connected": ["feedback"],
    },
    {
        "id": "check_in_only",
        "label": "Check-in",
        "description": "Verification → Check-in complete",
        "default_name": "Check-in Experience",
        "type": "check_in",
        "customer_flow": [
            {"id": "check_in", "label": "Check-in", "role": "first"},
        ],
        "connected": ["checkin"],
    },
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    store_id INTEGER,
    qr_code_id INTEGER,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'menu',
    status TEXT NOT NULL DEFAULT 'draft',
    experience_config TEXT DEFAULT '{}',
    destination TEXT DEFAULT '',
    analytics_config TEXT DEFAULT '{}',
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(qr_code_id) REFERENCES qr_codes(id)
);
CREATE INDEX IF NOT EXISTS idx_qr_exp_workspace ON qr_experiences(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_qr_exp_type ON qr_experiences(workspace_id, type);

CREATE TABLE IF NOT EXISTS qr_experience_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    visitor_key TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qr_exp_events ON qr_experience_events(experience_id, event_type);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10].lower()


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _migrate_qr_codes(conn) -> None:
    for col, typedef in (
        ("pass_type", "TEXT DEFAULT 'storefront'"),
        ("ref_id", "INTEGER"),
        ("status", "TEXT DEFAULT 'active'"),
        ("workspace_id", "INTEGER"),
        ("experience_id", "INTEGER"),
        ("updated_at", "TEXT"),
    ):
        if not _column_exists(conn, "qr_codes", col):
            conn.execute(f"ALTER TABLE qr_codes ADD COLUMN {col} {typedef}")


def init_qr_experience_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _migrate_qr_codes(conn)
    from qr_experience_builder import init_builder_tables
    init_builder_tables(conn)
    from qr_experience_runtime import init_runtime_tables
    init_runtime_tables(conn)
    from qr_experience_analytics import init_analytics_tables
    init_analytics_tables(conn)
    from qr_experience_templates import init_template_tables
    init_template_tables(conn)
    from qr_experience_workflow import init_workflow_tables
    init_workflow_tables(conn)
    from qr_customer_data import init_qr_customer_tables
    init_qr_customer_tables(conn)


def register_qr_experience_platform(app) -> None:
    from app import current_user, db, login_required
    from bos.permissions import has_permission

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
        # Prefer qr_experience.* permissions; fall back to workspace.* for older role rows
        if has_permission(conn, uid(), int(ws), permission):
            return
        fallback = {
            "qr_experience.read": "workspace.read",
            "qr_experience.create": "workspace.update",
            "qr_experience.update": "workspace.update",
            "qr_experience.publish": "workspace.update",
            "qr_experience.delete": "workspace.update",
            "template.read": "qr_experience.read",
            "template.create": "qr_experience.create",
            "template.manage": "qr_experience.update",
            "workflow.read": "qr_experience.read",
            "workflow.create": "qr_experience.create",
            "workflow.update": "qr_experience.update",
            "workflow.publish": "qr_experience.publish",
            "workflow.delete": "qr_experience.delete",
        }.get(permission)
        if fallback and has_permission(conn, uid(), int(ws), fallback):
            return
        abort(403)

    def _store_for_workspace(conn, workspace_id: int):
        return conn.execute(
            "SELECT id, slug, name FROM stores WHERE workspace_id=? ORDER BY id LIMIT 1",
            (workspace_id,),
        ).fetchone()

    def _ensure_store_for_workspace(conn, workspace_id: int, user_id: int):
        from bos.workspace_store import ensure_workspace_store
        return ensure_workspace_store(conn, workspace_id, user_id)

    def _qr_code_to_api(conn, qr_row, exp_row) -> dict:
        from app import public_url_for, qr_data_uri

        code = qr_row["code"]
        slug_val = exp_row["public_slug"] if "public_slug" in exp_row.keys() and exp_row["public_slug"] else None
        landing = f"/e/{slug_val}" if slug_val else (f"/e/{code}" if code else "")
        abs_url = public_url_for("qr_entry", code=code) if code else None
        status = qr_row["status"] if "status" in qr_row.keys() else "draft"
        if status == "paused":
            status = "disabled"
        return {
            "id": qr_row["id"],
            "experience_id": (qr_row["experience_id"] if "experience_id" in qr_row.keys() else None) or exp_row["id"],
            "name": qr_row["name"],
            "code": code,
            "url": landing,
            "absolute_url": abs_url,
            "status": status or "draft",
            "qr_image": qr_data_uri(abs_url) if abs_url else None,
            "created_at": qr_row["created_at"] if "created_at" in qr_row.keys() else (qr_row["updated_at"] if "updated_at" in qr_row.keys() else None),
            "is_primary": qr_row["id"] == exp_row["qr_code_id"],
        }

    def _list_experience_qr_codes(conn, exp_row) -> list[dict]:
        eid = exp_row["id"]
        primary_id = exp_row["qr_code_id"] or 0
        rows = conn.execute(
            """SELECT * FROM qr_codes
               WHERE experience_id=? OR id=?
               ORDER BY id""",
            (eid, primary_id),
        ).fetchall()
        seen: set[int] = set()
        result = []
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            result.append(_qr_code_to_api(conn, r, exp_row))
        return result

    def _analytics(conn, experience_id: int) -> dict:
        from qr_experience_analytics import experience_analytics_summary
        s = experience_analytics_summary(conn, experience_id, "all")
        return {
            "scan_count": s["total_scans"],
            "unique_visitors": s["unique_visitors"],
            "completed_actions": s["completed_actions"],
            "conversion_rate": s["conversion_rate"],
        }

    def experience_to_api(conn, row) -> dict:
        from app import public_url_for, qr_data_uri

        from bos.mvp_schema import (
            accepted_qr_statuses,
            accepted_qr_types,
            experience_content_from_row,
            normalize_qr_status,
            normalize_qr_type_for_mvp,
            storage_qr_status,
        )

        config = experience_content_from_row(row)
        analytics_cfg = {}
        try:
            analytics_cfg = json.loads(row["analytics_config"] or "{}")
        except (TypeError, json.JSONDecodeError):
            pass
        qr = None
        if row["qr_code_id"]:
            qr = conn.execute("SELECT * FROM qr_codes WHERE id=?", (row["qr_code_id"],)).fetchone()
        analytics = _analytics(conn, row["id"])
        response_count = conn.execute(
            "SELECT COUNT(*) AS c FROM responses WHERE experience_id=?", (row["id"],),
        ).fetchone()["c"]
        if not response_count:
            response_count = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_customer_interactions
                   WHERE experience_id=? AND interaction_type IN ('feedback_submitted', 'survey_completed')""",
                (row["id"],),
            ).fetchone()["c"]
        analytics["response_count"] = int(response_count or analytics.get("completed_actions") or 0)
        code = qr["code"] if qr else None
        scan_path = f"/qr/{code}" if code else None
        absolute = public_url_for("qr_entry", code=code) if code else None
        from qr_experience_builder import enrich_actions_with_hrefs, list_actions, list_blocks

        flow = config.get("customer_flow") or []
        branding = config.get("branding") or {}
        slug_val = row["public_slug"] if "public_slug" in row.keys() and row["public_slug"] else None
        landing_path = f"/e/{slug_val}" if slug_val else (f"/e/{code}" if code else None)
        store = None
        if row["store_id"]:
            store = conn.execute("SELECT * FROM stores WHERE id=?", (row["store_id"],)).fetchone()
        actions = enrich_actions_with_hrefs(
            conn, list_actions(conn, row["id"]), store, row["workspace_id"],
        )
        tpl_id = config.get("template_id")
        tpl_meta = None
        if tpl_id:
            from qr_experience_templates import get_template
            tpl_meta = get_template(conn, tpl_id)
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "store_id": row["store_id"],
            "qr_code_id": row["qr_code_id"],
            "name": row["name"],
            "type": row["type"],
            "mvp_type": normalize_qr_type_for_mvp(row["type"]),
            "type_label": TYPE_LABELS.get(normalize_qr_type_for_mvp(row["type"]), TYPE_LABELS.get(row["type"], row["type"])),
            "status": normalize_qr_status(row["status"]),
            "description": config.get("description") or "",
            "content": config,
            "template_id": tpl_id,
            "template_version": config.get("template_version"),
            "template_name": (tpl_meta or {}).get("name") or tpl_id,
            "template_category": (tpl_meta or {}).get("category") or "",
            "enabled_actions": config.get("enabled_actions") or {},
            "customer_flow": flow,
            "branding": branding,
            "experience_config": config,
            "destination": row["destination"] or landing_path or "",
            "analytics_config": analytics_cfg,
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "code": code,
            "scan_url": scan_path,
            "public_slug": slug_val,
            "landing_url": landing_path,
            "public_url": landing_path,
            "absolute_url": absolute,
            "qr_image": qr_data_uri(absolute) if absolute else None,
            "pass_type": (qr["pass_type"] if qr and "pass_type" in qr.keys() else None)
            or TYPE_TO_PASS.get(row["type"], "experience"),
            "connected_features": config.get("connected") or [],
            "analytics": analytics,
            "blocks": list_blocks(conn, row["id"]),
            "actions": actions,
            "qr_codes": _list_experience_qr_codes(conn, row),
            "workflow": _workflow_summary(conn, row["id"], row["workspace_id"]),
        }

    def _workflow_summary(conn, experience_id: int, workspace_id: int) -> dict | None:
        from qr_experience_workflow import get_workflow_for_experience, workflow_to_api
        wf = get_workflow_for_experience(conn, experience_id, workspace_id)
        if not wf:
            return None
        api = workflow_to_api(wf)
        return {
            "id": api["id"],
            "name": api["name"],
            "status": api["status"],
            "trigger": api["trigger"],
            "step_count": api["step_count"],
        }

    def get_experience(conn, experience_id: int, workspace_id: int):
        row = conn.execute(
            "SELECT * FROM qr_experiences WHERE id=? AND workspace_id=?",
            (experience_id, workspace_id),
        ).fetchone()
        if not row:
            abort(404)
        return row

    @app.get("/api/qr-experiences/types")
    @login_required
    def api_qr_experience_types():
        return jsonify([
            {"id": t, "label": TYPE_LABELS[t], "pass_type": TYPE_TO_PASS[t]}
            for t in EXPERIENCE_TYPES
        ])

    @app.get("/api/qr-experiences/templates")
    @login_required
    def api_qr_experience_templates():
        from qr_experience_templates import list_templates
        with db() as conn:
            _guard(conn, "template.read")
            return jsonify(list_templates(conn))

    @app.get("/api/qr-experiences")
    @app.get("/api/experiences")
    @login_required
    def api_qr_experiences_list():
        ws = ws_id()
        if not ws:
            return jsonify([])
        status = request.args.get("status", "")
        exp_type = request.args.get("type", "")
        q = request.args.get("q", "").strip()
        with db() as conn:
            _guard(conn, "qr_experience.read")
            query = "SELECT * FROM qr_experiences WHERE workspace_id=?"
            params: list = [ws]
            if status:
                query += " AND status=?"
                params.append(status)
            if exp_type:
                query += " AND type=?"
                params.append(exp_type)
            store_id = request.args.get("store_id", "").strip()
            if store_id.isdigit():
                query += " AND store_id=?"
                params.append(int(store_id))
            if q:
                query += " AND name LIKE ?"
                params.append(f"%{q}%")
            query += " ORDER BY updated_at DESC, id DESC LIMIT 500"
            rows = conn.execute(query, params).fetchall()
            return jsonify([experience_to_api(conn, r) for r in rows])

    @app.get("/api/qr-experiences/summary")
    @login_required
    def api_qr_experiences_summary():
        ws = ws_id()
        if not ws:
            return jsonify({"total": 0, "active": 0, "scans": 0, "by_type": []})
        with db() as conn:
            _guard(conn, "qr_experience.read")
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM qr_experiences WHERE workspace_id=? AND status!='archived'",
                (ws,),
            ).fetchone()["c"]
            active = conn.execute(
                "SELECT COUNT(*) AS c FROM qr_experiences WHERE workspace_id=? AND status='active'",
                (ws,),
            ).fetchone()["c"]
            scans = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_events e
                   JOIN qr_experiences x ON x.id=e.experience_id
                   WHERE x.workspace_id=? AND e.event_type IN ('scan', 'view')""",
                (ws,),
            ).fetchone()["c"]
            responses = conn.execute(
                "SELECT COUNT(*) AS c FROM feedback_records WHERE workspace_id=?",
                (ws,),
            ).fetchone()["c"]
            by_type = conn.execute(
                """SELECT type, COUNT(*) AS c FROM qr_experiences
                   WHERE workspace_id=? AND status!='archived' GROUP BY type ORDER BY c DESC""",
                (ws,),
            ).fetchall()
        return jsonify({
            "total": int(total or 0),
            "active": int(active or 0),
            "scans": int(scans or 0),
            "responses": int(responses or 0),
            "by_type": [dict(r) for r in by_type],
        })

    @app.post("/api/qr-experiences")
    @app.post("/api/experiences")
    @login_required
    def api_qr_experiences_create():
        from bos.mvp_schema import accepted_qr_types, resolve_mvp_experience_type

        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        template_id = data.get("template_id")
        template = None
        if template_id:
            from qr_experience_templates import get_template
            with db() as conn:
                template = get_template(conn, template_id)
        if not template and template_id:
            template = next((t for t in EXPERIENCE_TEMPLATES if t["id"] == template_id), None)
            if template:
                template = {
                    "id": template["id"],
                    "name": template.get("label"),
                    "label": template.get("label"),
                    "type": template["type"],
                    "experience_type": template["type"],
                    "version": 1,
                    "default_name": template.get("default_name"),
                    "description": template.get("description"),
                    "customer_flow": template.get("customer_flow"),
                    "connected": template.get("connected"),
                }
        exp_type = resolve_mvp_experience_type(data.get("type"), template)
        name = (data.get("name") or "").strip() or (template.get("default_name") if template else "")
        if not name:
            return jsonify({"error": "Name required"}), 400
        if exp_type not in accepted_qr_types():
            return jsonify({"error": "Invalid type. MVP types: information, feedback, survey"}), 400
        with db() as conn:
            _guard(conn, "qr_experience.create")
            if data.get("store_id"):
                store = conn.execute(
                    "SELECT * FROM stores WHERE id=? AND (workspace_id=? OR owner_id=?)",
                    (int(data["store_id"]), int(ws), uid()),
                ).fetchone()
                if not store:
                    return jsonify({"error": "Store not found."}), 404
            else:
                store = _ensure_store_for_workspace(conn, int(ws), uid())
            config = data.get("experience_config") or {}
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    config = {}
            if template:
                config.setdefault("template_id", template["id"])
                config.setdefault("template_version", template.get("version") or 1)
                config.setdefault("customer_flow", template.get("customer_flow"))
                config.setdefault("connected", template.get("connected"))
                config.setdefault("description", template.get("description"))
                config.setdefault("enabled_actions", template.get("enabled_actions") or {})
            if data.get("description"):
                config["description"] = str(data["description"]).strip()
            if data.get("customer_flow"):
                config["customer_flow"] = data["customer_flow"]
            branding = config.get("branding") or {}
            if data.get("branding"):
                branding = {**branding, **(data["branding"] or {})}
            from bos.workspace_store import workspace_identity
            identity = workspace_identity(conn, int(ws))
            branding.setdefault("business_name", identity["business_name"])
            branding.setdefault("logo_url", identity.get("logo_url") or "")
            config["branding"] = branding
            ref_id = data.get("ref_id") or config.get("ref_id")
            pass_type = "experience"  # landing page first; legacy types remain for linked destinations
            if exp_type in TYPE_TO_PASS and not template:
                pass_type = TYPE_TO_PASS[exp_type]
            if template:
                pass_type = "experience"
            code = _code()
            while conn.execute("SELECT 1 FROM qr_codes WHERE code=?", (code,)).fetchone():
                code = _code()
            qcur = conn.execute(
                """INSERT INTO qr_codes
                   (store_id, name, code, pass_type, ref_id, status, workspace_id, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)""",
                (store["id"], name, code, pass_type, ref_id, ws, _now()),
            )
            qr_id = int(qcur.lastrowid)
            destination = f"/e/{code}"  # slug assigned on publish
            config_json = json.dumps(config)
            content_cols = ", content" if _column_exists(conn, "qr_experiences", "content") else ""
            content_vals = ", ?" if content_cols else ""
            cur = conn.execute(
                f"""INSERT INTO qr_experiences
                   (workspace_id, store_id, qr_code_id, name, type, status,
                    experience_config, destination, created_by, updated_at{content_cols})
                   VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?{content_vals})""",
                (
                    ws, store["id"], qr_id, name, exp_type,
                    config_json, destination, uid(), _now(),
                    *([config_json] if content_cols else []),
                ),
            )
            eid = int(cur.lastrowid)
            if _column_exists(conn, "qr_codes", "experience_id"):
                conn.execute("UPDATE qr_codes SET experience_id=? WHERE id=?", (eid, qr_id))
            from qr_experience_builder import seed_template_builder
            tid = config.get("template_id") or (template["id"] if template else "feedback_only")
            seed_template_builder(conn, eid, tid, {
                "name": name,
                "description": config.get("description") or "",
                "business_name": branding.get("business_name") or store["name"],
            })
            from qr_experience_workflow import create_default_workflow, sync_workflow_to_builder, get_workflow_for_experience, workflow_to_api
            create_default_workflow(conn, eid, int(ws), f"{name} Workflow", config.get("template_id") or tid)
            wf = get_workflow_for_experience(conn, eid)
            if wf:
                sync_workflow_to_builder(conn, eid, workflow_to_api(wf)["steps"], {
                    "name": name,
                    "description": config.get("description") or "",
                    "business_name": branding.get("business_name") or store["name"],
                })
            from bos.events import emit
            from customer_qr_platform import manage_landing_qr_href

            emit(
                conn, "qr_experience.created", "qr_experience", eid,
                workspace_id=int(ws), user_id=uid(), actor="member",
                title=f"Landing page created: {name}",
                href=manage_landing_qr_href(conn, eid, builder=True),
            )
            row = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (eid,)).fetchone()
            return jsonify(experience_to_api(conn, row)), 201

    @app.get("/api/qr-experiences/<int:experience_id>")
    @app.get("/api/experiences/<int:experience_id>")
    @login_required
    def api_qr_experience_detail(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.read")
            row = get_experience(conn, experience_id, int(ws))
            payload = experience_to_api(conn, row)
            payload["recent_events"] = [
                dict(e) for e in conn.execute(
                    """SELECT event_type, visitor_key, created_at FROM qr_experience_events
                       WHERE experience_id=? ORDER BY created_at DESC LIMIT 30""",
                    (experience_id,),
                ).fetchall()
            ]
            return jsonify(payload)

    @app.get("/api/qr-experiences/<int:experience_id>/responses")
    @login_required
    def api_qr_experience_responses(experience_id):
        ws = ws_id()
        if not ws:
            return jsonify([])
        with db() as conn:
            _guard(conn, "feedback.read")
            get_experience(conn, experience_id, int(ws))
            from bos.responses import list_workspace_responses, response_to_api
            rows = list_workspace_responses(conn, int(ws), experience_id=experience_id, limit=100)
            return jsonify([response_to_api(r, conn) for r in rows])

    @app.patch("/api/qr-experiences/<int:experience_id>")
    @login_required
    def api_qr_experience_update(experience_id):
        from bos.mvp_schema import accepted_qr_statuses, accepted_qr_types, storage_qr_status

        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "qr_experience.update")
            before = get_experience(conn, experience_id, int(ws))
            updates, params = [], []
            if "name" in data and str(data["name"]).strip():
                updates.append("name=?")
                params.append(str(data["name"]).strip())
            if "type" in data:
                exp_type = data["type"]
                if exp_type in accepted_qr_types() or exp_type in EXPERIENCE_TYPES:
                    updates.append("type=?")
                    params.append(exp_type)
            if "status" in data and data["status"] in accepted_qr_statuses():
                updates.append("status=?")
                params.append(storage_qr_status(data["status"]))
            if "destination" in data:
                updates.append("destination=?")
                params.append(str(data["destination"] or ""))

            try:
                cfg = json.loads(before["experience_config"] or "{}")
            except (TypeError, json.JSONDecodeError):
                cfg = {}
            cfg_changed = False
            if "experience_config" in data:
                incoming = data["experience_config"]
                if isinstance(incoming, str):
                    try:
                        incoming = json.loads(incoming)
                    except json.JSONDecodeError:
                        incoming = {}
                cfg = {**cfg, **(incoming or {})}
                cfg_changed = True
            if "description" in data:
                cfg["description"] = str(data["description"] or "").strip()
                cfg_changed = True
            if "branding" in data and isinstance(data["branding"], dict):
                cfg["branding"] = {**(cfg.get("branding") or {}), **data["branding"]}
                cfg_changed = True
            if "customer_flow" in data:
                cfg["customer_flow"] = data["customer_flow"]
                cfg_changed = True
            if cfg_changed:
                cfg_json = json.dumps(cfg)
                updates.append("experience_config=?")
                params.append(cfg_json)
                if _column_exists(conn, "qr_experiences", "content"):
                    updates.append("content=?")
                    params.append(cfg_json)
            if "content" in data and isinstance(data["content"], dict):
                cfg_json = json.dumps(data["content"])
                updates.append("experience_config=?")
                params.append(cfg_json)
                if _column_exists(conn, "qr_experiences", "content"):
                    updates.append("content=?")
                    params.append(cfg_json)

            if updates:
                updates.append("updated_at=?")
                params.extend([_now(), experience_id, ws])
                conn.execute(
                    f"UPDATE qr_experiences SET {', '.join(updates)} WHERE id=? AND workspace_id=?",
                    params,
                )
            row = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (experience_id,)).fetchone()
            # Sync linked QR code — keep experience landing when already builder-based
            if row["qr_code_id"]:
                qr = conn.execute("SELECT * FROM qr_codes WHERE id=?", (row["qr_code_id"],)).fetchone()
                current_pass = (qr["pass_type"] if qr and "pass_type" in qr.keys() else None) or ""
                pass_type = current_pass if current_pass == "experience" else TYPE_TO_PASS.get(row["type"], "storefront")
                if row["destination"] and str(row["destination"]).startswith("/experience/"):
                    pass_type = "experience"
                ref_id = None
                try:
                    cfg2 = json.loads(row["experience_config"] or "{}")
                    ref_id = cfg2.get("ref_id")
                except (TypeError, json.JSONDecodeError):
                    pass
                qr_status = "active" if row["status"] == "active" else row["status"]
                conn.execute(
                    """UPDATE qr_codes SET name=?, pass_type=?, ref_id=?, status=?, updated_at=?
                       WHERE id=?""",
                    (row["name"], pass_type, ref_id, qr_status, _now(), row["qr_code_id"]),
                )
            if "status" in data and data["status"] != before["status"]:
                from bos.events import emit
                from customer_qr_platform import manage_landing_qr_href

                emit(
                    conn, "qr_experience.status_changed", "qr_experience", experience_id,
                    workspace_id=int(ws), user_id=uid(), actor="member",
                    title=f"Landing page {data['status']}: {row['name']}",
                    href=manage_landing_qr_href(conn, experience_id),
                    metadata={"from": before["status"], "to": data["status"]},
                )
            row = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (experience_id,)).fetchone()
            return jsonify(experience_to_api(conn, row))

    @app.put("/api/qr-experiences/<int:experience_id>/blocks")
    @login_required
    def api_qr_experience_blocks_put(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else data if isinstance(data, list) else []
        with db() as conn:
            _guard(conn, "qr_experience.update")
            get_experience(conn, experience_id, int(ws))
            from qr_experience_builder import replace_blocks
            saved = replace_blocks(conn, experience_id, blocks)
            conn.execute(
                "UPDATE qr_experiences SET updated_at=? WHERE id=?",
                (_now(), experience_id),
            )
            return jsonify({"blocks": saved})

    @app.put("/api/qr-experiences/<int:experience_id>/actions")
    @login_required
    def api_qr_experience_actions_put(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        actions = data.get("actions") if isinstance(data.get("actions"), list) else data if isinstance(data, list) else []
        with db() as conn:
            _guard(conn, "qr_experience.update")
            row = get_experience(conn, experience_id, int(ws))
            from qr_experience_builder import enrich_actions_with_hrefs, replace_actions
            saved = replace_actions(conn, experience_id, actions)
            store = conn.execute("SELECT * FROM stores WHERE id=?", (row["store_id"],)).fetchone() if row["store_id"] else None
            conn.execute(
                "UPDATE qr_experiences SET updated_at=? WHERE id=?",
                (_now(), experience_id),
            )
            return jsonify({
                "actions": enrich_actions_with_hrefs(conn, saved, store, row["workspace_id"]),
            })

    @app.get("/api/qr-experiences/<int:experience_id>/preview")
    @login_required
    def api_qr_experience_preview(experience_id):
        """Owner preview payload — same structure as customer landing, no mock content."""
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.read")
            row = get_experience(conn, experience_id, int(ws))
            store = conn.execute("SELECT * FROM stores WHERE id=?", (row["store_id"],)).fetchone() if row["store_id"] else None
            from qr_experience_builder import public_experience_payload
            payload = public_experience_payload(conn, row, store)
            payload["preview"] = True
            return jsonify(payload)

    @app.post("/api/qr-experiences/<int:experience_id>/publish")
    @login_required
    def api_qr_experience_publish(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.publish")
            before = get_experience(conn, experience_id, int(ws))
            qr = None
            if before["qr_code_id"]:
                qr = conn.execute("SELECT * FROM qr_codes WHERE id=?", (before["qr_code_id"],)).fetchone()
            code = qr["code"] if qr else None
            from qr_experience_runtime import assign_public_slug
            pub_slug = assign_public_slug(conn, experience_id, before["name"])
            destination = f"/e/{pub_slug}"
            pub_cols = ", public_url=?" if _column_exists(conn, "qr_experiences", "public_url") else ""
            conn.execute(
                f"""UPDATE qr_experiences SET status='active', destination=?, updated_at=?{pub_cols}
                   WHERE id=? AND workspace_id=?""",
                (destination, _now(), *([destination] if pub_cols else []), experience_id, ws),
            )
            row = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (experience_id,)).fetchone()
            if row["qr_code_id"]:
                conn.execute(
                    """UPDATE qr_codes SET status='active', pass_type='experience',
                       experience_id=?, updated_at=? WHERE id=?""",
                    (experience_id, _now(), row["qr_code_id"]),
                )
            from bos.events import emit
            from customer_qr_platform import manage_landing_qr_href

            emit(
                conn, "qr_experience.published", "qr_experience", experience_id,
                workspace_id=int(ws), user_id=uid(), actor="member",
                title=f"Landing page published: {row['name']}",
                href=manage_landing_qr_href(conn, experience_id),
            )
            return jsonify(experience_to_api(conn, row))

    @app.post("/api/qr-experiences/<int:experience_id>/duplicate")
    @login_required
    def api_qr_experience_duplicate(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.create")
            source = get_experience(conn, experience_id, int(ws))
            new_id = _duplicate_experience(conn, source, int(ws), uid())
            row = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (new_id,)).fetchone()
            return jsonify(experience_to_api(conn, row)), 201

    @app.post("/api/qr-experiences/<int:experience_id>/archive")
    @app.post("/api/experiences/<int:experience_id>/archive")
    @login_required
    def api_qr_experience_archive(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.delete")
            row = get_experience(conn, experience_id, int(ws))
            conn.execute(
                "UPDATE qr_experiences SET status='archived', updated_at=? WHERE id=?",
                (_now(), experience_id),
            )
            if row["qr_code_id"]:
                conn.execute(
                    "UPDATE qr_codes SET status='archived', updated_at=? WHERE id=?",
                    (_now(), row["qr_code_id"]),
                )
            conn.execute(
                "UPDATE qr_codes SET status='archived', updated_at=? WHERE experience_id=? AND status!='archived'",
                (_now(), experience_id),
            )
            from bos.events import emit
            emit(
                conn, "qr_experience.archived", "qr_experience", experience_id,
                workspace_id=int(ws), user_id=uid(), actor="member",
                title=f"Experience archived: {row['name']}",
                href="/app/store#experiences",
            )
        return jsonify({"ok": True, "status": "archived"})

    def _duplicate_experience(conn, source, workspace_id: int, user_id: int) -> int:
        try:
            config = json.loads(source["experience_config"] or "{}")
        except json.JSONDecodeError:
            config = {}
        name = f"{source['name']} (Copy)"
        code = _code()
        while conn.execute("SELECT 1 FROM qr_codes WHERE code=?", (code,)).fetchone():
            code = _code()
        qcur = conn.execute(
            """INSERT INTO qr_codes
               (store_id, name, code, pass_type, ref_id, status, workspace_id, updated_at)
               VALUES (?, ?, ?, 'experience', ?, 'draft', ?, ?)""",
            (source["store_id"], name, code, config.get("ref_id"), workspace_id, _now()),
        )
        qr_id = int(qcur.lastrowid)
        cur = conn.execute(
            """INSERT INTO qr_experiences
               (workspace_id, store_id, qr_code_id, name, type, status,
                experience_config, destination, created_by, updated_at)
               VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""",
            (
                workspace_id, source["store_id"], qr_id, name, source["type"],
                source["experience_config"], f"/e/{code}", user_id, _now(),
            ),
        )
        new_id = int(cur.lastrowid)
        conn.execute("UPDATE qr_codes SET experience_id=? WHERE id=?", (new_id, qr_id))
        from qr_experience_builder import list_blocks, list_actions
        for b in list_blocks(conn, source["id"]):
            conn.execute(
                """INSERT INTO qr_experience_blocks (experience_id, type, content, sort_order)
                   VALUES (?, ?, ?, ?)""",
                (new_id, b["type"], json.dumps(b.get("content") or {}), b.get("order", 0)),
            )
        for a in list_actions(conn, source["id"]):
            conn.execute(
                """INSERT INTO qr_experience_actions (experience_id, type, label, configuration, sort_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (new_id, a["type"], a["label"], json.dumps(a.get("configuration") or {}), a.get("order", 0)),
            )
        from qr_experience_workflow import get_workflow_for_experience, workflow_to_api
        src_wf = get_workflow_for_experience(conn, source["id"], workspace_id)
        if src_wf:
            steps = workflow_to_api(src_wf)["steps"]
            conn.execute(
                """INSERT INTO qr_experience_workflows
                   (experience_id, workspace_id, name, status, trigger_type, steps, created_at, updated_at)
                   VALUES (?, ?, ?, 'draft', 'qr_scanned', ?, ?, ?)""",
                (new_id, workspace_id, f"{name} Workflow", json.dumps(steps), _now(), _now()),
            )
        from bos.events import emit
        emit(
            conn, "qr_experience.created", "qr_experience", new_id,
            workspace_id=workspace_id, user_id=user_id, actor="member",
            title=f"QR Experience duplicated: {name}",
            href=f"/app/store#experience/{new_id}",
        )
        return new_id

    def _delete_experience(conn, row, workspace_id: int, user_id: int) -> bool:
        if row["status"] not in ("draft", "archived"):
            return False
        experience_id = int(row["id"])
        qr_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM qr_codes WHERE experience_id=? OR id=?",
            (experience_id, row["qr_code_id"] or 0),
        ).fetchall()]
        for qr_id in qr_ids:
            conn.execute("DELETE FROM qr_codes WHERE id=?", (qr_id,))
        conn.execute("DELETE FROM qr_experiences WHERE id=? AND workspace_id=?", (experience_id, workspace_id))
        from bos.events import emit
        emit(
            conn, "qr_experience.deleted", "qr_experience", experience_id,
            workspace_id=workspace_id, user_id=user_id, actor="member",
            title=f"Experience deleted: {row['name']}",
            href="/app/store#experiences",
        )
        return True

    @app.post("/api/qr-experiences/batch")
    @app.post("/api/experiences/batch")
    @login_required
    def api_qr_experiences_batch():
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        action = (data.get("action") or "").strip()
        ids = [int(x) for x in data.get("experience_ids", []) if str(x).isdigit()]
        if not ids:
            return jsonify({"error": "Select at least one experience."}), 400

        perm = {
            "archive": "qr_experience.delete",
            "activate": "qr_experience.update",
            "duplicate": "qr_experience.create",
            "delete": "qr_experience.delete",
            "export": "qr_experience.read",
        }.get(action)
        if not perm:
            return jsonify({"error": "Unknown action."}), 400

        with db() as conn:
            _guard(conn, perm)
            rows = []
            for eid in ids:
                row = conn.execute(
                    "SELECT * FROM qr_experiences WHERE id=? AND workspace_id=?",
                    (eid, int(ws)),
                ).fetchone()
                if row:
                    rows.append(row)

            if not rows:
                return jsonify({"error": "No matching experiences found."}), 404

            if action == "export":
                exported = [experience_to_api(conn, row) for row in rows]
                return jsonify({
                    "experiences": exported,
                    "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

            processed = 0
            skipped = 0
            user_id = uid()

            for row in rows:
                eid = int(row["id"])
                if action == "archive":
                    if row["status"] == "archived":
                        skipped += 1
                        continue
                    conn.execute(
                        "UPDATE qr_experiences SET status='archived', updated_at=? WHERE id=?",
                        (_now(), eid),
                    )
                    if row["qr_code_id"]:
                        conn.execute(
                            "UPDATE qr_codes SET status='archived', updated_at=? WHERE id=?",
                            (_now(), row["qr_code_id"]),
                        )
                    conn.execute(
                        "UPDATE qr_codes SET status='archived', updated_at=? WHERE experience_id=? AND status!='archived'",
                        (_now(), eid),
                    )
                    from bos.events import emit
                    emit(
                        conn, "qr_experience.archived", "qr_experience", eid,
                        workspace_id=int(ws), user_id=user_id, actor="member",
                        title=f"Experience archived: {row['name']}",
                        href="/app/store#experiences",
                    )
                    processed += 1
                elif action == "activate":
                    conn.execute(
                        "UPDATE qr_experiences SET status='active', updated_at=? WHERE id=?",
                        (_now(), eid),
                    )
                    if row["qr_code_id"]:
                        conn.execute(
                            "UPDATE qr_codes SET status='active', updated_at=? WHERE id=?",
                            (_now(), row["qr_code_id"]),
                        )
                    conn.execute(
                        "UPDATE qr_codes SET status='active', updated_at=? WHERE experience_id=?",
                        (_now(), eid),
                    )
                    from bos.events import emit
                    emit(
                        conn, "qr_experience.updated", "qr_experience", eid,
                        workspace_id=int(ws), user_id=user_id, actor="member",
                        title=f"Experience activated: {row['name']}",
                        href="/app/store#experiences",
                    )
                    processed += 1
                elif action == "duplicate":
                    _duplicate_experience(conn, row, int(ws), user_id)
                    processed += 1
                elif action == "delete":
                    if _delete_experience(conn, row, int(ws), user_id):
                        processed += 1
                    else:
                        skipped += 1

        return jsonify({"ok": True, "action": action, "processed": processed, "skipped": skipped})

    @app.delete("/api/qr-experiences/<int:experience_id>")
    @app.delete("/api/experiences/<int:experience_id>")
    @login_required
    def api_qr_experience_delete(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.delete")
            row = get_experience(conn, experience_id, int(ws))
            if row["status"] not in ("draft", "archived"):
                return jsonify({"error": "Archive active experiences before deleting. Draft and archived items can be deleted."}), 400
            qr_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM qr_codes WHERE experience_id=? OR id=?",
                (experience_id, row["qr_code_id"] or 0),
            ).fetchall()]
            for qr_id in qr_ids:
                conn.execute("DELETE FROM qr_codes WHERE id=?", (qr_id,))
            conn.execute("DELETE FROM qr_experiences WHERE id=? AND workspace_id=?", (experience_id, ws))
            from bos.events import emit
            emit(
                conn, "qr_experience.deleted", "qr_experience", experience_id,
                workspace_id=int(ws), user_id=uid(), actor="member",
                title=f"Experience deleted: {row['name']}",
                href="/app/store#experiences",
            )
        return jsonify({"ok": True, "deleted": True})

    @app.get("/api/qr-experiences/<int:experience_id>/qr-codes")
    @app.get("/api/experiences/<int:experience_id>/qr-codes")
    @login_required
    def api_experience_qr_codes_list(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "qr_experience.read")
            row = get_experience(conn, experience_id, int(ws))
            return jsonify(_list_experience_qr_codes(conn, row))

    @app.post("/api/qr-experiences/<int:experience_id>/qr-codes")
    @app.post("/api/experiences/<int:experience_id>/qr-codes")
    @login_required
    def api_experience_qr_codes_create(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip() or "QR Code"
        with db() as conn:
            _guard(conn, "qr_experience.update")
            row = get_experience(conn, experience_id, int(ws))
            store = conn.execute("SELECT * FROM stores WHERE id=?", (row["store_id"],)).fetchone()
            if not store:
                abort(400)
            code = _code()
            while conn.execute("SELECT 1 FROM qr_codes WHERE code=?", (code,)).fetchone():
                code = _code()
            qcur = conn.execute(
                """INSERT INTO qr_codes
                   (store_id, name, code, pass_type, status, workspace_id, experience_id, updated_at)
                   VALUES (?, ?, ?, 'experience', 'draft', ?, ?, ?)""",
                (store["id"], name, code, ws, experience_id, _now()),
            )
            qr_row = conn.execute("SELECT * FROM qr_codes WHERE id=?", (int(qcur.lastrowid),)).fetchone()
            return jsonify(_qr_code_to_api(conn, qr_row, row)), 201

    @app.patch("/api/qr-experiences/<int:experience_id>/qr-codes/<int:qr_id>")
    @app.patch("/api/experiences/<int:experience_id>/qr-codes/<int:qr_id>")
    @login_required
    def api_experience_qr_code_update(experience_id, qr_id):
        from bos.mvp_schema import storage_qr_status

        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "qr_experience.update")
            row = get_experience(conn, experience_id, int(ws))
            qr = conn.execute(
                """SELECT * FROM qr_codes
                   WHERE id=? AND (experience_id=? OR id=?)""",
                (qr_id, experience_id, row["qr_code_id"] or 0),
            ).fetchone()
            if not qr:
                abort(404)
            updates, params = [], []
            if "name" in data and str(data["name"]).strip():
                updates.append("name=?")
                params.append(str(data["name"]).strip())
            if "status" in data:
                status = data["status"]
                if status in ("active", "draft", "disabled", "archived", "paused"):
                    storage = storage_qr_status(status) if status == "disabled" else status
                    if storage == "archived":
                        storage = "paused"
                    updates.append("status=?")
                    params.append(storage)
            if updates:
                updates.append("updated_at=?")
                params.extend([_now(), qr_id])
                conn.execute(f"UPDATE qr_codes SET {', '.join(updates)} WHERE id=?", params)
            qr_row = conn.execute("SELECT * FROM qr_codes WHERE id=?", (qr_id,)).fetchone()
            return jsonify(_qr_code_to_api(conn, qr_row, row))

    @app.post("/api/qr-experiences/<int:experience_id>/events")
    def api_qr_experience_track(experience_id):
        """Public-ish analytics event (scan / action). No auth required for customer scans."""
        data = request.get_json(silent=True) or {}
        event_type = (data.get("event_type") or "scan").strip()
        if event_type not in ("scan", "action_completed", "view"):
            return jsonify({"error": "Invalid event_type"}), 400
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM qr_experiences WHERE id=? AND status IN ('active', 'draft')",
                (experience_id,),
            ).fetchone()
            if not row:
                abort(404)
            # Draft tracking only for owner preview via session; public requires active
            if row["status"] != "active" and not session.get("user_id"):
                abort(404)
            conn.execute(
                """INSERT INTO qr_experience_events
                   (experience_id, workspace_id, event_type, visitor_key, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    experience_id, row["workspace_id"], event_type,
                    data.get("visitor_key"),
                    json.dumps(data.get("metadata") or {}),
                ),
            )
        return jsonify({"ok": True}), 201

    @app.get("/experience/<code>")
    def qr_experience_landing(code):
        from flask import redirect, render_template
        from qr_experience_runtime import resolve_experience
        with db() as conn:
            exp, _qr = resolve_experience(conn, code.lower())
            if not exp:
                abort(404)
            if exp["status"] == "paused":
                return render_template("customer/qr_disabled.html", experience_name=exp["name"]), 403
            if exp["status"] == "archived":
                return render_template("customer/qr_expired.html", experience_name=exp["name"]), 410
            if exp["status"] == "active":
                slug = exp["public_slug"] if "public_slug" in exp.keys() and exp["public_slug"] else code
                return redirect(f"/e/{slug}?from=qr")
        abort(404)

    @app.get("/experience/<code>/preview")
    @login_required
    def qr_experience_owner_preview(code):
        from qr_experience_runtime import resolve_experience
        with db() as conn:
            exp, _qr = resolve_experience(conn, code.lower(), allow_draft=True)
            if not exp:
                abort(404)
            slug = exp["public_slug"] if "public_slug" in exp.keys() and exp["public_slug"] else code
            return redirect(f"/e/{slug}/preview")

    app.init_qr_experience_tables = init_qr_experience_tables
