"""Universal Feedback Platform — template builder, publishing, inbox."""

from __future__ import annotations

import json
import logging
import uuid

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

_log = logging.getLogger("app.feedback")

FEEDBACK_TYPES = ("review", "survey", "suggestion", "complaint", "nps", "internal", "employee", "custom")
FEEDBACK_STATUSES = ("new", "read", "replied", "archived", "hidden", "flagged")
FEEDBACK_SOURCES = (
    "qr", "public_link", "qr_menu", "qr_product", "qr_event_pass",
    "qr_check_in", "qr_business_card", "customer_portal", "api",
)
PUBLISH_CHANNELS = ("qr", "public_link")
BLOCK_TYPES = (
    "rating", "short_text", "long_text", "single_choice", "multiple_choice",
    "dropdown", "yes_no", "number", "date", "email", "phone",
    "image_upload", "file_upload", "heading", "description", "divider", "section",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedback_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#888888',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    feedback_type TEXT DEFAULT 'review',
    blocks TEXT NOT NULL DEFAULT '[]',
    thank_you_message TEXT DEFAULT 'Thank you for your feedback.',
    status TEXT DEFAULT 'draft',
    version INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback_publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    channel_type TEXT DEFAULT 'qr',
    pub_code TEXT UNIQUE NOT NULL,
    name TEXT,
    status TEXT DEFAULT 'active',
    scan_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(template_id) REFERENCES feedback_templates(id) ON DELETE CASCADE,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback_settings (
    store_id INTEGER PRIMARY KEY,
    anonymous_allowed INTEGER DEFAULT 1,
    require_login INTEGER DEFAULT 0,
    notify_new INTEGER DEFAULT 1,
    notify_negative INTEGER DEFAULT 1,
    thank_you_message TEXT,
    auto_close_days INTEGER DEFAULT 0,
    default_template_id INTEGER,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    workspace_id INTEGER,
    template_id INTEGER,
    publication_id INTEGER,
    form_id INTEGER,
    feedback_type TEXT DEFAULT 'review',
    source_type TEXT NOT NULL,
    source_ref TEXT,
    related_object_type TEXT,
    related_object_id INTEGER,
    rating INTEGER,
    title TEXT,
    comment TEXT,
    responses TEXT,
    attachments TEXT,
    customer_name TEXT,
    customer_email TEXT,
    is_anonymous INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    owner_reply TEXT,
    owner_reply_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback_record_tags (
    feedback_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (feedback_id, tag_id),
    FOREIGN KEY(feedback_id) REFERENCES feedback_records(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES feedback_tags(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    actor TEXT DEFAULT 'system',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(feedback_id) REFERENCES feedback_records(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS feedback_tags_owner_name ON feedback_tags(owner_id, name);
"""


def _block_id() -> str:
    return uuid.uuid4().hex[:8]


def preset_blocks(feedback_type: str) -> list[dict]:
    presets = {
        "review": [
            {"id": _block_id(), "type": "heading", "label": "How was your experience?"},
            {"id": _block_id(), "type": "rating", "label": "Your rating", "required": True, "max": 5},
            {"id": _block_id(), "type": "long_text", "label": "Tell us more", "required": False},
            {"id": _block_id(), "type": "image_upload", "label": "Add a photo", "required": False},
            {"id": _block_id(), "type": "email", "label": "Email (optional)", "required": False},
        ],
        "survey": [
            {"id": _block_id(), "type": "heading", "label": "Quick survey"},
            {"id": _block_id(), "type": "single_choice", "label": "How did you hear about us?", "required": True,
             "options": ["Social media", "Friend", "Search", "Other"]},
            {"id": _block_id(), "type": "rating", "label": "Overall satisfaction", "required": True, "max": 5},
            {"id": _block_id(), "type": "long_text", "label": "Anything else?", "required": False},
        ],
        "complaint": [
            {"id": _block_id(), "type": "heading", "label": "We're sorry something went wrong"},
            {"id": _block_id(), "type": "dropdown", "label": "Category", "required": True,
             "options": ["Service", "Product", "Billing", "Staff", "Other"]},
            {"id": _block_id(), "type": "long_text", "label": "Describe the issue", "required": True},
            {"id": _block_id(), "type": "image_upload", "label": "Supporting photo", "required": False},
            {"id": _block_id(), "type": "email", "label": "Contact email", "required": False},
        ],
        "suggestion": [
            {"id": _block_id(), "type": "heading", "label": "Share your idea"},
            {"id": _block_id(), "type": "short_text", "label": "Suggestion title", "required": True},
            {"id": _block_id(), "type": "long_text", "label": "Details", "required": True},
            {"id": _block_id(), "type": "yes_no", "label": "May we contact you?", "required": False},
        ],
    }
    return presets.get(feedback_type, presets["review"])


TEMPLATE_LIBRARY = (
    {"type": "review", "name": "Review", "desc": "Star rating, comment, and optional photo"},
    {"type": "survey", "name": "Survey", "desc": "Multi-question customer survey"},
    {"type": "complaint", "name": "Complaint", "desc": "Issue reporting with category"},
    {"type": "suggestion", "name": "Suggestion", "desc": "Ideas and improvement feedback"},
    {"type": "custom", "name": "Custom form", "desc": "Start from a blank canvas"},
)


def _strip_legacy_feedback_forms_fk(conn) -> None:
    """Rebuild feedback_records if it still FKs the dropped feedback_forms table."""
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feedback_records" not in tables:
        return
    fks = conn.execute("PRAGMA foreign_key_list(feedback_records)").fetchall()
    if not any(fk["table"] == "feedback_forms" for fk in fks):
        return

    info = conn.execute("PRAGMA table_info(feedback_records)").fetchall()
    col_defs = []
    for col in info:
        parts = [col["name"], col["type"] or "TEXT"]
        if col["pk"]:
            parts.append("PRIMARY KEY AUTOINCREMENT" if (col["type"] or "").upper() == "INTEGER" else "PRIMARY KEY")
        else:
            if col["notnull"]:
                parts.append("NOT NULL")
            if col["dflt_value"] is not None:
                parts.append(f"DEFAULT {col['dflt_value']}")
        col_defs.append(" ".join(parts))
    col_list = ", ".join(col["name"] for col in info)
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute(
            "CREATE TABLE feedback_records__mig (\n  "
            + ",\n  ".join(col_defs)
            + ",\n  FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE\n)"
        )
        conn.execute(
            f"INSERT INTO feedback_records__mig ({col_list}) SELECT {col_list} FROM feedback_records"
        )
        conn.execute("DROP TABLE feedback_records")
        conn.execute("ALTER TABLE feedback_records__mig RENAME TO feedback_records")
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def init_feedback_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    record_cols = {r["name"] for r in conn.execute("PRAGMA table_info(feedback_records)")}
    for col, defn in (("responses", "TEXT"), ("template_id", "INTEGER"), ("publication_id", "INTEGER")):
        if col not in record_cols:
            conn.execute(f"ALTER TABLE feedback_records ADD COLUMN {col} {defn}")
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feedback_forms" in tables:
        forms = conn.execute("SELECT * FROM feedback_forms").fetchall()
        for form in forms:
            existing = conn.execute(
                "SELECT id FROM feedback_templates WHERE store_id = ? AND name = ?",
                (form["store_id"], form["name"]),
            ).fetchone()
            if existing:
                tid = existing["id"]
            else:
                blocks = json.dumps(preset_blocks(form["feedback_type"] or "review"))
                cur = conn.execute(
                    """INSERT INTO feedback_templates (store_id, name, description, feedback_type, blocks, status, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (form["store_id"], form["name"], form["description"], form["feedback_type"] or "review",
                     blocks, form["status"] or "draft"),
                )
                tid = cur.lastrowid
            pub = conn.execute("SELECT id FROM feedback_publications WHERE pub_code = ?", (form["form_code"],)).fetchone()
            if not pub:
                conn.execute(
                    """INSERT INTO feedback_publications (template_id, store_id, channel_type, pub_code, name, status, scan_count)
                       VALUES (?, ?, 'qr', ?, ?, ?, ?)""",
                    (tid, form["store_id"], form["form_code"], form["name"], form["status"] or "draft", form["scan_count"] or 0),
                )
        conn.execute("DROP TABLE IF EXISTS feedback_forms")
    # Dropping feedback_forms leaves a dangling FK on older feedback_records schemas.
    _strip_legacy_feedback_forms_fk(conn)
    for store in conn.execute("SELECT id FROM stores").fetchall():
        exists = conn.execute("SELECT 1 FROM feedback_settings WHERE store_id = ?", (store["id"],)).fetchone()
        if not exists:
            conn.execute("INSERT INTO feedback_settings (store_id) VALUES (?)", (store["id"],))


def register_feedback_platform(app) -> None:
    from app import (
        current_user, db, entity_qr_payload, get_store_or_404, login_required,
        regenerate_entity_code, require_store_owner, save_uploaded_image, unique_entity_code,
    )

    def log_activity(conn, feedback_id, action, detail="", actor="system"):
        conn.execute(
            "INSERT INTO feedback_activity (feedback_id, action, detail, actor) VALUES (?, ?, ?, ?)",
            (feedback_id, action, detail, actor),
        )
        row = conn.execute(
            """SELECT fr.id, fr.rating, fr.comment, fr.customer_id, s.id AS store_id, s.workspace_id, s.owner_id
               FROM feedback_records fr JOIN stores s ON s.id = fr.store_id WHERE fr.id=?""",
            (feedback_id,),
        ).fetchone()
        if row:
            from bos.events import emit, event_type as ev_type
            verb = action if action in ("submitted", "replied", "viewed", "archived", "deleted") else "updated"
            emit(
                conn,
                ev_type("feedback", verb),
                "feedback",
                feedback_id,
                workspace_id=row["workspace_id"],
                store_id=row["store_id"],
                user_id=row["owner_id"] if actor == "owner" else None,
                actor=actor,
                title="Feedback submitted" if action == "submitted" else f"Feedback {action}",
                detail=detail or (row["comment"] or "")[:120],
                metadata={"rating": row["rating"], "customer_id": row["customer_id"], "owner_id": row["owner_id"]},
                href="/app/feedback",
            )

    def get_settings(store_id):
        with db() as conn:
            row = conn.execute("SELECT * FROM feedback_settings WHERE store_id = ?", (store_id,)).fetchone()
            if not row:
                conn.execute("INSERT INTO feedback_settings (store_id) VALUES (?)", (store_id,))
                row = conn.execute("SELECT * FROM feedback_settings WHERE store_id = ?", (store_id,)).fetchone()
        return row

    def publication_by_code(code: str):
        with db() as conn:
            return conn.execute(
                """SELECT p.*, t.name AS template_name, t.blocks, t.feedback_type, t.thank_you_message,
                          s.name AS store_name, s.slug AS store_slug
                   FROM feedback_publications p
                   JOIN feedback_templates t ON t.id = p.template_id
                   JOIN stores s ON s.id = p.store_id
                   WHERE p.pub_code = ?""",
                (code.lower(),),
            ).fetchone()

    def store_templates(store_id):
        with db() as conn:
            return conn.execute(
                "SELECT * FROM feedback_templates WHERE store_id = ? ORDER BY updated_at DESC, id DESC",
                (store_id,),
            ).fetchall()

    def get_template_or_404(store_id, template_id):
        with db() as conn:
            row = conn.execute("SELECT * FROM feedback_templates WHERE id = ? AND store_id = ?", (template_id, store_id)).fetchone()
        if not row:
            abort(404)
        return row

    def delete_template(store_id, template_id):
        get_template_or_404(store_id, template_id)
        with db() as conn:
            conn.execute("DELETE FROM feedback_publications WHERE template_id=?", (template_id,))
            conn.execute(
                "UPDATE feedback_records SET template_id=NULL, publication_id=NULL WHERE template_id=?",
                (template_id,),
            )
            conn.execute("DELETE FROM feedback_templates WHERE id=? AND store_id=?", (template_id, store_id))

    def template_publications(template_id):
        with db() as conn:
            return conn.execute(
                "SELECT * FROM feedback_publications WHERE template_id = ? ORDER BY id DESC", (template_id,),
            ).fetchall()

    def get_feedback_or_404(store_id, feedback_id):
        with db() as conn:
            row = conn.execute("SELECT * FROM feedback_records WHERE id = ? AND store_id = ?", (feedback_id, store_id)).fetchone()
        if not row:
            abort(404)
        return row

    def feedback_tags_for_owner(owner_id):
        with db() as conn:
            return conn.execute("SELECT * FROM feedback_tags WHERE owner_id = ? ORDER BY name", (owner_id,)).fetchall()

    def feedback_record_tags(feedback_id):
        with db() as conn:
            return conn.execute(
                """SELECT ft.* FROM feedback_tags ft JOIN feedback_record_tags frt ON frt.tag_id = ft.id
                   WHERE frt.feedback_id = ?""", (feedback_id,),
            ).fetchall()

    def feedback_activity_list(feedback_id):
        with db() as conn:
            return conn.execute(
                "SELECT * FROM feedback_activity WHERE feedback_id = ? ORDER BY created_at DESC", (feedback_id,),
            ).fetchall()

    def list_feedback_records(store_id, owner_id, filters=None):
        filters = filters or {}
        query = """SELECT fr.*, s.name AS store_name, s.slug AS store_slug,
                          t.name AS template_name
                   FROM feedback_records fr
                   JOIN stores s ON s.id = fr.store_id
                   LEFT JOIN feedback_templates t ON t.id = fr.template_id
                   WHERE s.owner_id = ?"""
        params = [owner_id]
        if store_id:
            query += " AND fr.store_id = ?"
            params.append(store_id)
        if filters.get("status"):
            query += " AND fr.status = ?"
            params.append(filters["status"])
        ftype = filters.get("type") or filters.get("feedback_type")
        if ftype:
            query += " AND fr.feedback_type = ?"
            params.append(ftype)
        src = filters.get("source") or filters.get("source_type")
        if src:
            query += " AND fr.source_type = ?"
            params.append(src)
        if filters.get("rating"):
            query += " AND fr.rating = ?"
            params.append(int(filters["rating"]))
        if filters.get("has_reply") == "yes":
            query += " AND fr.owner_reply IS NOT NULL AND fr.owner_reply != ''"
        elif filters.get("has_reply") == "no":
            query += " AND (fr.owner_reply IS NULL OR fr.owner_reply = '')"
        if filters.get("q"):
            like = f"%{filters['q']}%"
            query += " AND (fr.comment LIKE ? OR fr.responses LIKE ? OR fr.customer_name LIKE ?)"
            params.extend([like, like, like])
        query += " ORDER BY fr.created_at DESC LIMIT 500"
        with db() as conn:
            return conn.execute(query, params).fetchall()

    def feedback_analytics(owner_id, store_id=None):
        base = "FROM feedback_records fr JOIN stores s ON s.id = fr.store_id WHERE s.owner_id = ?"
        params = [owner_id]
        if store_id:
            base += " AND fr.store_id = ?"
            params.append(store_id)
        with db() as conn:
            total = conn.execute(f"SELECT COUNT(*) AS c {base}", params).fetchone()["c"]
            avg = conn.execute(f"SELECT AVG(rating) AS avg {base} AND fr.rating IS NOT NULL", params).fetchone()["avg"]
            replied = conn.execute(
                f"SELECT COUNT(*) AS c {base} AND fr.owner_reply IS NOT NULL AND fr.owner_reply != ''", params,
            ).fetchone()["c"]
            pending = conn.execute(
                f"SELECT COUNT(*) AS c {base} AND (fr.owner_reply IS NULL OR fr.owner_reply = '') AND fr.status NOT IN ('archived','hidden')",
                params,
            ).fetchone()["c"]
            new_count = conn.execute(f"SELECT COUNT(*) AS c {base} AND fr.status = 'new'", params).fetchone()["c"]
            dist = conn.execute(
                f"SELECT fr.rating, COUNT(*) AS c {base} AND fr.rating IS NOT NULL GROUP BY fr.rating ORDER BY fr.rating DESC",
                params,
            ).fetchall()
            by_store = conn.execute(
                """SELECT s.name, COUNT(*) AS c, ROUND(AVG(fr.rating), 1) AS avg
                   FROM feedback_records fr JOIN stores s ON s.id = fr.store_id
                   WHERE s.owner_id = ? GROUP BY s.id ORDER BY c DESC LIMIT 10""", (owner_id,),
            ).fetchall()
            by_template = conn.execute(
                """SELECT COALESCE(t.name, 'Unknown') AS name, COUNT(*) AS c
                   FROM feedback_records fr
                   LEFT JOIN feedback_templates t ON t.id = fr.template_id
                   JOIN stores s ON s.id = fr.store_id
                   WHERE s.owner_id = ?""" + (" AND fr.store_id = ?" if store_id else "") +
                " GROUP BY fr.template_id ORDER BY c DESC LIMIT 10",
                params,
            ).fetchall()
            by_source = conn.execute(
                f"SELECT fr.source_type, COUNT(*) AS c {base} GROUP BY fr.source_type ORDER BY c DESC", params,
            ).fetchall()
            recent = conn.execute(
                f"SELECT fr.*, s.name AS store_name {base} ORDER BY fr.created_at DESC LIMIT 6", params,
            ).fetchall()
            activity = conn.execute(
                """SELECT fa.action, fa.detail, fa.created_at, fr.id AS feedback_id
                   FROM feedback_activity fa JOIN feedback_records fr ON fr.id = fa.feedback_id
                   JOIN stores s ON s.id = fr.store_id WHERE s.owner_id = ?
                   ORDER BY fa.created_at DESC LIMIT 10""", (owner_id,),
            ).fetchall()
        total = int(total or 0)
        reply_rate = round((replied / total) * 100) if total else 0
        return {
            "total": total, "average_rating": round(float(avg or 0), 1),
            "reply_rate": reply_rate, "pending_replies": int(pending or 0),
            "new_count": int(new_count or 0),
            "rating_distribution": {int(r["rating"]): int(r["c"]) for r in dist if r["rating"]},
            "by_store": [dict(r) for r in by_store],
            "by_template": [dict(r) for r in by_template],
            "by_source": [dict(r) for r in by_source],
            "recent": [dict(r) for r in recent],
            "recent_activity": [dict(r) for r in activity],
        }

    def parse_blocks(row):
        try:
            return json.loads(row["blocks"] or "[]")
        except json.JSONDecodeError:
            _log.debug("feedback_blocks_parse_failed", exc_info=True, extra={"op": "parse_blocks"})
            return []

    def extract_from_responses(responses: dict, blocks: list) -> dict:
        out = {"rating": None, "comment": "", "title": "", "attachments": [], "customer_name": "", "customer_email": ""}
        for block in blocks:
            bid = block["id"]
            val = responses.get(bid)
            if val is None:
                continue
            btype = block.get("type")
            if btype == "rating":
                try:
                    out["rating"] = int(val)
                except (TypeError, ValueError):
                    _log.debug("feedback_rating_parse_failed", exc_info=True, extra={"op": "extract_from_responses"})
                    pass
            elif btype == "long_text" and not out["comment"]:
                out["comment"] = str(val)
            elif btype == "short_text":
                if not out["title"]:
                    out["title"] = str(val)
                elif not out["comment"]:
                    out["comment"] = str(val)
            elif btype == "email":
                out["customer_email"] = str(val)
            elif btype in ("image_upload", "file_upload") and val:
                out["attachments"].append(val)
        return out

    def record_to_api(row):
        responses = json.loads(row["responses"] or "{}") if row["responses"] else {}
        return {
            "id": row["id"], "store_id": row["store_id"],
            "store_name": row["store_name"] if "store_name" in row.keys() else None,
            "template_name": row["template_name"] if "template_name" in row.keys() else None,
            "feedback_type": row["feedback_type"], "source_type": row["source_type"],
            "rating": row["rating"], "comment": row["comment"], "responses": responses,
            "attachments": json.loads(row["attachments"] or "[]"),
            "customer_name": None if row["is_anonymous"] else row["customer_name"],
            "customer_id": row["customer_id"] if "customer_id" in row.keys() else None,
            "is_anonymous": bool(row["is_anonymous"]), "status": row["status"],
            "owner_reply": row["owner_reply"], "created_at": row["created_at"],
            "tags": [dict(t) for t in feedback_record_tags(row["id"])],
        }

    def fb_ctx(store, section):
        return {
            "store": store, "fb_section": section,
            "feedback_statuses": FEEDBACK_STATUSES,
            "feedback_types": FEEDBACK_TYPES,
        }

    # --- Customer ---

    @app.get("/feedback/<code>")
    def feedback_submit_view(code):
        pub = publication_by_code(code)
        if not pub or pub["status"] == "archived":
            abort(404)
        template_status = get_template_or_404(pub["store_id"], pub["template_id"])["status"]
        if template_status == "archived":
            abort(404)
        blocks = parse_blocks(pub)
        settings = get_settings(pub["store_id"])
        return render_template(
            "customer/feedback_experience.html",
            publication=pub, blocks=blocks, settings=settings,
            submitted=False, preview_mode=False,
        )

    @app.route("/feedback/<code>", methods=["POST"])
    def feedback_submit_post(code):
        pub = publication_by_code(code)
        if not pub or pub["status"] != "active":
            abort(404)
        template = get_template_or_404(pub["store_id"], pub["template_id"])
        if template["status"] != "published":
            abort(404)
        settings = get_settings(pub["store_id"])
        blocks = parse_blocks(pub)
        is_anonymous = request.form.get("is_anonymous") == "1"
        if not settings["anonymous_allowed"] and is_anonymous:
            flash("Anonymous feedback is not allowed.", "error")
            return redirect(url_for("feedback_submit_view", code=code))
        responses = {}
        attachments = []
        for block in blocks:
            bid = block["id"]
            btype = block["type"]
            if btype in ("heading", "description", "divider", "section"):
                continue
            key = f"field_{bid}"
            if btype == "multiple_choice":
                responses[bid] = request.form.getlist(key)
            elif btype == "image_upload":
                try:
                    uploaded = save_uploaded_image(key)
                    if uploaded:
                        responses[bid] = uploaded
                        attachments.append(uploaded)
                except ValueError as exc:
                    flash(str(exc), "error")
                    return redirect(url_for("feedback_submit_view", code=code))
            else:
                val = request.form.get(key, "").strip()
                if block.get("required") and not val:
                    flash(f"Please complete: {block.get('label', 'required field')}", "error")
                    return redirect(url_for("feedback_submit_view", code=code))
                if val:
                    responses[bid] = val
        extracted = extract_from_responses(responses, blocks)
        with db() as conn:
            store_row = conn.execute("SELECT owner_id FROM stores WHERE id=?", (pub["store_id"],)).fetchone()
            owner_id = store_row["owner_id"] if store_row else None
            customer_id = None
            if not is_anonymous and owner_id:
                from customer_platform import find_or_create_customer, log_customer_activity
                customer_id = find_or_create_customer(
                    conn, owner_id,
                    email=extracted["customer_email"] or request.form.get("customer_email"),
                    full_name=extracted["customer_name"] or request.form.get("customer_name"),
                    store_id=pub["store_id"],
                    source=pub["channel_type"] or "qr",
                )
            cur = conn.execute(
                """INSERT INTO feedback_records
                   (store_id, template_id, publication_id, feedback_type, source_type, source_ref,
                    rating, title, comment, responses, attachments, customer_name, customer_email,
                    customer_id, is_anonymous, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', CURRENT_TIMESTAMP)""",
                (
                    pub["store_id"], pub["template_id"], pub["id"], template["feedback_type"],
                    pub["channel_type"], code, extracted["rating"], extracted["title"],
                    extracted["comment"], json.dumps(responses), json.dumps(attachments),
                    "" if is_anonymous else (extracted["customer_name"] or request.form.get("customer_name", "")),
                    "" if is_anonymous else (extracted["customer_email"] or request.form.get("customer_email", "")),
                    customer_id,
                    1 if is_anonymous else 0,
                ),
            )
            feedback_id = cur.lastrowid
            feedback_row = conn.execute("SELECT * FROM feedback_records WHERE id=?", (feedback_id,)).fetchone()
            from bos.responses import record_response_from_feedback
            record_response_from_feedback(conn, feedback_row)
            log_activity(conn, feedback_id, "submitted", "Feedback submitted", "customer")
            conn.execute("UPDATE feedback_publications SET scan_count = COALESCE(scan_count,0)+1 WHERE id=?", (pub["id"],))
        blocks = parse_blocks(pub)
        return render_template(
            "customer/feedback_experience.html",
            publication=pub, blocks=blocks, settings=settings,
            submitted=True, preview_mode=False,
            thank_you=template["thank_you_message"] or settings["thank_you_message"],
        )

    @app.get("/manage/<slug>/preview/feedback/<code>")
    @login_required
    def feedback_owner_preview(slug, code):
        store = get_store_or_404(slug)
        require_store_owner(store)
        pub = publication_by_code(code)
        if not pub or pub["store_slug"] != slug:
            abort(404)
        return render_template(
            "customer/feedback_experience.html",
            publication=pub, blocks=parse_blocks(pub), settings=get_settings(store["id"]),
            submitted=False, preview_mode=True,
        )

    # --- Owner: Overview ---

    @app.get("/manage/<slug>/feedback")
    @login_required
    def manage_feedback_overview(slug):
        store = get_store_or_404(slug)
        require_store_owner(store)
        analytics = feedback_analytics(current_user()["id"], store["id"])
        return render_template("owner/feedback_overview.html", **fb_ctx(store, "overview"), analytics=analytics)

    # --- Templates ---

    @app.route("/manage/<slug>/feedback/templates", methods=["GET", "POST"])
    @login_required
    def manage_feedback_templates(slug):
        store = get_store_or_404(slug)
        require_store_owner(store)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "create":
                ftype = request.form.get("feedback_type", "review")
                blocks = preset_blocks("custom" if ftype == "custom" else ftype)
                if ftype == "custom":
                    blocks = [{"id": _block_id(), "type": "heading", "label": "Your feedback"}]
                with db() as conn:
                    conn.execute(
                        """INSERT INTO feedback_templates (store_id, name, feedback_type, blocks, status, updated_at)
                           VALUES (?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                        (store["id"], request.form.get("name", "").strip() or "Untitled template", ftype, json.dumps(blocks)),
                    )
                flash("Template created.", "success")
            elif action == "duplicate":
                tid = request.form.get("template_id", type=int)
                tpl = get_template_or_404(store["id"], tid)
                with db() as conn:
                    conn.execute(
                        """INSERT INTO feedback_templates (store_id, name, description, feedback_type, blocks, thank_you_message, status, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP)""",
                        (store["id"], f"{tpl['name']} (copy)", tpl["description"], tpl["feedback_type"],
                         tpl["blocks"], tpl["thank_you_message"]),
                    )
                flash("Template duplicated.", "success")
            elif action == "archive":
                tid = request.form.get("template_id", type=int)
                with db() as conn:
                    conn.execute("UPDATE feedback_templates SET status='archived', updated_at=CURRENT_TIMESTAMP WHERE id=? AND store_id=?", (tid, store["id"]))
                flash("Template archived.", "success")
            elif action == "delete":
                tid = request.form.get("template_id", type=int)
                delete_template(store["id"], tid)
                flash("Template deleted.", "success")
        templates = store_templates(store["id"])
        return render_template(
            "owner/feedback_templates.html", **fb_ctx(store, "templates"),
            templates=templates, library=TEMPLATE_LIBRARY, block_types=BLOCK_TYPES,
        )

    @app.route("/manage/<slug>/feedback/templates/<int:template_id>", methods=["GET", "POST"])
    @login_required
    def manage_feedback_builder(slug, template_id):
        store = get_store_or_404(slug)
        require_store_owner(store)
        template = get_template_or_404(store["id"], template_id)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "save":
                blocks_json = request.form.get("blocks_json", "[]")
                with db() as conn:
                    conn.execute(
                        """UPDATE feedback_templates SET name=?, description=?, feedback_type=?,
                           blocks=?, thank_you_message=?, status=?, updated_at=CURRENT_TIMESTAMP
                           WHERE id=? AND store_id=?""",
                        (
                            request.form.get("name", template["name"]).strip(),
                            request.form.get("description", "").strip(),
                            request.form.get("feedback_type", template["feedback_type"]),
                            blocks_json, request.form.get("thank_you_message", "").strip(),
                            request.form.get("status", template["status"]),
                            template_id, store["id"],
                        ),
                    )
                flash("Template saved.", "success")
            elif action == "delete":
                delete_template(store["id"], template_id)
                flash("Template deleted.", "success")
                return redirect(url_for("manage_feedback_templates", slug=slug))
            return redirect(url_for("manage_feedback_builder", slug=slug, template_id=template_id))
        return render_template(
            "owner/feedback_builder.html", **fb_ctx(store, "templates"),
            template=template, blocks=parse_blocks(template),
            block_types=BLOCK_TYPES, publications=template_publications(template_id),
        )

    @app.route("/manage/<slug>/feedback/templates/<int:template_id>/publish", methods=["GET", "POST"])
    @login_required
    def manage_feedback_publish(slug, template_id):
        store = get_store_or_404(slug)
        require_store_owner(store)
        template = get_template_or_404(store["id"], template_id)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "publish_template":
                with db() as conn:
                    conn.execute(
                        "UPDATE feedback_templates SET status='published', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (template_id,),
                    )
                flash("Template published.", "success")
            elif action == "create_publication":
                channel = request.form.get("channel_type", "qr")
                if channel not in PUBLISH_CHANNELS:
                    channel = "qr"
                with db() as conn:
                    code = unique_entity_code(conn, "feedback_publications", "pub_code")
                    conn.execute(
                        """INSERT INTO feedback_publications (template_id, store_id, channel_type, pub_code, name, status)
                           VALUES (?, ?, ?, ?, ?, 'active')""",
                        (template_id, store["id"], channel, code,
                         request.form.get("name", "").strip() or f"{template['name']} — {channel}"),
                    )
                    if template["status"] == "draft":
                        conn.execute("UPDATE feedback_templates SET status='published', updated_at=CURRENT_TIMESTAMP WHERE id=?", (template_id,))
                flash("Publication created.", "success")
            elif action == "regenerate":
                pub_id = request.form.get("publication_id", type=int)
                with db() as conn:
                    regenerate_entity_code(conn, "feedback_publications", pub_id, store["id"])
                flash("Link regenerated.", "success")
            return redirect(url_for("manage_feedback_publish", slug=slug, template_id=template_id))
        pubs = template_publications(template_id)
        pub_payloads = []
        for p in pubs:
            pub_payloads.append({"pub": p, "qr": entity_qr_payload("feedback_submit_view", p["pub_code"])})
        return render_template(
            "owner/feedback_publish.html", **fb_ctx(store, "templates"),
            template=template, publications=pub_payloads, channels=PUBLISH_CHANNELS,
        )

    # --- Inbox ---

    @app.route("/manage/<slug>/feedback/inbox", methods=["GET", "POST"])
    @login_required
    def manage_feedback_inbox(slug):
        store = get_store_or_404(slug)
        require_store_owner(store)
        owner_id = current_user()["id"]
        if request.method == "POST" and request.form.get("action") == "batch_status":
            ids = [int(v) for v in request.form.get("feedback_ids", "").split(",") if v.isdigit()]
            status = request.form.get("status", "read")
            if ids and status in FEEDBACK_STATUSES:
                ph = ",".join("?" * len(ids))
                with db() as conn:
                    conn.execute(
                        f"UPDATE feedback_records SET status=?, updated_at=CURRENT_TIMESTAMP WHERE store_id=? AND id IN ({ph})",
                        [status, store["id"], *ids],
                    )
                    for fid in ids:
                        log_activity(conn, fid, "status_changed", f"→ {status}", "owner")
                flash(f"Updated {len(ids)} record(s).", "success")
        filters = {
            "status": request.args.get("status", ""), "type": request.args.get("type", ""),
            "source_type": request.args.get("source", ""), "rating": request.args.get("rating", ""),
            "has_reply": request.args.get("has_reply", ""), "q": request.args.get("q", "").strip(),
        }
        records = list_feedback_records(store["id"], owner_id, filters)
        tags = feedback_tags_for_owner(owner_id)
        return render_template(
            "owner/feedback_inbox.html", **fb_ctx(store, "inbox"),
            records=records, filters=filters, tags=tags,
        )

    @app.route("/manage/<slug>/feedback/inbox/<int:feedback_id>", methods=["GET", "POST"])
    @login_required
    def manage_feedback_detail(slug, feedback_id):
        store = get_store_or_404(slug)
        require_store_owner(store)
        record = get_feedback_or_404(store["id"], feedback_id)
        if request.method == "POST":
            action = request.form.get("action")
            with db() as conn:
                if action == "reply":
                    reply = request.form.get("owner_reply", "").strip()
                    conn.execute(
                        """UPDATE feedback_records SET owner_reply=?, owner_reply_at=CURRENT_TIMESTAMP,
                           status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (reply, "replied" if reply else record["status"], feedback_id),
                    )
                    log_activity(conn, feedback_id, "replied", "Owner reply", "owner")
                    flash("Reply saved.", "success")
                elif action == "status":
                    st = request.form.get("status")
                    if st in FEEDBACK_STATUSES:
                        conn.execute("UPDATE feedback_records SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (st, feedback_id))
                        log_activity(conn, feedback_id, "status_changed", st, "owner")
                elif action == "delete":
                    conn.execute("DELETE FROM feedback_activity WHERE feedback_id=?", (feedback_id,))
                    conn.execute("DELETE FROM feedback_record_tags WHERE feedback_id=?", (feedback_id,))
                    conn.execute("DELETE FROM feedback_records WHERE id=?", (feedback_id,))
                    flash("Deleted.", "success")
                    return redirect(url_for("manage_feedback_inbox", slug=slug))
            return redirect(url_for("manage_feedback_detail", slug=slug, feedback_id=feedback_id))
        if record["status"] == "new":
            with db() as conn:
                conn.execute("UPDATE feedback_records SET status='read', updated_at=CURRENT_TIMESTAMP WHERE id=?", (feedback_id,))
                log_activity(conn, feedback_id, "viewed", "Opened", "owner")
            record = get_feedback_or_404(store["id"], feedback_id)
        template = None
        blocks = []
        if record["template_id"]:
            try:
                template = get_template_or_404(store["id"], record["template_id"])
                blocks = parse_blocks(template)
            except Exception:
                logging.getLogger("app.feedback").error("feedback_template_load_failed", exc_info=True)  # SUSPECT: swallow may hide bug — see Phase 1.1
        responses = json.loads(record["responses"] or "{}")
        return render_template(
            "owner/feedback_detail.html", **fb_ctx(store, "inbox"),
            record=record, responses=responses, blocks=blocks, template=template,
            attachments=json.loads(record["attachments"] or "[]"),
            activity=feedback_activity_list(feedback_id),
            record_tag_ids=[t["id"] for t in feedback_record_tags(feedback_id)],
            all_tags=feedback_tags_for_owner(current_user()["id"]),
        )

    @app.get("/manage/<slug>/feedback/export")
    @login_required
    def export_feedback(slug):
        store = get_store_or_404(slug)
        require_store_owner(store)
        records = list_feedback_records(store["id"], current_user()["id"], {})
        lines = ["id,rating,status,type,source,responses,created_at"]
        for r in records:
            resp = (r["responses"] or "").replace('"', '""')
            lines.append(f'{r["id"]},{r["rating"] or ""},{r["status"]},{r["feedback_type"]},{r["source_type"]},"{resp}",{r["created_at"]}')
        return app.response_class("\n".join(lines), mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{store["slug"]}-feedback.csv"'})

    # --- Analytics ---

    @app.get("/manage/<slug>/feedback/analytics")
    @login_required
    def manage_feedback_analytics(slug):
        store = get_store_or_404(slug)
        require_store_owner(store)
        analytics = feedback_analytics(current_user()["id"], store["id"])
        return render_template("owner/feedback_analytics.html", **fb_ctx(store, "analytics"), analytics=analytics)

    # --- Settings ---

    @app.route("/manage/<slug>/feedback/settings", methods=["GET", "POST"])
    @login_required
    def manage_feedback_settings(slug):
        store = get_store_or_404(slug)
        require_store_owner(store)
        settings = get_settings(store["id"])
        if request.method == "POST":
            with db() as conn:
                conn.execute(
                    """UPDATE feedback_settings SET anonymous_allowed=?, require_login=?,
                       notify_new=?, notify_negative=?, thank_you_message=?, auto_close_days=?
                       WHERE store_id=?""",
                    (
                        1 if request.form.get("anonymous_allowed") == "1" else 0,
                        1 if request.form.get("require_login") == "1" else 0,
                        1 if request.form.get("notify_new") == "1" else 0,
                        1 if request.form.get("notify_negative") == "1" else 0,
                        request.form.get("thank_you_message", "").strip(),
                        request.form.get("auto_close_days", type=int) or 0,
                        store["id"],
                    ),
                )
            flash("Settings saved.", "success")
            return redirect(url_for("manage_feedback_settings", slug=slug))
        return render_template(
            "owner/feedback_settings.html", **fb_ctx(store, "settings"),
            settings=get_settings(store["id"]), templates=store_templates(store["id"]),
        )

    # --- API ---

    @app.get("/api/feedback/summary")
    @login_required
    def api_feedback_summary():
        return jsonify(feedback_analytics(current_user()["id"], request.args.get("store_id", type=int)))

    @app.get("/api/feedback/records")
    @login_required
    def api_feedback_records():
        filters = {"status": request.args.get("status", ""), "type": request.args.get("type", ""),
                   "source_type": request.args.get("source", ""), "q": request.args.get("q", "").strip()}
        rows = list_feedback_records(request.args.get("store_id", type=int), current_user()["id"], filters)
        return jsonify([record_to_api(r) for r in rows])

    @app.get("/api/feedback/records/<int:feedback_id>")
    @login_required
    def api_feedback_record_detail(feedback_id):
        with db() as conn:
            row = conn.execute(
                """SELECT fr.*, s.name AS store_name, t.name AS template_name
                   FROM feedback_records fr JOIN stores s ON s.id=fr.store_id
                   LEFT JOIN feedback_templates t ON t.id=fr.template_id
                   WHERE fr.id=? AND s.owner_id=?""",
                (feedback_id, current_user()["id"]),
            ).fetchone()
        if not row:
            abort(404)
        payload = record_to_api(row)
        payload["activity"] = [dict(a) for a in feedback_activity_list(feedback_id)]
        return jsonify(payload)

    @app.post("/api/feedback/records/<int:feedback_id>/reply")
    @login_required
    def api_feedback_reply(feedback_id):
        reply = (request.get_json(silent=True) or {}).get("reply", "").strip()
        with db() as conn:
            row = conn.execute(
                "SELECT fr.id FROM feedback_records fr JOIN stores s ON s.id=fr.store_id WHERE fr.id=? AND s.owner_id=?",
                (feedback_id, current_user()["id"]),
            ).fetchone()
            if not row:
                abort(404)
            conn.execute(
                "UPDATE feedback_records SET owner_reply=?, owner_reply_at=CURRENT_TIMESTAMP, status='replied', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (reply, feedback_id),
            )
            log_activity(conn, feedback_id, "replied", "BOS reply", "owner")
        return jsonify({"ok": True})

    app.feedback_form_by_code = publication_by_code

    # Legacy route redirects
    @app.route("/manage/<slug>/feedback/forms/<int:form_id>")
    @login_required
    def legacy_form_redirect(slug, form_id):
        return redirect(url_for("manage_feedback_builder", slug=slug, template_id=form_id))
