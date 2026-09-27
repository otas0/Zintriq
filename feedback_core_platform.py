"""Feedback & Reputation Core — BOS workspace feedback, surveys, and plugin layer."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from flask import abort, jsonify, redirect, render_template, request, session, url_for

from integration_catalog import REPUTATION_PLUGINS as CATALOG_REPUTATION

_log = logging.getLogger("app.feedback")

FEEDBACK_SOURCES = (
    "business_os", "qr_survey",
    *(p["slug"] for p in CATALOG_REPUTATION),
)
FEEDBACK_TYPES = ("review", "survey_response", "rating", "comment", "complaint", "suggestion")
FEEDBACK_STATUSES = ("new", "read", "replied", "archived", "hidden", "flagged")
QUESTION_TYPES = ("single_choice", "multiple_choice", "text", "rating", "nps")
SURVEY_STATUSES = ("draft", "published", "archived")

REPUTATION_PLUGINS = tuple(
    {"slug": p["slug"], "name": p["name"], "capabilities": p.get("capabilities", ())}
    for p in CATALOG_REPUTATION
)

REMOVED_REPUTATION_SLUGS = ("google_business",)

CORE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS surveys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    pub_code TEXT UNIQUE,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_surveys_workspace ON surveys(workspace_id);

CREATE TABLE IF NOT EXISTS survey_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    question TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    options TEXT DEFAULT '[]',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(survey_id) REFERENCES surveys(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_survey_questions_survey ON survey_questions(survey_id, sort_order);

CREATE TABLE IF NOT EXISTS survey_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    customer_id INTEGER,
    feedback_id INTEGER,
    submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(survey_id) REFERENCES surveys(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_survey_responses_survey ON survey_responses(survey_id);

CREATE TABLE IF NOT EXISTS survey_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    answer TEXT,
    FOREIGN KEY(response_id) REFERENCES survey_responses(id) ON DELETE CASCADE,
    FOREIGN KEY(question_id) REFERENCES survey_questions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_survey_answers_response ON survey_answers(response_id);

CREATE TABLE IF NOT EXISTS external_feedback_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'synced',
    last_synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, external_id),
    FOREIGN KEY(feedback_id) REFERENCES feedback_records(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ext_feedback_platform ON external_feedback_mappings(platform);

CREATE TABLE IF NOT EXISTS feedback_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    customer_id INTEGER,
    booking_id INTEGER,
    check_in_id INTEGER,
    survey_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_feedback_requests_ws ON feedback_requests(workspace_id, status);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _pub_code() -> str:
    return uuid.uuid4().hex[:12]


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _migrate_feedback_records(conn) -> None:
    for col, typedef in (
        ("customer_id", "INTEGER"),
        ("external_platform", "TEXT"),
        ("external_id", "TEXT"),
        ("language", "TEXT DEFAULT ''"),
        ("source", "TEXT"),
    ):
        if not _column_exists(conn, "feedback_records", col):
            conn.execute(f"ALTER TABLE feedback_records ADD COLUMN {col} {typedef}")
    conn.execute(
        """UPDATE feedback_records SET source=source_type
           WHERE (source IS NULL OR source='') AND source_type IS NOT NULL"""
    )


def init_feedback_core_tables(conn) -> None:
    conn.executescript(CORE_SCHEMA_SQL)
    _migrate_feedback_records(conn)
    from integration_platform import purge_removed_plugins
    purge_removed_plugins(conn)
    for slug in REMOVED_REPUTATION_SLUGS:
        conn.execute(
            """DELETE FROM user_integration_connections
               WHERE plugin_id IN (SELECT id FROM integration_plugins WHERE slug=?)""",
            (slug,),
        )
        conn.execute("DELETE FROM integration_plugins WHERE slug=?", (slug,))
    for p in REPUTATION_PLUGINS:
        conn.execute(
            """INSERT INTO integration_plugins (slug, name, provider, description, category, status)
               VALUES (?, ?, ?, ?, 'reputation', 'available')
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name,
                 description=excluded.description,
                 updated_at=CURRENT_TIMESTAMP""",
            (p["slug"], p["name"], p["slug"], f"Sync reviews from {p['name']}"),
        )


def maybe_create_feedback_request(
    conn,
    *,
    workspace_id: int,
    customer_id: int | None = None,
    booking_id: int | None = None,
    check_in_id: int | None = None,
) -> int | None:
    """Create a pending feedback request after booking/check-in completion."""
    if booking_id:
        existing = conn.execute(
            "SELECT id FROM feedback_requests WHERE workspace_id=? AND booking_id=? AND status='pending'",
            (workspace_id, booking_id),
        ).fetchone()
        if existing:
            return int(existing["id"])
    if check_in_id:
        existing = conn.execute(
            "SELECT id FROM feedback_requests WHERE workspace_id=? AND check_in_id=? AND status='pending'",
            (workspace_id, check_in_id),
        ).fetchone()
        if existing:
            return int(existing["id"])
    pub = conn.execute(
        "SELECT id FROM surveys WHERE workspace_id=? AND status='published' ORDER BY id LIMIT 1",
        (workspace_id,),
    ).fetchone()
    survey_id = int(pub["id"]) if pub else None
    cur = conn.execute(
        """INSERT INTO feedback_requests
           (workspace_id, customer_id, booking_id, check_in_id, survey_id, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (workspace_id, customer_id, booking_id, check_in_id, survey_id),
    )
    return int(cur.lastrowid)


