"""QR Experience Builder — blocks, actions, landing pages, template seeding."""

from __future__ import annotations

import json
from datetime import datetime

BLOCK_TYPES = ("header", "text", "image", "info", "actions", "shop", "survey", "booking", "check_in", "contact")
ACTION_TYPES = ("open_page", "start_survey", "create_booking", "start_checkin", "show_information", "external_link")

BUILDER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experience_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    content TEXT DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qr_exp_blocks ON qr_experience_blocks(experience_id, sort_order);

CREATE TABLE IF NOT EXISTS qr_experience_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    configuration TEXT DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qr_exp_actions ON qr_experience_actions(experience_id, sort_order);
"""

# Template → default blocks + actions (real structure, filled with store name at seed time)
TEMPLATE_BUILDER_SEED = {
    "restaurant": {
        "blocks": [
            {"type": "header", "content": {"title": "{name}", "subtitle": "Welcome — scan to get started"}},
            {"type": "shop", "content": {"label": "View shop", "subtitle": "Browse our full menu and deals"}},
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
    "event": {
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
    "product": {
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
    "service": {
        "blocks": [
            {"type": "header", "content": {"title": "{name}", "subtitle": "Book your visit"}},
            {"type": "info", "content": {"title": "How it works", "body": "{description}"}},
            {"type": "actions", "content": {"title": "Get started"}},
        ],
        "actions": [
            {"type": "create_booking", "label": "Book Appointment", "configuration": {}},
            {"type": "start_checkin", "label": "I'm here — Check-in", "configuration": {}},
            {"type": "start_survey", "label": "Leave Feedback", "configuration": {}},
        ],
    },
    "feedback_only": {
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
    "check_in_only": {
        "blocks": [
            {"type": "header", "content": {"title": "{name}", "subtitle": "Check-in"}},
            {"type": "info", "content": {"title": "Arrival", "body": "{description}"}},
            {"type": "check_in", "content": {"title": "Confirm your arrival"}},
            {"type": "actions", "content": {"title": ""}},
        ],
        "actions": [
            {"type": "start_checkin", "label": "Check-in Now", "configuration": {}},
        ],
    },
}


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def init_builder_tables(conn) -> None:
    conn.executescript(BUILDER_SCHEMA_SQL)


def _fill(text: str, ctx: dict) -> str:
    out = text or ""
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v or ""))
    return out


def seed_template_builder(conn, experience_id: int, template_id: str, ctx: dict) -> None:
    from qr_experience_templates import template_builder_seed
    seed = template_builder_seed(conn, template_id)
    if not seed.get("blocks"):
        seed = TEMPLATE_BUILDER_SEED.get(template_id) or TEMPLATE_BUILDER_SEED["feedback_only"]
    for i, b in enumerate(seed["blocks"]):
        content = {k: _fill(v, ctx) if isinstance(v, str) else v for k, v in (b.get("content") or {}).items()}
        conn.execute(
            """INSERT INTO qr_experience_blocks (experience_id, type, content, sort_order)
               VALUES (?, ?, ?, ?)""",
            (experience_id, b["type"], json.dumps(content), i),
        )
    for i, a in enumerate(seed["actions"]):
        conn.execute(
            """INSERT INTO qr_experience_actions (experience_id, type, label, configuration, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (experience_id, a["type"], a["label"], json.dumps(a.get("configuration") or {}), i),
        )


def list_blocks(conn, experience_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM qr_experience_blocks WHERE experience_id=? ORDER BY sort_order, id",
        (experience_id,),
    ).fetchall()
    result = []
    for r in rows:
        try:
            content = json.loads(r["content"] or "{}")
        except json.JSONDecodeError:
            content = {}
        result.append({
            "id": r["id"],
            "experience_id": r["experience_id"],
            "type": r["type"],
            "content": content,
            "order": r["sort_order"],
        })
    return result


def list_actions(conn, experience_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM qr_experience_actions WHERE experience_id=? ORDER BY sort_order, id",
        (experience_id,),
    ).fetchall()
    result = []
    for r in rows:
        try:
            configuration = json.loads(r["configuration"] or "{}")
        except json.JSONDecodeError:
            configuration = {}
        result.append({
            "id": r["id"],
            "experience_id": r["experience_id"],
            "type": r["type"],
            "label": r["label"],
            "configuration": configuration,
            "order": r["sort_order"],
        })
    return result


def replace_blocks(conn, experience_id: int, blocks: list) -> list[dict]:
    conn.execute("DELETE FROM qr_experience_blocks WHERE experience_id=?", (experience_id,))
    for i, b in enumerate(blocks or []):
        btype = b.get("type") or "text"
        if btype not in BLOCK_TYPES:
            continue
        content = b.get("content") or {}
        conn.execute(
            """INSERT INTO qr_experience_blocks (experience_id, type, content, sort_order)
               VALUES (?, ?, ?, ?)""",
            (experience_id, btype, json.dumps(content), b.get("order", i)),
        )
    return list_blocks(conn, experience_id)


