"""QR Customer Data Layer — profiles and interactions from QR Experiences."""

from __future__ import annotations

import json
from datetime import datetime

INTERACTION_TYPES = (
    "qr_scan",
    "feedback_submitted",
    "survey_completed",
    "booking_created",
    "checkin_completed",
)

INTERACTION_LABELS = {
    "qr_scan": "QR Scan",
    "feedback_submitted": "Feedback Submitted",
    "survey_completed": "Survey Completed",
    "booking_created": "Booking Created",
    "checkin_completed": "Check-in Completed",
}

ACTIVITY_MAP = {
    "qr_scan": "qr_scan",
    "feedback_submitted": "feedback",
    "survey_completed": "survey",
    "booking_created": "appointment",
    "checkin_completed": "check_in",
}

QR_CUSTOMER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_customer_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    workspace_id INTEGER NOT NULL,
    experience_id INTEGER,
    workflow_id INTEGER,
    session_id TEXT,
    interaction_type TEXT NOT NULL,
    related_object_type TEXT,
    related_object_id INTEGER,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qr_cust_int_ws ON qr_customer_interactions(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_qr_cust_int_cust ON qr_customer_interactions(customer_id, created_at);
CREATE INDEX IF NOT EXISTS idx_qr_cust_int_exp ON qr_customer_interactions(experience_id);
CREATE INDEX IF NOT EXISTS idx_qr_cust_int_type ON qr_customer_interactions(interaction_type);

CREATE TABLE IF NOT EXISTS qr_customer_identities (
    workspace_id INTEGER NOT NULL,
    visitor_key TEXT NOT NULL,
    customer_id INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, visitor_key),
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def init_qr_customer_tables(conn) -> None:
    conn.executescript(QR_CUSTOMER_SCHEMA_SQL)
    if not _column_exists(conn, "customer_profiles", "metadata"):
        conn.execute("ALTER TABLE customer_profiles ADD COLUMN metadata TEXT DEFAULT '{}'")


def _workspace_owner_id(conn, workspace_id: int) -> int | None:
    row = conn.execute(
        """SELECT user_id FROM workspace_members
           WHERE workspace_id=? AND role='owner' AND status='active' LIMIT 1""",
        (workspace_id,),
    ).fetchone()
    if row:
        return int(row["user_id"])
    store = conn.execute(
        "SELECT owner_id FROM stores WHERE workspace_id=? LIMIT 1", (workspace_id,),
    ).fetchone()
    return int(store["owner_id"]) if store and store["owner_id"] else None


def _customer_code() -> str:
    import secrets
    return f"C-{secrets.token_hex(4).upper()}"


def _enrich_customer_profile(
    conn,
    customer_id: int,
    *,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    visitor_key: str | None = None,
) -> None:
    """Apply optional contact info collected after anonymous QR scan."""
    name = (name or "").strip()
    email = (email or "").strip() or None
    phone = (phone or "").strip() or None
    if not (name or email or phone):
        return

    row = conn.execute(
        "SELECT full_name, email, phone, metadata FROM customer_profiles WHERE id=?",
        (customer_id,),
    ).fetchone()
    if not row:
        return

    updates = []
    params: list = []
    if name and (not row["full_name"] or row["full_name"] == "Anonymous Guest"):
        updates.append("full_name=?")
        params.append(name)
    if email and not row["email"]:
        updates.append("email=?")
        params.append(email)
    if phone and not row["phone"]:
        updates.append("phone=?")
        params.append(phone)

    meta = {}
    try:
        meta = json.loads(row["metadata"] or "{}")
    except json.JSONDecodeError:
        pass
    if name or email or phone:
        meta["anonymous"] = False
        if visitor_key:
            meta["visitor_key"] = visitor_key
        updates.append("metadata=?")
        params.append(json.dumps(meta))

    if updates:
        updates.append("updated_at=?")
        params.append(_now())
        params.append(customer_id)
        conn.execute(
            f"UPDATE customer_profiles SET {', '.join(updates)} WHERE id=?",
            params,
        )


def resolve_session_customer(
    conn,
    workspace_id: int,
    store_id: int | None,
    visitor_key: str,
    session_row,
    *,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> int | None:
    """Resolve or create customer profile for a QR runtime session."""
    from customer_platform import find_or_create_customer

    if session_row["customer_id"]:
        cid = int(session_row["customer_id"])
        _enrich_customer_profile(conn, cid, name=name, email=email, phone=phone, visitor_key=visitor_key)
        return cid

    ident = conn.execute(
        "SELECT customer_id FROM qr_customer_identities WHERE workspace_id=? AND visitor_key=?",
        (workspace_id, visitor_key),
    ).fetchone()
    if ident:
        cid = int(ident["customer_id"])
        conn.execute(
            "UPDATE qr_experience_sessions SET customer_id=? WHERE id=?",
            (cid, session_row["id"]),
        )
        _enrich_customer_profile(conn, cid, name=name, email=email, phone=phone, visitor_key=visitor_key)
        return cid

    owner_id = _workspace_owner_id(conn, workspace_id)
    if not owner_id:
        return None

    name = (name or "").strip()
    email = (email or "").strip() or None
    phone = (phone or "").strip() or None

    if name or email or phone:
        cid = find_or_create_customer(
            conn, owner_id,
            email=email, phone=phone, full_name=name or None,
            store_id=store_id, source="qr_experience",
        )
    else:
        now = _now()
        meta = json.dumps({"anonymous": True, "visitor_key": visitor_key})
        cur = conn.execute(
            """INSERT INTO customer_profiles
               (owner_id, customer_code, full_name, preferred_name, primary_store_id,
                workspace_id, metadata, last_activity_at, updated_at)
               VALUES (?, ?, 'Anonymous Guest', ?, ?, ?, ?, ?, ?)""",
            (owner_id, _customer_code(), visitor_key[:12], store_id, workspace_id, meta, now, now),
        )
        cid = int(cur.lastrowid)

    if not cid:
        return None

    conn.execute(
        """INSERT OR REPLACE INTO qr_customer_identities
           (workspace_id, visitor_key, customer_id, created_at) VALUES (?, ?, ?, ?)""",
        (workspace_id, visitor_key, cid, _now()),
    )
    conn.execute(
        "UPDATE qr_experience_sessions SET customer_id=? WHERE id=?",
        (cid, session_row["id"]),
    )
    if name or email or phone:
        conn.execute(
            "UPDATE customer_profiles SET metadata=? WHERE id=?",
            (json.dumps({"anonymous": False, "visitor_key": visitor_key}), cid),
        )
    return cid


def record_qr_interaction(
    conn,
    *,
    customer_id: int,
    workspace_id: int,
    interaction_type: str,
    experience_id: int | None = None,
    workflow_id: int | None = None,
    session_id: str | None = None,
    related_object_type: str | None = None,
    related_object_id: int | None = None,
    metadata: dict | None = None,
    store_id: int | None = None,
) -> int:
    """Persist interaction row and project to customer activity timeline."""
    if interaction_type not in INTERACTION_TYPES:
        raise ValueError(f"Invalid interaction_type: {interaction_type}")

    meta = metadata or {}
    exp_name = None
    if experience_id:
        exp = conn.execute("SELECT name FROM qr_experiences WHERE id=?", (experience_id,)).fetchone()
        exp_name = exp["name"] if exp else None
        meta.setdefault("experience_name", exp_name)

    cur = conn.execute(
        """INSERT INTO qr_customer_interactions
           (customer_id, workspace_id, experience_id, workflow_id, session_id,
            interaction_type, related_object_type, related_object_id, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            customer_id, workspace_id, experience_id, workflow_id, session_id,
            interaction_type, related_object_type, related_object_id,
            json.dumps(meta), _now(),
        ),
    )
    iid = int(cur.lastrowid)

    label = INTERACTION_LABELS.get(interaction_type, interaction_type)
    title = label
    if exp_name:
        title = f"{label} — {exp_name}"

    owner_id = _workspace_owner_id(conn, workspace_id)
    if owner_id:
        from customer_platform import log_customer_activity
        log_customer_activity(
            conn, customer_id, owner_id,
            ACTIVITY_MAP.get(interaction_type, "visit"),
            title,
            detail=meta.get("detail") or "",
            store_id=store_id,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            source="qr_experience",
            actor="customer",
        )
    return iid


def _customer_display(row) -> str:
    if row["full_name"] and row["full_name"] != "Anonymous Guest":
        return row["full_name"]
    if row["email"]:
        return row["email"]
    if row["phone"]:
        return row["phone"]
    return "Anonymous Guest"


def list_qr_customers(conn, workspace_id: int, *, q: str = "", interaction_type: str = "", experience_id: int | None = None, limit: int = 100) -> list[dict]:
    """Customers with at least one QR interaction in workspace."""
    clauses = ["i.workspace_id=?"]
    params: list = [workspace_id]
    if interaction_type:
        clauses.append("i.interaction_type=?")
        params.append(interaction_type)
    if experience_id:
        clauses.append("i.experience_id=?")
        params.append(experience_id)
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(cp.full_name LIKE ? OR cp.email LIKE ? OR cp.phone LIKE ? OR x.name LIKE ?)")
        params.extend([like, like, like, like])

    rows = conn.execute(
        f"""SELECT cp.id, cp.full_name, cp.email, cp.phone, cp.last_activity_at, cp.metadata,
                   COUNT(i.id) AS interactions,
                   GROUP_CONCAT(DISTINCT i.interaction_type) AS kinds,
                   MAX(i.created_at) AS last_interaction,
                   GROUP_CONCAT(DISTINCT x.name) AS experience_names
            FROM qr_customer_interactions i
            JOIN customer_profiles cp ON cp.id=i.customer_id
            LEFT JOIN qr_experiences x ON x.id=i.experience_id
            WHERE {' AND '.join(clauses)}
            GROUP BY cp.id
            ORDER BY last_interaction DESC
            LIMIT ?""",
        (*params, limit),
    ).fetchall()

    result = []
    for r in rows:
        meta = {}
        try:
            meta = json.loads(r["metadata"] or "{}")
        except json.JSONDecodeError:
            pass
        result.append({
            "id": r["id"],
            "name": _customer_display(r),
            "email": r["email"] or "",
            "phone": r["phone"] or "",
            "anonymous": bool(meta.get("anonymous")),
            "interactions": int(r["interactions"] or 0),
            "kinds": (r["kinds"] or "").split(",") if r["kinds"] else [],
            "last_activity": r["last_interaction"] or r["last_activity_at"] or "",
            "experience_names": (r["experience_names"] or "").split(",") if r["experience_names"] else [],
        })
    return result


def customer_detail(conn, customer_id: int, workspace_id: int) -> dict | None:
    cp = conn.execute(
        """SELECT cp.* FROM customer_profiles cp
           WHERE cp.id=? AND cp.id IN (
             SELECT DISTINCT customer_id FROM qr_customer_interactions WHERE workspace_id=?
           )""",
        (customer_id, workspace_id),
    ).fetchone()
    if not cp:
        return None

    meta = {}
    try:
        meta = json.loads(cp["metadata"] or "{}")
    except json.JSONDecodeError:
        pass

    interactions = [
        dict(r) for r in conn.execute(
            """SELECT i.*, x.name AS experience_name
               FROM qr_customer_interactions i
               LEFT JOIN qr_experiences x ON x.id=i.experience_id
               WHERE i.customer_id=? AND i.workspace_id=?
               ORDER BY i.created_at DESC LIMIT 200""",
            (customer_id, workspace_id),
        ).fetchall()
    ]
    for row in interactions:
        try:
            row["metadata"] = json.loads(row["metadata"] or "{}")
        except json.JSONDecodeError:
            row["metadata"] = {}

    feedback = [
        dict(r) for r in conn.execute(
            """SELECT fr.id, fr.rating, fr.comment, fr.status, fr.created_at, s.name AS store_name
               FROM feedback_records fr
               JOIN stores s ON s.id=fr.store_id
               WHERE fr.customer_id=? AND s.workspace_id=?
               ORDER BY fr.created_at DESC LIMIT 50""",
            (customer_id, workspace_id),
        ).fetchall()
    ]

    bookings = [
        dict(r) for r in conn.execute(
            """SELECT b.id, b.title, b.starts_at, b.status, b.customer_name, b.created_at,
                      x.name AS experience_name
               FROM bookings b
               LEFT JOIN qr_customer_interactions i ON i.related_object_type='booking'
                 AND i.related_object_id=b.id AND i.customer_id=?
               LEFT JOIN qr_experiences x ON x.id=i.experience_id
               WHERE b.workspace_id=? AND (b.contact_id=? OR i.customer_id=?)
               ORDER BY b.starts_at DESC LIMIT 50""",
            (customer_id, workspace_id, customer_id, customer_id),
        ).fetchall()
    ]

    checkins = [
        dict(r) for r in conn.execute(
            """SELECT c.id, c.customer_name, c.checked_in_at, c.status,
                      x.name AS experience_name
               FROM check_ins c
               LEFT JOIN qr_customer_interactions i ON i.related_object_type='check_in'
                 AND i.related_object_id=c.id AND i.customer_id=?
               LEFT JOIN qr_experiences x ON x.id=i.experience_id
               WHERE c.workspace_id=? AND (c.contact_id=? OR i.customer_id=?)
               ORDER BY c.checked_in_at DESC LIMIT 50""",
            (customer_id, workspace_id, customer_id, customer_id),
        ).fetchall()
    ]

    timeline = [
        dict(r) for r in conn.execute(
            """SELECT activity_type, title, detail, related_object_type, related_object_id, created_at
               FROM customer_activities WHERE customer_id=?
               ORDER BY created_at DESC LIMIT 100""",
            (customer_id,),
        ).fetchall()
    ]

    sources = conn.execute(
        """SELECT DISTINCT x.id, x.name, GROUP_CONCAT(DISTINCT i.interaction_type) AS actions
           FROM qr_customer_interactions i
           JOIN qr_experiences x ON x.id=i.experience_id
           WHERE i.customer_id=? AND i.workspace_id=?
           GROUP BY x.id, x.name""",
        (customer_id, workspace_id),
    ).fetchall()

    return {
        "id": cp["id"],
        "name": _customer_display(cp),
        "email": cp["email"] or "",
        "phone": cp["phone"] or "",
        "anonymous": bool(meta.get("anonymous")),
        "status": cp["status"],
        "created_at": cp["created_at"],
        "last_activity_at": cp["last_activity_at"],
        "interactions": interactions,
        "feedback": feedback,
        "bookings": bookings,
        "checkins": checkins,
        "timeline": timeline,
        "qr_sources": [
            {"experience_id": s["id"], "name": s["name"], "actions": (s["actions"] or "").split(",")}
            for s in sources
        ],
    }


def dashboard_summary(conn, workspace_id: int) -> dict:
    total = conn.execute(
        "SELECT COUNT(DISTINCT customer_id) AS c FROM qr_customer_interactions WHERE workspace_id=?",
        (workspace_id,),
    ).fetchone()["c"]
    recent = conn.execute(
        """SELECT COUNT(*) AS c FROM qr_customer_interactions
           WHERE workspace_id=? AND date(created_at) >= date('now', '-7 days')""",
        (workspace_id,),
    ).fetchone()["c"]
    by_type = {
        r["interaction_type"]: r["c"]
        for r in conn.execute(
            """SELECT interaction_type, COUNT(*) AS c FROM qr_customer_interactions
               WHERE workspace_id=? GROUP BY interaction_type""",
            (workspace_id,),
        ).fetchall()
    }
    popular = [
        dict(r) for r in conn.execute(
            """SELECT x.id, x.name, COUNT(i.id) AS interactions
               FROM qr_customer_interactions i
               JOIN qr_experiences x ON x.id=i.experience_id
               WHERE i.workspace_id=?
               GROUP BY x.id, x.name
               ORDER BY interactions DESC LIMIT 5""",
            (workspace_id,),
        ).fetchall()
    ]
    activity = [
        dict(r) for r in conn.execute(
            """SELECT i.interaction_type, i.created_at, cp.full_name, cp.email, x.name AS experience_name
               FROM qr_customer_interactions i
               JOIN customer_profiles cp ON cp.id=i.customer_id
               LEFT JOIN qr_experiences x ON x.id=i.experience_id
               WHERE i.workspace_id=?
               ORDER BY i.created_at DESC LIMIT 15""",
            (workspace_id,),
        ).fetchall()
    ]
    return {
        "total_customers": int(total or 0),
        "recent_interactions_7d": int(recent or 0),
        "by_type": by_type,
        "popular_experiences": popular,
        "recent_activity": activity,
    }


def register_qr_customer_data(app) -> None:
    from flask import abort, jsonify, request, session as flask_session
    from app import current_user, db, login_required
    from bos.permissions import has_permission

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def _guard(conn, permission: str):
        ws = flask_session.get("active_workspace_id")
        if not ws:
            abort(400)
        if has_permission(conn, uid(), int(ws), permission):
            return int(ws)
        fallback = {
            "interaction.read": "customer.read",
            "customer.manage": "customer.update",
        }.get(permission)
        if fallback and has_permission(conn, uid(), int(ws), fallback):
            return int(ws)
        abort(403)

    @app.get("/api/customers/qr/dashboard")
    @login_required
    def api_qr_customers_dashboard():
        with db() as conn:
            ws = _guard(conn, "interaction.read")
            return jsonify(dashboard_summary(conn, ws))

    @app.get("/api/customers/qr")
    @login_required
    def api_qr_customers_list():
        q = request.args.get("q", "")
        itype = request.args.get("type", "")
        exp_id = request.args.get("experience_id")
        with db() as conn:
            ws = _guard(conn, "customer.read")
            customers = list_qr_customers(
                conn, ws,
                q=q,
                interaction_type=itype if itype in INTERACTION_TYPES else "",
                experience_id=int(exp_id) if exp_id and exp_id.isdigit() else None,
            )
            return jsonify({"customers": customers})

    @app.get("/api/customers/qr/<int:customer_id>")
    @login_required
    def api_qr_customer_detail(customer_id):
        with db() as conn:
            ws = _guard(conn, "customer.read")
            detail = customer_detail(conn, customer_id, ws)
            if not detail:
                abort(404)
            return jsonify(detail)

    @app.delete("/api/customers/qr/<int:customer_id>")
    @login_required
    def api_qr_customer_delete(customer_id):
        """Privacy — remove QR interaction data for a customer."""
        with db() as conn:
            ws = _guard(conn, "customer.manage")
            cp = conn.execute(
                "SELECT id FROM customer_profiles WHERE id=? AND workspace_id=?",
                (customer_id, ws),
            ).fetchone()
            if not cp:
                abort(404)
            conn.execute(
                "DELETE FROM qr_customer_interactions WHERE customer_id=? AND workspace_id=?",
                (customer_id, ws),
            )
            conn.execute(
                "DELETE FROM qr_customer_identities WHERE customer_id=? AND workspace_id=?",
                (customer_id, ws),
            )
            remaining = conn.execute(
                "SELECT COUNT(*) AS c FROM qr_customer_interactions WHERE customer_id=?",
                (customer_id,),
            ).fetchone()["c"]
            if not remaining:
                conn.execute(
                    "UPDATE customer_profiles SET status='archived', updated_at=? WHERE id=?",
                    (_now(), customer_id),
                )
            return jsonify({"ok": True})

    app.init_qr_customer_tables = init_qr_customer_tables
