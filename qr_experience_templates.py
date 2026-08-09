"""QR Experience Template Library — predefined customer workflow templates."""

from __future__ import annotations

import json
from datetime import datetime

TEMPLATE_CATEGORIES = (
    "Restaurant",
    "Retail",
    "Event",
    "Service",
    "Hospitality",
    "General Business",
)

# Canonical template catalog — single source of truth for metadata + builder seed.
CORE_TEMPLATES: tuple[dict, ...] = (
    {
        "id": "restaurant",
        "name": "Restaurant Table QR",
        "category": "Restaurant",
        "description": "Table customer experience — business info, menu, optional booking, feedback.",
        "preview_image": "",
        "experience_type": "menu",
        "version": 1,
        "sort_order": 10,
        "experience_configuration": {
            "default_name": "Restaurant Table Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "info", "label": "Business Information", "role": "first"},
                {"id": "menu", "label": "Menu", "role": "optional"},
                {"id": "feedback", "label": "Feedback", "role": "completion"},
            ],
            "connected": ["booking", "feedback"],
            "enabled_actions": {"feedback": True, "survey": True, "booking": True, "checkin": False},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "Welcome — scan to get started"}},
                {"type": "info", "content": {"title": "About", "body": "{description}"}},
                {"type": "actions", "content": {"title": "What would you like to do?"}},
                {"type": "contact", "content": {"title": "Contact", "show_store": True}},
            ],
            "actions": [
                {"type": "open_page", "label": "View Menu", "configuration": {"target": "menu"}},
                {"type": "create_booking", "label": "Book Now", "configuration": {}},
                {"type": "start_survey", "label": "Leave Feedback", "configuration": {}},
            ],
        },
    },
    {
        "id": "feedback_only",
        "name": "Customer Feedback QR",
        "category": "General Business",
        "description": "Collect customer opinions — rating, survey, submit feedback.",
        "preview_image": "",
        "experience_type": "feedback",
        "version": 1,
        "sort_order": 20,
        "experience_configuration": {
            "default_name": "Customer Feedback Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "rating", "label": "Rating", "role": "first"},
                {"id": "survey", "label": "Survey", "role": "optional"},
                {"id": "feedback", "label": "Submit Feedback", "role": "completion"},
            ],
            "connected": ["feedback"],
            "enabled_actions": {"feedback": True, "survey": True, "booking": False, "checkin": False},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "We value your feedback"}},
                {"type": "text", "content": {"body": "{description}"}},
                {"type": "survey", "content": {"title": "Your feedback"}},
                {"type": "actions", "content": {"title": ""}},
            ],
            "actions": [
                {"type": "start_survey", "label": "Start Survey", "configuration": {}},
            ],
        },
    },
    {
        "id": "check_in_only",
        "name": "Event Check-in QR",
        "category": "Event",
        "description": "Event attendance — event info, check-in, confirmation.",
        "preview_image": "",
        "experience_type": "check_in",
        "version": 1,
        "sort_order": 30,
        "experience_configuration": {
            "default_name": "Event Check-in Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "info", "label": "Event Information", "role": "first"},
                {"id": "check_in", "label": "Check-in", "role": "optional"},
                {"id": "confirm", "label": "Confirmation", "role": "completion"},
            ],
            "connected": ["checkin"],
            "enabled_actions": {"feedback": False, "survey": False, "booking": False, "checkin": True},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "Event check-in"}},
                {"type": "info", "content": {"title": "Event information", "body": "{description}"}},
                {"type": "check_in", "content": {"title": "Confirm your arrival"}},
                {"type": "actions", "content": {"title": ""}},
            ],
            "actions": [
                {"type": "start_checkin", "label": "Check-in Now", "configuration": {}},
            ],
        },
    },
    {
        "id": "event",
        "name": "Event Experience QR",
        "category": "Event",
        "description": "Full event flow — information, check-in, and survey.",
        "preview_image": "",
        "experience_type": "event",
        "version": 1,
        "sort_order": 31,
        "experience_configuration": {
            "default_name": "Event Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "info", "label": "Event Information", "role": "first"},
                {"id": "check_in", "label": "Check-in", "role": "optional"},
                {"id": "survey", "label": "Survey", "role": "completion"},
            ],
            "connected": ["checkin", "feedback"],
            "enabled_actions": {"feedback": True, "survey": True, "booking": False, "checkin": True},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "Event experience"}},
                {"type": "info", "content": {"title": "Event information", "body": "{description}"}},
                {"type": "actions", "content": {"title": "Actions"}},
            ],
            "actions": [
                {"type": "show_information", "label": "Event Info", "configuration": {}},
                {"type": "start_checkin", "label": "Check-in", "configuration": {}},
                {"type": "start_survey", "label": "Survey", "configuration": {}},
            ],
        },
    },
    {
        "id": "product",
        "name": "Product Information QR",
        "category": "Retail",
        "description": "Physical product interaction — product info, customer action, feedback.",
        "preview_image": "",
        "experience_type": "product",
        "version": 1,
        "sort_order": 40,
        "experience_configuration": {
            "default_name": "Product Information Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "product", "label": "Product Information", "role": "first"},
                {"id": "action", "label": "Customer Action", "role": "optional"},
                {"id": "feedback", "label": "Feedback", "role": "completion"},
            ],
            "connected": ["feedback"],
            "enabled_actions": {"feedback": True, "survey": True, "booking": False, "checkin": False},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "Product information"}},
                {"type": "info", "content": {"title": "Details", "body": "{description}"}},
                {"type": "actions", "content": {"title": "Next steps"}},
            ],
            "actions": [
                {"type": "show_information", "label": "Product Info", "configuration": {}},
                {"type": "start_survey", "label": "Leave Feedback", "configuration": {}},
            ],
        },
    },
    {
        "id": "service",
        "name": "Booking QR",
        "category": "Service",
        "description": "Simple reservation flow — booking form and confirmation.",
        "preview_image": "",
        "experience_type": "booking",
        "version": 1,
        "sort_order": 50,
        "experience_configuration": {
            "default_name": "Booking Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "booking", "label": "Booking Form", "role": "first"},
                {"id": "confirm", "label": "Confirmation", "role": "completion"},
            ],
            "connected": ["booking", "checkin", "feedback"],
            "enabled_actions": {"feedback": True, "survey": True, "booking": True, "checkin": True},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "Book your visit"}},
                {"type": "info", "content": {"title": "How it works", "body": "{description}"}},
                {"type": "booking", "content": {"title": "Make a reservation"}},
                {"type": "actions", "content": {"title": "Get started"}},
            ],
            "actions": [
                {"type": "create_booking", "label": "Book Appointment", "configuration": {}},
                {"type": "start_checkin", "label": "I'm here — Check-in", "configuration": {}},
                {"type": "start_survey", "label": "Leave Feedback", "configuration": {}},
            ],
        },
    },
    {
        "id": "hospitality",
        "name": "Guest Welcome QR",
        "category": "Hospitality",
        "description": "Hotel and hospitality guest welcome — info, check-in, contact.",
        "preview_image": "",
        "experience_type": "check_in",
        "version": 1,
        "sort_order": 60,
        "experience_configuration": {
            "default_name": "Guest Welcome Experience",
            "customer_flow": [
                {"id": "scan", "label": "Scan QR", "role": "entry"},
                {"id": "info", "label": "Welcome Information", "role": "first"},
                {"id": "check_in", "label": "Check-in", "role": "optional"},
                {"id": "contact", "label": "Contact", "role": "completion"},
            ],
            "connected": ["checkin"],
            "enabled_actions": {"feedback": False, "survey": False, "booking": False, "checkin": True},
            "blocks": [
                {"type": "header", "content": {"title": "{name}", "subtitle": "Welcome"}},
                {"type": "info", "content": {"title": "Guest information", "body": "{description}"}},
                {"type": "check_in", "content": {"title": "Check in to your stay"}},
                {"type": "contact", "content": {"title": "Need help?", "show_store": True}},
            ],
            "actions": [
                {"type": "start_checkin", "label": "Check-in", "configuration": {}},
                {"type": "show_information", "label": "Hotel Info", "configuration": {}},
            ],
        },
    },
)

TEMPLATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experience_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    preview_image TEXT DEFAULT '',
    experience_type TEXT NOT NULL DEFAULT 'menu',
    version INTEGER NOT NULL DEFAULT 1,
    experience_configuration TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_qr_tpl_category ON qr_experience_templates(category, sort_order);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_template_tables(conn) -> None:
    conn.executescript(TEMPLATE_SCHEMA_SQL)
    _seed_core_templates(conn)


def _seed_core_templates(conn) -> None:
    for tpl in CORE_TEMPLATES:
        existing = conn.execute(
            "SELECT version FROM qr_experience_templates WHERE id=?", (tpl["id"],)
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """INSERT INTO qr_experience_templates
               (id, name, category, description, preview_image, experience_type,
                version, experience_configuration, status, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (
                tpl["id"],
                tpl["name"],
                tpl["category"],
                tpl["description"],
                tpl.get("preview_image") or "",
                tpl["experience_type"],
                tpl.get("version") or 1,
                json.dumps(tpl["experience_configuration"]),
                tpl.get("sort_order") or 0,
                _now(),
                _now(),
            ),
        )


def get_template(conn, template_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM qr_experience_templates WHERE id=? AND status='active'",
        (template_id,),
    ).fetchone()
    if not row:
        return _fallback_template(template_id)
    return _row_to_api(row)


def _fallback_template(template_id: str) -> dict | None:
    for tpl in CORE_TEMPLATES:
        if tpl["id"] == template_id:
            return template_to_api(tpl)
    return None


def template_to_api(tpl: dict) -> dict:
    cfg = tpl.get("experience_configuration") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except json.JSONDecodeError:
            cfg = {}
    return {
        "id": tpl["id"],
        "name": tpl.get("name") or tpl.get("label") or tpl["id"],
        "label": tpl.get("name") or tpl.get("label") or tpl["id"],
        "category": tpl.get("category") or "General Business",
        "description": tpl.get("description") or "",
        "preview_image": tpl.get("preview_image") or "",
        "type": tpl.get("experience_type") or tpl.get("type") or "menu",
        "experience_type": tpl.get("experience_type") or tpl.get("type") or "menu",
        "version": tpl.get("version") or 1,
        "default_name": cfg.get("default_name") or tpl.get("name") or "QR Experience",
        "customer_flow": cfg.get("customer_flow") or [],
        "connected": cfg.get("connected") or [],
        "enabled_actions": cfg.get("enabled_actions") or {},
        "blocks": cfg.get("blocks") or [],
        "actions": cfg.get("actions") or [],
        "status": tpl.get("status") or "active",
        "sort_order": tpl.get("sort_order") or 0,
    }


def _row_to_api(row) -> dict:
    try:
        cfg = json.loads(row["experience_configuration"] or "{}")
    except json.JSONDecodeError:
        cfg = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "label": row["name"],
        "category": row["category"],
        "description": row["description"] or "",
        "preview_image": row["preview_image"] or "",
        "type": row["experience_type"],
        "experience_type": row["experience_type"],
        "version": int(row["version"] or 1),
        "default_name": cfg.get("default_name") or row["name"],
        "customer_flow": cfg.get("customer_flow") or [],
        "connected": cfg.get("connected") or [],
        "enabled_actions": cfg.get("enabled_actions") or {},
        "blocks": cfg.get("blocks") or [],
        "actions": cfg.get("actions") or [],
        "status": row["status"],
        "sort_order": row["sort_order"] or 0,
    }


def list_templates(conn, category: str | None = None) -> list[dict]:
    query = "SELECT * FROM qr_experience_templates WHERE status='active'"
    params: list = []
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY sort_order, name"
    rows = conn.execute(query, params).fetchall()
    if rows:
        return [_row_to_api(r) for r in rows]
    # Fallback before first seed
    items = [template_to_api(t) for t in CORE_TEMPLATES]
    if category:
        items = [t for t in items if t["category"] == category]
    return items


def list_categories(conn) -> list[dict]:
    templates = list_templates(conn)
    grouped: dict[str, list] = {c: [] for c in TEMPLATE_CATEGORIES}
    for tpl in templates:
        cat = tpl.get("category") or "General Business"
        grouped.setdefault(cat, []).append(tpl)
    return [
        {"id": cat, "label": cat, "templates": grouped.get(cat) or []}
        for cat in TEMPLATE_CATEGORIES
        if grouped.get(cat)
    ]


def template_builder_seed(conn, template_id: str) -> dict:
    tpl = get_template(conn, template_id)
    if not tpl:
        return {"blocks": [], "actions": []}
    return {"blocks": tpl.get("blocks") or [], "actions": tpl.get("actions") or []}


def template_usage_stats(conn, workspace_id: int, period: str = "all") -> list[dict]:
    """Experiences created per template with interaction totals."""
    from qr_experience_analytics import experience_analytics_summary, period_filter

    rows = conn.execute(
        """SELECT id, name, experience_config, status FROM qr_experiences
           WHERE workspace_id=? AND status!='archived'""",
        (workspace_id,),
    ).fetchall()
    usage: dict[str, dict] = {}
    for row in rows:
        try:
            cfg = json.loads(row["experience_config"] or "{}")
        except json.JSONDecodeError:
            cfg = {}
        tid = cfg.get("template_id") or "unknown"
        if tid not in usage:
            tpl = get_template(conn, tid) if tid != "unknown" else None
            usage[tid] = {
                "template_id": tid,
                "template_name": (tpl or {}).get("name") or tid,
                "category": (tpl or {}).get("category") or "",
                "experiences_created": 0,
                "active_experiences": 0,
                "total_scans": 0,
                "completed_actions": 0,
            }
        usage[tid]["experiences_created"] += 1
        if row["status"] == "active":
            usage[tid]["active_experiences"] += 1
        summary = experience_analytics_summary(conn, row["id"], period)
        usage[tid]["total_scans"] += summary["total_scans"]
        usage[tid]["completed_actions"] += summary["completed_actions"]
    result = sorted(usage.values(), key=lambda x: x["experiences_created"], reverse=True)
    return result


def register_qr_experience_templates(app) -> None:
    from flask import abort, jsonify, request, session
    from app import db, login_required
    from bos.permissions import has_permission

    def uid():
        from app import current_user
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def ws_id():
        return session.get("active_workspace_id")

    def _guard(conn, permission: str):
        ws = ws_id()
        if not ws:
            abort(400)
        if has_permission(conn, uid(), int(ws), permission):
            return
        fallback = {
            "template.read": "qr_experience.read",
            "template.create": "qr_experience.create",
            "template.manage": "qr_experience.update",
        }.get(permission)
        if fallback and has_permission(conn, uid(), int(ws), fallback):
            return
        abort(403)

    @app.get("/api/qr-templates")
    @login_required
    def api_qr_templates_list():
        category = request.args.get("category", "").strip() or None
        grouped = request.args.get("grouped", "").lower() in ("1", "true", "yes")
        with db() as conn:
            _guard(conn, "template.read")
            if grouped:
                return jsonify({"categories": list_categories(conn)})
            return jsonify({"templates": list_templates(conn, category)})

    @app.get("/api/qr-templates/categories")
    @login_required
    def api_qr_templates_categories():
        with db() as conn:
            _guard(conn, "template.read")
            cats = list_categories(conn)
            return jsonify({"categories": cats})

    @app.get("/api/qr-templates/usage")
    @login_required
    def api_qr_template_usage():
        ws = ws_id()
        if not ws:
            return jsonify({"usage": []})
        period = request.args.get("period", "30d")
        with db() as conn:
            _guard(conn, "template.read")
            return jsonify({"usage": template_usage_stats(conn, int(ws), period)})

    @app.get("/api/qr-templates/<template_id>")
    @login_required
    def api_qr_template_detail(template_id: str):
        with db() as conn:
            _guard(conn, "template.read")
            tpl = get_template(conn, template_id)
            if not tpl:
                abort(404)
            return jsonify(tpl)