def replace_actions(conn, experience_id: int, actions: list) -> list[dict]:
    conn.execute("DELETE FROM qr_experience_actions WHERE experience_id=?", (experience_id,))
    for i, a in enumerate(actions or []):
        atype = a.get("type") or "show_information"
        if atype not in ACTION_TYPES:
            continue
        conn.execute(
            """INSERT INTO qr_experience_actions (experience_id, type, label, configuration, sort_order)
               VALUES (?, ?, ?, ?, ?)""",
            (
                experience_id, atype, (a.get("label") or atype.replace("_", " ").title()),
                json.dumps(a.get("configuration") or {}), a.get("order", i),
            ),
        )
    return list_actions(conn, experience_id)


def resolve_action_href(conn, action: dict, store_row, workspace_id: int) -> str | None:
    """Map ExperienceAction → real customer URL from workspace data."""
    atype = action.get("type")
    cfg = action.get("configuration") or {}
    if cfg.get("url"):
        return str(cfg["url"])
    slug = store_row["slug"] if store_row else None
    store_id = store_row["id"] if store_row else None

    if atype == "show_information":
        return "#info"

    if atype == "external_link":
        url = cfg.get("url") or cfg.get("href")
        return str(url) if url else None

    if atype == "open_page":
        target = cfg.get("target") or "menu"
        if cfg.get("path"):
            return str(cfg["path"])
        if target in ("contact",) and slug:
            return f"/store/{slug}#sf-contact"
        if target in ("menu", "shop", "storefront") and slug:
            return f"/store/{slug}"
        if slug:
            return f"/store/{slug}"
        return None

    if atype == "start_survey":
        survey_id = cfg.get("survey_id")
        row = None
        if survey_id:
            row = conn.execute(
                "SELECT pub_code FROM surveys WHERE id=? AND workspace_id=? AND status='published'",
                (survey_id, workspace_id),
            ).fetchone()
        if not row:
            row = conn.execute(
                """SELECT pub_code FROM surveys
                   WHERE workspace_id=? AND status='published' AND pub_code IS NOT NULL
                   ORDER BY updated_at DESC LIMIT 1""",
                (workspace_id,),
            ).fetchone()
        if row and row["pub_code"]:
            return f"/survey/{row['pub_code']}"
        return None

    if atype == "create_booking":
        # Public booking lands on storefront until a dedicated customer booking page exists
        return f"/store/{slug}?intent=booking" if slug else None

    if atype == "start_checkin":
        point_id = cfg.get("check_in_point_id")
        point = None
        if point_id and store_id:
            point = conn.execute(
                "SELECT point_code FROM check_in_points WHERE id=? AND store_id=? AND status!='archived'",
                (point_id, store_id),
            ).fetchone()
        if not point and store_id:
            point = conn.execute(
                """SELECT point_code FROM check_in_points
                   WHERE store_id=? AND status!='archived' ORDER BY id DESC LIMIT 1""",
                (store_id,),
            ).fetchone()
        if point and point["point_code"]:
            return f"/checkin/{point['point_code']}"
        return None

    return None


def enrich_actions_with_hrefs(conn, actions: list[dict], store_row, workspace_id: int) -> list[dict]:
    out = []
    for a in actions:
        item = dict(a)
        item["href"] = resolve_action_href(conn, a, store_row, workspace_id)
        out.append(item)
    return out


def public_experience_payload(conn, experience_row, store_row=None) -> dict:
    """Payload for customer landing — real DB blocks/actions only."""
    from bos.workspace_store import workspace_identity

    eid = experience_row["id"]
    ws_id = experience_row["workspace_id"]
    identity = workspace_identity(conn, ws_id)
    try:
        config = json.loads(experience_row["experience_config"] or "{}")
    except json.JSONDecodeError:
        config = {}
    branding_cfg = config.get("branding") or {}
    blocks = list_blocks(conn, eid)
    if not store_row and identity.get("store_id"):
        store_row = conn.execute("SELECT * FROM stores WHERE id=?", (identity["store_id"],)).fetchone()
    actions = enrich_actions_with_hrefs(conn, list_actions(conn, eid), store_row, ws_id)
    return {
        "id": eid,
        "name": experience_row["name"],
        "status": experience_row["status"],
        "description": config.get("description") or "",
        "template_id": config.get("template_id"),
        "branding": {
            "business_name": branding_cfg.get("business_name") or identity["business_name"],
            "logo_url": branding_cfg.get("logo_url") or identity.get("logo_url") or "",
            "background": branding_cfg.get("background") or "",
            "theme": branding_cfg.get("theme") or "light",
            "language": branding_cfg.get("language") or "en",
        },
        "blocks": blocks,
        "actions": actions,
        "contact": identity.get("contact") or {},
        "store_slug": identity.get("store_slug"),
    }