def _submit_survey_response(conn, survey_id: int, data: dict, *, experience_id: int | None = None) -> tuple[int, int]:
    """Create survey response + linked feedback record. Returns (feedback_id, response_id)."""
    survey = conn.execute(
        "SELECT * FROM surveys WHERE id=? AND status='published'", (survey_id,)
    ).fetchone()
    if not survey:
        abort(404)
    ws = int(survey["workspace_id"])
    answers = data.get("answers") or {}
    rating = None
    comment_parts = []
    questions = conn.execute(
        "SELECT * FROM survey_questions WHERE survey_id=? ORDER BY sort_order", (survey_id,)
    ).fetchall()
    for q in questions:
        val = answers.get(str(q["id"])) or answers.get(q["id"])
        if val is None:
            continue
        if q["type"] in ("rating", "nps"):
            try:
                rating = int(val)
            except (TypeError, ValueError):
                _log.debug("survey_rating_parse_failed", exc_info=True, extra={"op": "_submit_survey_response"})
                pass
        elif q["type"] == "text":
            comment_parts.append(str(val))
    store = conn.execute("SELECT id FROM stores WHERE workspace_id=? LIMIT 1", (ws,)).fetchone()
    if not store:
        abort(400)
    cur = conn.execute(
        """INSERT INTO feedback_records
           (store_id, workspace_id, feedback_type, source_type, source,
            rating, comment, customer_id, customer_name, status, updated_at)
           VALUES (?, ?, 'survey_response', 'qr_survey', 'qr_survey', ?, ?, ?, ?, 'new', ?)""",
        (
            store["id"], ws, rating, "\n".join(comment_parts),
            data.get("customer_id"), data.get("customer_name"), _now(),
        ),
    )
    fid = int(cur.lastrowid)
    feedback_row = conn.execute("SELECT * FROM feedback_records WHERE id=?", (fid,)).fetchone()
    from bos.responses import record_response_from_feedback
    record_response_from_feedback(
        conn, feedback_row, experience_id=experience_id, answers=answers,
    )
    rcur = conn.execute(
        """INSERT INTO survey_responses (survey_id, workspace_id, customer_id, feedback_id)
           VALUES (?, ?, ?, ?)""",
        (survey_id, ws, data.get("customer_id"), fid),
    )
    rid = int(rcur.lastrowid)
    for q in questions:
        val = answers.get(str(q["id"])) or answers.get(q["id"])
        if val is not None:
            conn.execute(
                "INSERT INTO survey_answers (response_id, question_id, answer) VALUES (?, ?, ?)",
                (rid, q["id"], json.dumps(val) if isinstance(val, (list, dict)) else str(val)),
            )
    from bos.events import emit
    meta = {}
    if data.get("customer_id"):
        meta["customer_id"] = int(data["customer_id"])
    emit(conn, "feedback.submitted", "feedback", fid, workspace_id=ws,
         actor="customer", title="Survey response submitted", metadata=meta, href="/app/feedback")
    emit(conn, "survey.response_submitted", "survey", survey_id, workspace_id=ws,
         actor="customer", title="Survey response received", metadata={"feedback_id": fid})
    return fid, rid


