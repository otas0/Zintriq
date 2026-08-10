"""QR Customer Experience Runtime — executes published experiences for customers."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime

INTERACTION_TYPES = ("scan", "view", "click", "submit", "complete")
SESSION_STATUSES = ("active", "completed", "abandoned")

RUNTIME_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experience_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    visitor_key TEXT,
    customer_id INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    actions_completed INTEGER NOT NULL DEFAULT 0,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qrx_sess_exp ON qr_experience_sessions(experience_id, started_at);
CREATE INDEX IF NOT EXISTS idx_qrx_sess_sid ON qr_experience_sessions(session_id);

CREATE TABLE IF NOT EXISTS qr_experience_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_session_id INTEGER NOT NULL,
    experience_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    action_type TEXT,
    action_id INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_session_id) REFERENCES qr_experience_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qrx_int_sess ON qr_experience_interactions(experience_session_id);
CREATE INDEX IF NOT EXISTS idx_qrx_int_exp ON qr_experience_interactions(experience_id, event_type);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def init_runtime_tables(conn) -> None:
    conn.executescript(RUNTIME_SCHEMA_SQL)
    if not _column_exists(conn, "qr_experiences", "public_slug"):
        conn.execute("ALTER TABLE qr_experiences ADD COLUMN public_slug TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_qr_exp_public_slug ON qr_experiences(public_slug)"
        )


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "experience").lower()).strip("-")
    return (s[:56] or "experience").strip("-")


def assign_public_slug(conn, experience_id: int, name: str) -> str:
    base = slugify(name)
    slug = base
    n = 1
    while conn.execute(
        "SELECT 1 FROM qr_experiences WHERE public_slug=? AND id!=?",
        (slug, experience_id),
    ).fetchone():
        n += 1
        slug = f"{base}-{n:03d}"
    conn.execute(
        "UPDATE qr_experiences SET public_slug=?, updated_at=? WHERE id=?",
        (slug, _now(), experience_id),
    )
    return slug


def ensure_visitor_key(session) -> str:
    from guest_platform import ensure_visitor_key as _ensure

    return _ensure(session)


def resolve_experience(conn, key: str, *, allow_draft: bool = False):
    """Find experience by public_slug or linked qr code."""
    key = (key or "").strip().lower()
    if not key:
        return None, None
    row = conn.execute(
        "SELECT * FROM qr_experiences WHERE lower(public_slug)=?",
        (key,),
    ).fetchone()
    if row:
        if not allow_draft and row["status"] != "active":
            return None, None
        qr = None
        if row["qr_code_id"]:
            qr = conn.execute("SELECT * FROM qr_codes WHERE id=?", (row["qr_code_id"],)).fetchone()
        return row, qr
    qr = conn.execute(
        """SELECT qr_codes.* FROM qr_codes
           WHERE lower(code)=? AND status!='archived'""",
        (key,),
    ).fetchone()
    if not qr:
        return None, None
    exp = None
    if "experience_id" in qr.keys() and qr["experience_id"]:
        exp = conn.execute("SELECT * FROM qr_experiences WHERE id=?", (qr["experience_id"],)).fetchone()
    if not exp:
        exp = conn.execute(
            "SELECT * FROM qr_experiences WHERE qr_code_id=?", (qr["id"],)
        ).fetchone()
    if not exp:
        return None, qr
    if not allow_draft and exp["status"] != "active":
        return None, qr
    return exp, qr


def create_experience_session(conn, exp_row, visitor_key: str) -> dict:
    sid = secrets.token_urlsafe(18)
    cur = conn.execute(
        """INSERT INTO qr_experience_sessions
           (experience_id, workspace_id, session_id, visitor_key, status, started_at)
           VALUES (?, ?, ?, ?, 'active', ?)""",
        (exp_row["id"], exp_row["workspace_id"], sid, visitor_key, _now()),
    )
    session_pk = int(cur.lastrowid)
    row = conn.execute(
        "SELECT * FROM qr_experience_sessions WHERE id=?", (session_pk,)
    ).fetchone()
    return dict(row)


def get_session(conn, session_id: str):
    return conn.execute(
        "SELECT * FROM qr_experience_sessions WHERE session_id=?",
        (session_id,),
    ).fetchone()


def record_interaction(
    conn,
    session_row,
    event_type: str,
    *,
    action_type: str | None = None,
    action_id: int | None = None,
    metadata: dict | None = None,
    device_type: str = "unknown",
    analytics_app=None,
) -> int:
    if event_type not in INTERACTION_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}")
    meta = json.dumps(metadata or {})
    cur = conn.execute(
        """INSERT INTO qr_experience_interactions
           (experience_session_id, experience_id, workspace_id,
            event_type, action_type, action_id, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_row["id"], session_row["experience_id"], session_row["workspace_id"],
            event_type, action_type, action_id, meta, _now(),
        ),
    )
    legacy_type = {
        "scan": "scan",
        "view": "view",
        "click": "action_completed",
        "submit": "action_completed",
        "complete": "action_completed",
    }.get(event_type, "action_completed")
    conn.execute(
        """INSERT INTO qr_experience_events
           (experience_id, workspace_id, event_type, visitor_key, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (
            session_row["experience_id"], session_row["workspace_id"],
            legacy_type, session_row["visitor_key"], meta,
        ),
    )
    if analytics_app:
        from qr_experience_analytics import insert_analytics_event, map_runtime_to_analytics
        analytics_type = map_runtime_to_analytics(event_type, action_type)
        if analytics_type:
            insert_analytics_event(conn, {
                "experience_id": session_row["experience_id"],
                "session_id": session_row["session_id"],
                "event_type": analytics_type,
                "device_type": device_type,
                "metadata": metadata or {},
            })
    if event_type in ("submit", "complete"):
        conn.execute(
            """UPDATE qr_experience_sessions
               SET actions_completed=actions_completed+1
               WHERE id=?""",
            (session_row["id"],),
        )
    return int(cur.lastrowid)


def complete_session(conn, session_row) -> None:
    if session_row["status"] == "active":
        conn.execute(
            """UPDATE qr_experience_sessions
               SET status='completed', completed_at=?
               WHERE id=?""",
            (_now(), session_row["id"]),
        )


def public_create_booking(conn, workspace_id: int, store_id: int, data: dict, *, contact_id: int | None = None) -> int:
    title = (data.get("title") or data.get("service") or "Booking").strip()
    name = (data.get("customer_name") or data.get("name") or "").strip()
    starts_at = (data.get("starts_at") or "").strip().replace("T", " ")
    if len(starts_at) == 16:
        starts_at += ":00"
    if not name or not starts_at:
        from flask import abort
        abort(400, description="Name and start time required")
    ends_at = data.get("ends_at") or starts_at
    cols = ["workspace_id", "title", "customer_name", "customer_email", "customer_phone",
            "starts_at", "ends_at", "location", "status", "notes", "updated_at"]
    vals = [
        workspace_id, title, name,
        (data.get("customer_email") or data.get("email") or "").strip() or None,
        (data.get("customer_phone") or data.get("phone") or "").strip() or None,
        starts_at, ends_at,
        (data.get("location") or "").strip() or None,
        "confirmed",
        (data.get("notes") or "").strip() or None,
        _now(),
    ]
    if _column_exists(conn, "bookings", "contact_id"):
        cols.insert(1, "contact_id")
        vals.insert(1, contact_id)
    placeholders = ", ".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO bookings ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    bid = int(cur.lastrowid)
    from bos.events import emit
    emit(
        conn, "booking.created", "booking", bid,
        workspace_id=int(workspace_id), actor="customer",
        title=f"Booking from QR: {name}",
        metadata={"source": "qr_runtime", "store_id": store_id, "customer_id": contact_id},
        href="/app/booking",
    )
    return bid


def public_create_checkin(
    conn,
    workspace_id: int,
    store_id: int,
    point_id: int,
    data: dict,
    *,
    contact_id: int | None = None,
) -> int:
    name = (data.get("customer_name") or data.get("name") or "Guest").strip()
    cols = ["workspace_id", "store_id", "point_id", "method", "source", "customer_name",
            "status", "notes", "checked_in_at", "updated_at"]
    vals = [
        workspace_id, store_id, point_id, "qr", "qr", name,
        "checked_in",
        (data.get("notes") or "").strip() or None,
        _now(), _now(),
    ]
    if _column_exists(conn, "check_ins", "contact_id"):
        cols.insert(3, "contact_id")
        vals.insert(3, contact_id)
    placeholders = ", ".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO check_ins ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    cid = int(cur.lastrowid)
    from bos.events import emit
    emit(
        conn, "check_in.created", "check_in", cid,
        workspace_id=int(workspace_id), actor="customer",
        title=f"QR check-in: {name}",
        metadata={"source": "qr_runtime", "point_id": point_id, "customer_id": contact_id},
        href="/app/check-in",
    )
    return cid


def bridge_legacy_checkin(conn, point: dict, customer_name: str | None = None) -> int | None:
    """Create BOS check_ins row when customer uses legacy /checkin/<code> page."""
    store = conn.execute(
        "SELECT id, workspace_id FROM stores WHERE id=?", (point["store_id"],)
    ).fetchone()
    if not store or not store["workspace_id"]:
        return None
    return public_create_checkin(
        conn, int(store["workspace_id"]), int(store["id"]), int(point["id"]),
        {"customer_name": customer_name or "Guest"},
    )


def runtime_customer_payload(conn, exp_row, store_row, session_row) -> dict:
    from qr_experience_builder import public_experience_payload
    from qr_experience_workflow import get_workflow_for_experience, start_workflow_run, get_workflow_progress, workflow_to_api, _parse_steps, workflow_progress_payload

    payload = public_experience_payload(conn, exp_row, store_row)
    xs = session_row["session_id"]
    payload["session_id"] = xs
    payload["public_slug"] = exp_row["public_slug"] if "public_slug" in exp_row.keys() else None
    payload["runtime"] = {
        "session_id": xs,
        "interact_api": f"/api/runtime/sessions/{xs}/interact",
        "booking_api": f"/api/runtime/sessions/{xs}/booking",
        "checkin_api": f"/api/runtime/sessions/{xs}/checkin",
        "workflow_advance_api": f"/api/runtime/sessions/{xs}/workflow/advance",
    }
    wf = get_workflow_for_experience(conn, int(exp_row["id"]))
    if wf and wf["status"] == "active":
        prog = get_workflow_progress(conn, xs)
        if prog:
            steps = _parse_steps(wf["steps"])
            step_states = json.loads(prog["step_states"] or "{}")
            payload["workflow"] = workflow_progress_payload(
                conn, xs, wf, steps, step_states, int(prog["current_step_index"]),
            )
        else:
            payload["workflow"] = {"status": wf["status"], "steps": workflow_to_api(wf)["steps"]}
    for action in payload.get("actions") or []:
        href = action.get("href")
        if href and href.startswith("/") and "xs=" not in href:
            sep = "&" if "?" in href else "?"
            action["href"] = f"{href}{sep}xs={xs}"
    return payload


def register_qr_experience_runtime(app) -> None:
    from flask import abort, jsonify, render_template, request, session
    from app import current_user, db, login_required
    from bos.permissions import has_permission

    def _render_runtime(slug: str, *, preview: bool = False, from_scan: bool = False):
        from qr_experience_analytics import detect_device
        device = detect_device(request.headers.get("User-Agent"))
        with db() as conn:
            exp, qr = resolve_experience(conn, slug, allow_draft=preview)
            if not exp:
                abort(404)
            if preview:
                user = current_user()
                if not user:
                    abort(401)
                if not has_permission(conn, int(user["id"]), int(exp["workspace_id"]), "qr_experience.read"):
                    if not has_permission(conn, int(user["id"]), int(exp["workspace_id"]), "workspace.read"):
                        abort(403)
            elif exp["status"] == "paused":
                return render_template(
                    "customer/qr_disabled.html",
                    experience_name=exp["name"],
                ), 403
            elif exp["status"] == "archived":
                return render_template(
                    "customer/qr_expired.html",
                    experience_name=exp["name"],
                ), 410
            elif exp["status"] != "active":
                abort(404)

            store = conn.execute(
                "SELECT * FROM stores WHERE id=?", (exp["store_id"],)
            ).fetchone() if exp["store_id"] else None

            visitor_key = ensure_visitor_key(session)
            sess = create_experience_session(conn, exp, visitor_key)
            session_row = conn.execute(
                "SELECT * FROM qr_experience_sessions WHERE id=?", (sess["id"],)
            ).fetchone()

            if from_scan:
                record_interaction(
                    conn, session_row, "scan", metadata={"source": "qr"},
                    device_type=device, analytics_app=app,
                )
                from qr_customer_data import resolve_session_customer, record_qr_interaction
                from qr_experience_workflow import get_workflow_for_experience
                cid = resolve_session_customer(
                    conn, int(exp["workspace_id"]), int(exp["store_id"]) if exp["store_id"] else None,
                    visitor_key, session_row,
                )
                if cid:
                    wf = get_workflow_for_experience(conn, int(exp["id"]))
                    record_qr_interaction(
                        conn, customer_id=cid, workspace_id=int(exp["workspace_id"]),
                        interaction_type="qr_scan", experience_id=int(exp["id"]),
                        workflow_id=int(wf["id"]) if wf else None,
                        session_id=session_row["session_id"],
                        store_id=int(exp["store_id"]) if exp["store_id"] else None,
                    )
                    session_row = conn.execute(
                        "SELECT * FROM qr_experience_sessions WHERE id=?", (session_row["id"],),
                    ).fetchone()
            record_interaction(
                conn, session_row, "view", device_type=device, analytics_app=app,
            )

            from qr_experience_workflow import get_workflow_for_experience, start_workflow_run
            wf = get_workflow_for_experience(conn, int(exp["id"]))
            if wf and wf["status"] == "active":
                start_workflow_run(conn, wf, session_row, from_scan=from_scan, analytics_app=app)

            payload = runtime_customer_payload(conn, exp, store, session_row)
            code = qr["code"] if qr else None
            return render_template(
                "customer/qr_experience.html",
                experience=payload,
                code=code,
                preview_mode=preview,
            )

    @app.get("/e/<slug>")
    def runtime_experience(slug: str):
        from_scan = request.args.get("from") == "qr"
        return _render_runtime(slug, preview=False, from_scan=from_scan)

    @app.get("/e/<slug>/preview")
    @login_required
    def runtime_experience_preview(slug: str):
        return _render_runtime(slug, preview=True, from_scan=False)

    @app.post("/api/runtime/sessions/<session_id>/interact")
    def runtime_interact(session_id: str):
        from qr_experience_analytics import detect_device
        data = request.get_json(silent=True) or {}
        event_type = (data.get("event_type") or "click").strip()
        if event_type not in INTERACTION_TYPES:
            return jsonify({"error": "Invalid event_type"}), 400
        device = detect_device(request.headers.get("User-Agent"))
        with db() as conn:
            session_row = get_session(conn, session_id)
            if not session_row:
                abort(404)
            exp = conn.execute(
                "SELECT status FROM qr_experiences WHERE id=?", (session_row["experience_id"],)
            ).fetchone()
            if not exp or exp["status"] != "active":
                abort(404)
            iid = record_interaction(
                conn, session_row, event_type,
                action_type=data.get("action_type"),
                action_id=data.get("action_id"),
                metadata=data.get("metadata") or {},
                device_type=device,
                analytics_app=app,
            )
        return jsonify({"ok": True, "interaction_id": iid}), 201

    @app.post("/api/runtime/sessions/<session_id>/booking")
    def runtime_booking(session_id: str):
        from qr_experience_analytics import detect_device
        data = request.get_json(silent=True) or {}
        device = detect_device(request.headers.get("User-Agent"))
        with db() as conn:
            session_row = get_session(conn, session_id)
            if not session_row:
                abort(404)
            exp = conn.execute(
                "SELECT * FROM qr_experiences WHERE id=? AND status='active'",
                (session_row["experience_id"],),
            ).fetchone()
            if not exp:
                abort(404)
            record_interaction(
                conn, session_row, "click",
                action_type="create_booking",
                action_id=data.get("action_id"),
                device_type=device, analytics_app=app,
            )
            from qr_customer_data import resolve_session_customer, record_qr_interaction
            from flask import session as flask_session
            visitor_key = session_row["visitor_key"] or flask_session.get("visitor_key") or ""
            cid = resolve_session_customer(
                conn, int(exp["workspace_id"]), int(exp["store_id"]),
                visitor_key, session_row,
                name=data.get("customer_name") or data.get("name"),
                email=data.get("customer_email") or data.get("email"),
                phone=data.get("customer_phone") or data.get("phone"),
            )
            bid = public_create_booking(
                conn, int(exp["workspace_id"]), int(exp["store_id"]), data, contact_id=cid,
            )
            if cid:
                record_qr_interaction(
                    conn, customer_id=cid, workspace_id=int(exp["workspace_id"]),
                    interaction_type="booking_created", experience_id=int(exp["id"]),
                    session_id=session_id, related_object_type="booking", related_object_id=bid,
                    store_id=int(exp["store_id"]),
                    metadata={"booking_id": bid, "customer_name": data.get("customer_name") or data.get("name")},
                )
            record_interaction(
                conn, session_row, "complete",
                action_type="create_booking",
                metadata={"booking_id": bid},
                device_type=device, analytics_app=app,
            )
            complete_session(conn, session_row)
        return jsonify({"ok": True, "booking_id": bid}), 201

    @app.post("/api/runtime/sessions/<session_id>/checkin")
    def runtime_checkin(session_id: str):
        from qr_experience_analytics import detect_device
        data = request.get_json(silent=True) or {}
        device = detect_device(request.headers.get("User-Agent"))
        with db() as conn:
            session_row = get_session(conn, session_id)
            if not session_row:
                abort(404)
            exp = conn.execute(
                "SELECT * FROM qr_experiences WHERE id=? AND status='active'",
                (session_row["experience_id"],),
            ).fetchone()
            if not exp:
                abort(404)
            point_id = data.get("check_in_point_id")
            point = None
            if point_id:
                point = conn.execute(
                    """SELECT * FROM check_in_points
                       WHERE id=? AND store_id=? AND status!='archived'""",
                    (point_id, exp["store_id"]),
                ).fetchone()
            if not point:
                point = conn.execute(
                    """SELECT * FROM check_in_points
                       WHERE store_id=? AND status!='archived'
                       ORDER BY id DESC LIMIT 1""",
                    (exp["store_id"],),
                ).fetchone()
            if not point:
                return jsonify({"error": "No check-in point configured"}), 400
            record_interaction(
                conn, session_row, "click",
                action_type="start_checkin",
                action_id=data.get("action_id"),
                device_type=device, analytics_app=app,
            )
            from qr_customer_data import resolve_session_customer, record_qr_interaction
            from flask import session as flask_session
            visitor_key = session_row["visitor_key"] or flask_session.get("visitor_key") or ""
            cid = resolve_session_customer(
                conn, int(exp["workspace_id"]), int(exp["store_id"]),
                visitor_key, session_row,
                name=data.get("customer_name") or data.get("name"),
            )
            cid_val = public_create_checkin(
                conn, int(exp["workspace_id"]), int(exp["store_id"]),
                int(point["id"]), data, contact_id=cid,
            )
            checkin_id = cid_val
            if cid:
                record_qr_interaction(
                    conn, customer_id=cid, workspace_id=int(exp["workspace_id"]),
                    interaction_type="checkin_completed", experience_id=int(exp["id"]),
                    session_id=session_id, related_object_type="check_in", related_object_id=checkin_id,
                    store_id=int(exp["store_id"]),
                )
            record_interaction(
                conn, session_row, "complete",
                action_type="start_checkin",
                metadata={"check_in_id": checkin_id, "point_id": point["id"]},
                device_type=device, analytics_app=app,
            )
            complete_session(conn, session_row)
        return jsonify({"ok": True, "check_in_id": checkin_id}), 201

    @app.post("/api/runtime/sessions/<session_id>/complete-survey")
    def runtime_survey_complete(session_id: str):
        from qr_experience_analytics import detect_device
        data = request.get_json(silent=True) or {}
        device = detect_device(request.headers.get("User-Agent"))
        with db() as conn:
            session_row = get_session(conn, session_id)
            if not session_row:
                abort(404)
            record_interaction(
                conn, session_row, "complete",
                action_type="start_survey",
                metadata={"feedback_id": data.get("feedback_id")},
                device_type=device, analytics_app=app,
            )
            from qr_customer_data import resolve_session_customer, record_qr_interaction
            from flask import session as flask_session
            exp = conn.execute(
                "SELECT * FROM qr_experiences WHERE id=?", (session_row["experience_id"],),
            ).fetchone()
            visitor_key = session_row["visitor_key"] or flask_session.get("visitor_key") or ""
            cid = resolve_session_customer(
                conn, int(session_row["workspace_id"]),
                int(exp["store_id"]) if exp and exp["store_id"] else None,
                visitor_key, session_row,
                name=data.get("customer_name") or data.get("name"),
                email=data.get("customer_email") or data.get("email"),
            )
            fid = data.get("feedback_id")
            if cid and fid:
                conn.execute(
                    "UPDATE feedback_records SET customer_id=? WHERE id=?",
                    (cid, int(fid)),
                )
                record_qr_interaction(
                    conn, customer_id=cid, workspace_id=int(session_row["workspace_id"]),
                    interaction_type="feedback_submitted" if data.get("type") != "survey" else "survey_completed",
                    experience_id=int(session_row["experience_id"]),
                    session_id=session_id, related_object_type="feedback", related_object_id=int(fid),
                    store_id=int(exp["store_id"]) if exp and exp["store_id"] else None,
                )
            complete_session(conn, session_row)
        return jsonify({"ok": True}), 201

    app.init_qr_experience_runtime_tables = init_runtime_tables