def register_feedback_core_platform(app) -> None:
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
        if ws and not has_permission(conn, uid(), int(ws), permission):
            abort(403)

    def feedback_to_api(row, conn=None) -> dict:
        source = row["source"] if "source" in row.keys() and row["source"] else row["source_type"]
        payload = {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "customer_id": row["customer_id"] if "customer_id" in row.keys() else None,
            "source": source,
            "external_platform": row["external_platform"] if "external_platform" in row.keys() else None,
            "external_id": row["external_id"] if "external_id" in row.keys() else None,
            "rating": row["rating"],
            "content": row["comment"],
            "comment": row["comment"],
            "language": row["language"] if "language" in row.keys() else "",
            "status": row["status"],
            "feedback_type": row["feedback_type"],
            "related_entity_type": row["related_object_type"],
            "related_entity_id": row["related_object_id"],
            "customer_name": row["customer_name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "experience_id": None,
            "experience_name": "",
        }
        if conn:
            src = conn.execute(
                """SELECT x.id, x.name FROM qr_customer_interactions i
                   JOIN qr_experiences x ON x.id=i.experience_id
                   WHERE i.related_object_type='feedback' AND i.related_object_id=?
                   ORDER BY i.created_at DESC LIMIT 1""",
                (row["id"],),
            ).fetchone()
            if src:
                payload["experience_id"] = src["id"]
                payload["experience_name"] = src["name"]
        return payload

    def get_workspace_feedback(conn, feedback_id: int, workspace_id: int):
        row = conn.execute(
            "SELECT * FROM feedback_records WHERE id=? AND workspace_id=?",
            (feedback_id, workspace_id),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def _emit(conn, event_type, feedback_id, title, **kw):
        from bos.events import emit
        emit(conn, event_type, "feedback", feedback_id, workspace_id=ws_id(), user_id=uid(),
             actor="member", title=title, href=f"/app/feedback#feedback/{feedback_id}", **kw)

    def _survey_to_api(conn, row, include_questions=False) -> dict:
        payload = {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "pub_code": row["pub_code"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_questions:
            qs = conn.execute(
                "SELECT * FROM survey_questions WHERE survey_id=? ORDER BY sort_order, id",
                (row["id"],),
            ).fetchall()
            payload["questions"] = [
                {
                    "id": q["id"],
                    "type": q["type"],
                    "question": q["question"],
                    "required": bool(q["required"]),
                    "order": q["sort_order"],
                    "options": json.loads(q["options"] or "[]"),
                }
                for q in qs
            ]
        return payload

    @app.get("/api/feedback/dashboard")
    @login_required
    def api_feedback_dashboard():
        ws = ws_id()
        if not ws:
            return jsonify({"total": 0, "average_rating": 0, "response_rate": 0, "by_source": [], "recent": []})
        with db() as conn:
            _guard(conn, "feedback.read")
            base = "FROM feedback_records WHERE workspace_id=?"
            total = conn.execute(f"SELECT COUNT(*) AS c {base}", (ws,)).fetchone()["c"]
            avg = conn.execute(
                f"SELECT AVG(rating) AS a {base} AND rating IS NOT NULL", (ws,)
            ).fetchone()["a"]
            replied = conn.execute(
                f"SELECT COUNT(*) AS c {base} AND owner_reply IS NOT NULL AND owner_reply != ''", (ws,)
            ).fetchone()["c"]
            by_source = conn.execute(
                f"""SELECT COALESCE(source, source_type, 'business_os') AS src, COUNT(*) AS c,
                           ROUND(AVG(rating), 1) AS avg_rating
                    {base} GROUP BY src ORDER BY c DESC""",
                (ws,),
            ).fetchall()
            recent = conn.execute(
                f"SELECT * {base} ORDER BY created_at DESC LIMIT 20", (ws,)
            ).fetchall()
            pending_requests = conn.execute(
                "SELECT COUNT(*) AS c FROM feedback_requests WHERE workspace_id=? AND status='pending'",
                (ws,),
            ).fetchone()["c"]
        total = int(total or 0)
        return jsonify({
            "total": total,
            "average_rating": round(float(avg or 0), 1),
            "response_rate": round((int(replied or 0) / total) * 100) if total else 0,
            "pending_requests": int(pending_requests or 0),
            "by_source": [dict(r) for r in by_source],
            "recent": [feedback_to_api(r, conn) for r in recent],
        })

    @app.get("/api/feedback/workspace")
    @login_required
    def api_feedback_workspace_list():
        ws = ws_id()
        if not ws:
            return jsonify([])
        q = request.args.get("q", "").strip()
        source = request.args.get("source", "")
        status = request.args.get("status", "")
        with db() as conn:
            _guard(conn, "feedback.read")
            query = "SELECT * FROM feedback_records WHERE workspace_id=?"
            params: list = [ws]
            if source:
                query += " AND (source=? OR source_type=?)"
                params.extend([source, source])
            if status:
                query += " AND status=?"
                params.append(status)
            if q:
                query += " AND (comment LIKE ? OR customer_name LIKE ? OR CAST(id AS TEXT) LIKE ?)"
                like = f"%{q}%"
                params.extend([like, like, like])
            query += " ORDER BY created_at DESC LIMIT 500"
            rows = conn.execute(query, params).fetchall()
            return jsonify([feedback_to_api(r, conn) for r in rows])

    @app.post("/api/feedback/workspace")
    @login_required
    def api_feedback_workspace_create():
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "feedback.create")
            store = conn.execute(
                "SELECT id FROM stores WHERE workspace_id=? LIMIT 1", (ws,)
            ).fetchone()
            if not store:
                return jsonify({"error": "No store linked to workspace — create a storefront first"}), 400
            ftype = data.get("feedback_type") or "comment"
            if ftype not in FEEDBACK_TYPES:
                ftype = "comment"
            source = data.get("source") or "business_os"
            cur = conn.execute(
                """INSERT INTO feedback_records
                   (store_id, workspace_id, feedback_type, source_type, source,
                    rating, comment, customer_id, customer_name, customer_email,
                    related_object_type, related_object_id, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
                (
                    store["id"], ws, ftype, source, source,
                    data.get("rating"), (data.get("content") or data.get("comment") or "").strip(),
                    data.get("customer_id"), data.get("customer_name"), data.get("customer_email"),
                    data.get("related_entity_type"), data.get("related_entity_id"), _now(),
                ),
            )
            fid = cur.lastrowid
            meta = {}
            if data.get("customer_id"):
                meta["customer_id"] = int(data["customer_id"])
                meta["owner_id"] = uid()
            row = conn.execute("SELECT * FROM feedback_records WHERE id=?", (fid,)).fetchone()
            from bos.responses import record_response_from_feedback
            record_response_from_feedback(conn, row)
            _emit(conn, "feedback.created", fid, "Feedback created", metadata=meta)
            row = conn.execute("SELECT * FROM feedback_records WHERE id=?", (fid,)).fetchone()
        return jsonify(feedback_to_api(row)), 201

    @app.get("/api/feedback/workspace/<int:feedback_id>")
    @login_required
    def api_feedback_workspace_detail(feedback_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "feedback.read")
            row = get_workspace_feedback(conn, feedback_id, int(ws))
            payload = feedback_to_api(row, conn)
            payload["activity"] = [
                dict(a) for a in conn.execute(
                    "SELECT * FROM feedback_activity WHERE feedback_id=? ORDER BY created_at DESC",
                    (feedback_id,),
                ).fetchall()
            ]
            mapping = conn.execute(
                "SELECT * FROM external_feedback_mappings WHERE feedback_id=?", (feedback_id,)
            ).fetchone()
            if mapping:
                payload["external_mapping"] = dict(mapping)
        return jsonify(payload)

    @app.patch("/api/feedback/workspace/<int:feedback_id>")
    @login_required
    def api_feedback_workspace_update(feedback_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "feedback.update")
            get_workspace_feedback(conn, feedback_id, int(ws))
            updates, params = [], []
            for field, col in (("status", "status"), ("content", "comment"), ("rating", "rating")):
                if field in data:
                    updates.append(f"{col}=?")
                    params.append(data[field])
            if updates:
                updates.append("updated_at=?")
                params.extend([_now(), feedback_id])
                conn.execute(f"UPDATE feedback_records SET {', '.join(updates)} WHERE id=?", params)
            _emit(conn, "feedback.updated", feedback_id, "Feedback updated")
            row = conn.execute("SELECT * FROM feedback_records WHERE id=?", (feedback_id,)).fetchone()
        return jsonify(feedback_to_api(row))

    @app.delete("/api/feedback/workspace/<int:feedback_id>")
    @login_required
    def api_feedback_workspace_delete(feedback_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "feedback.delete")
            get_workspace_feedback(conn, feedback_id, int(ws))
            conn.execute(
                "UPDATE feedback_records SET status='archived', updated_at=? WHERE id=?",
                (_now(), feedback_id),
            )
            _emit(conn, "feedback.archived", feedback_id, "Feedback archived")
        return jsonify({"ok": True})

    # ── Surveys ───────────────────────────────────────────────────────────────

    @app.get("/api/surveys")
    @login_required
    def api_surveys_list():
        ws = ws_id()
        if not ws:
            return jsonify([])
        with db() as conn:
            _guard(conn, "feedback.read")
            rows = conn.execute(
                "SELECT * FROM surveys WHERE workspace_id=? ORDER BY updated_at DESC", (ws,)
            ).fetchall()
            return jsonify([_survey_to_api(conn, r) for r in rows])

    @app.post("/api/surveys")
    @login_required
    def api_surveys_create():
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Title required"}), 400
        with db() as conn:
            _guard(conn, "survey.manage")
            cur = conn.execute(
                """INSERT INTO surveys (workspace_id, title, description, status, created_by, updated_at)
                   VALUES (?, ?, ?, 'draft', ?, ?)""",
                (ws, title, (data.get("description") or "").strip(), uid(), _now()),
            )
            sid = cur.lastrowid
            for i, q in enumerate(data.get("questions") or []):
                conn.execute(
                    """INSERT INTO survey_questions (survey_id, type, question, required, sort_order, options)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        sid, q.get("type") or "text", q.get("question") or "",
                        1 if q.get("required") else 0, q.get("order", i),
                        json.dumps(q.get("options") or []),
                    ),
                )
            from bos.events import emit
            emit(conn, "survey.created", "survey", sid, workspace_id=int(ws), user_id=uid(),
                 actor="member", title=f"Survey created: {title}", href="/app/feedback")
            row = conn.execute("SELECT * FROM surveys WHERE id=?", (sid,)).fetchone()
            return jsonify(_survey_to_api(conn, row, include_questions=True)), 201

    @app.get("/api/surveys/<int:survey_id>")
    @login_required
    def api_survey_detail(survey_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "feedback.read")
            row = conn.execute(
                "SELECT * FROM surveys WHERE id=? AND workspace_id=?", (survey_id, ws)
            ).fetchone()
            if not row:
                abort(404)
            return jsonify(_survey_to_api(conn, row, include_questions=True))

    @app.post("/api/surveys/<int:survey_id>/publish")
    @login_required
    def api_survey_publish(survey_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "survey.manage")
            row = conn.execute(
                "SELECT * FROM surveys WHERE id=? AND workspace_id=?", (survey_id, ws)
            ).fetchone()
            if not row:
                abort(404)
            pub = row["pub_code"] or _pub_code()
            conn.execute(
                "UPDATE surveys SET status='published', pub_code=?, updated_at=? WHERE id=?",
                (pub, _now(), survey_id),
            )
            from bos.events import emit
            emit(conn, "survey.published", "survey", survey_id, workspace_id=int(ws), user_id=uid(),
                 actor="member", title=f"Survey published: {row['title']}", href="/app/feedback")
            row = conn.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
            return jsonify(_survey_to_api(conn, row, include_questions=True))

    @app.get("/api/surveys/by-code/<code>")
    def api_survey_by_code(code):
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM surveys WHERE pub_code=? AND status='published'", (code.lower(),)
            ).fetchone()
            if not row:
                abort(404)
            return jsonify(_survey_to_api(conn, row, include_questions=True))

    @app.get("/survey/<code>")
    def survey_submit_view(code):
        xs = request.args.get("xs", "")
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM surveys WHERE pub_code=? AND status='published'", (code.lower(),)
            ).fetchone()
            if not row:
                abort(404)
            survey = _survey_to_api(conn, row, include_questions=True)
        return render_template("customer/survey.html", survey=survey, submitted=False, xs=xs)

    @app.post("/survey/<code>")
    def survey_submit_post(code):
        data = request.get_json(silent=True)
        if not data:
            answers = {}
            with db() as conn:
                row = conn.execute(
                    "SELECT id FROM surveys WHERE pub_code=? AND status='published'", (code.lower(),)
                ).fetchone()
                if not row:
                    abort(404)
                survey_id = int(row["id"])
                for q in conn.execute(
                    "SELECT id, type FROM survey_questions WHERE survey_id=?", (survey_id,)
                ).fetchall():
                    key = f"q_{q['id']}"
                    if q["type"] == "multiple_choice":
                        answers[str(q["id"])] = request.form.getlist(key)
                    else:
                        answers[str(q["id"])] = request.form.get(key)
            data = {
                "answers": answers,
                "customer_name": request.form.get("customer_name"),
                "customer_email": request.form.get("customer_email"),
            }
        else:
            with db() as conn:
                row = conn.execute(
                    "SELECT id FROM surveys WHERE pub_code=? AND status='published'", (code.lower(),)
                ).fetchone()
                if not row:
                    abort(404)
                survey_id = int(row["id"])
        xs = request.args.get("xs") or request.form.get("xs") or (data or {}).get("xs")
        exp_id = None
        if xs:
            with db() as conn:
                from qr_experience_runtime import get_session
                session_row = get_session(conn, xs)
                if session_row and session_row["experience_id"]:
                    exp_id = int(session_row["experience_id"])
        with db() as conn:
            fid, rid = _submit_survey_response(conn, survey_id, data, experience_id=exp_id)
            if xs:
                try:
                    from qr_experience_runtime import complete_session, get_session, record_interaction
                    session_row = get_session(conn, xs)
                    if session_row:
                        record_interaction(
                            conn, session_row, "click",
                            action_type="start_survey",
                            metadata={"feedback_id": fid},
                            analytics_app=app,
                        )
                        record_interaction(
                            conn, session_row, "complete",
                            action_type="start_survey",
                            metadata={"feedback_id": fid, "response_id": rid},
                            analytics_app=app,
                        )
                        complete_session(conn, session_row)
                except Exception:
                    logging.getLogger("app.feedback").debug("survey_event_recording_failed", exc_info=True)
            survey_row = conn.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
            survey_payload = _survey_to_api(conn, survey_row, include_questions=True)
        if request.is_json or (request.content_type and "json" in request.content_type):
            return jsonify({"ok": True, "feedback_id": fid, "response_id": rid}), 201
        return render_template("customer/survey.html", survey=survey_payload, submitted=True)

    @app.post("/api/surveys/<int:survey_id>/responses")
    def api_survey_submit(survey_id):
        data = request.get_json(silent=True) or {}
        with db() as conn:
            fid, rid = _submit_survey_response(conn, survey_id, data)
        return jsonify({"ok": True, "feedback_id": fid, "response_id": rid}), 201

    # ── Feedback requests (booking / check-in hooks) ────────────────────────

    @app.post("/api/feedback/requests")
    @login_required
    def api_feedback_request_create():
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "feedback.create")
            survey_id = data.get("survey_id")
            if not survey_id:
                pub = conn.execute(
                    "SELECT id FROM surveys WHERE workspace_id=? AND status='published' ORDER BY id LIMIT 1",
                    (ws,),
                ).fetchone()
                survey_id = pub["id"] if pub else None
            cur = conn.execute(
                """INSERT INTO feedback_requests
                   (workspace_id, customer_id, booking_id, check_in_id, survey_id, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (
                    ws, data.get("customer_id"), data.get("booking_id"),
                    data.get("check_in_id"), survey_id,
                ),
            )
            rid = cur.lastrowid
            from bos.events import emit
            emit(conn, "feedback.request_created", "feedback_request", rid,
                 workspace_id=int(ws), user_id=uid(), actor="member",
                 title="Feedback request created", href="/app/feedback")
        return jsonify({"id": rid, "survey_id": survey_id, "status": "pending"}), 201

    @app.get("/api/feedback/requests")
    @login_required
    def api_feedback_requests_list():
        ws = ws_id()
        if not ws:
            return jsonify([])
        with db() as conn:
            _guard(conn, "feedback.read")
            rows = conn.execute(
                "SELECT * FROM feedback_requests WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100",
                (ws,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    # ── Reputation plugins ───────────────────────────────────────────────────

    @app.get("/api/feedback/plugins")
    @login_required
    def api_feedback_plugins():
        with db() as conn:
            _guard(conn, "feedback.read")
            plugins = []
            for p in REPUTATION_PLUGINS:
                row = conn.execute(
                    """SELECT uic.* FROM user_integration_connections uic
                       JOIN integration_plugins ip ON ip.id=uic.plugin_id AND ip.slug=?
                       WHERE uic.user_id=?""",
                    (p["slug"], uid()),
                ).fetchone()
                plugins.append({
                    **p,
                    "connected": bool(row and row["status"] in ("connected", "active")),
                    "status": row["status"] if row else "not_connected",
                })
        return jsonify(plugins)

    @app.post("/api/feedback/plugins/<slug>/sync")
    @login_required
    def api_feedback_plugin_sync(slug):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "integration.manage")
            plugin_def = next((p for p in REPUTATION_PLUGINS if p["slug"] == slug), None)
            if not plugin_def:
                abort(404)
            from feedback_reputation_plugins import PLUGIN_REGISTRY
            plugin = PLUGIN_REGISTRY.get(slug)
            connection = conn.execute(
                """SELECT uic.id FROM user_integration_connections uic
                   JOIN integration_plugins ip ON ip.id=uic.plugin_id AND ip.slug=?
                   WHERE uic.user_id=? AND uic.status IN ('connected','active')""",
                (slug, uid()),
            ).fetchone()
            if not connection:
                return jsonify({"error": f"{plugin_def['name']} not connected", "synced": 0}), 400
            result = plugin.sync_feedback(conn, workspace_id=int(ws), connection_id=int(connection["id"])) if plugin else {"synced": 0}
            from integration_platform import log_integration_event
            log_integration_event(conn, connection["id"], "feedback.sync", "success",
                                  json.dumps(result))
        return jsonify({"ok": True, **result, "platform": slug})

    app.init_feedback_core_tables = init_feedback_core_tables
