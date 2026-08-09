"""Universal Customer Platform — identity layer for Business OS."""

from __future__ import annotations

import csv
import io
import json
import secrets
from datetime import datetime

from flask import abort, jsonify, request, session

CUSTOMER_STATUSES = ("active", "inactive", "blocked", "archived")
ACTIVITY_TYPES = (
    "joined", "visit", "qr_scan", "check_in", "feedback", "review", "survey",
    "event", "purchase", "appointment", "membership", "note", "tag", "import", "merge",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customer_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    customer_code TEXT UNIQUE NOT NULL,
    avatar_url TEXT,
    full_name TEXT NOT NULL DEFAULT '',
    preferred_name TEXT,
    email TEXT,
    phone TEXT,
    company TEXT,
    birthday TEXT,
    address TEXT,
    language TEXT DEFAULT 'en',
    country TEXT,
    status TEXT DEFAULT 'active',
    assigned_staff_id INTEGER,
    primary_store_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    last_activity_at TEXT,
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#888888',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_id, name),
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_tag_links (
    customer_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (customer_id, tag_id),
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES customer_tags(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    UNIQUE(owner_id, name),
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_group_members (
    customer_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (customer_id, group_id),
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY(group_id) REFERENCES customer_groups(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    author_id INTEGER,
    body TEXT NOT NULL,
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,
    uploaded_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    store_id INTEGER,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    related_object_type TEXT,
    related_object_id INTEGER,
    source TEXT,
    actor TEXT DEFAULT 'system',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_store_links (
    customer_id INTEGER NOT NULL,
    store_id INTEGER NOT NULL,
    visit_count INTEGER DEFAULT 0,
    first_visit_at TEXT,
    last_visit_at TEXT,
    PRIMARY KEY (customer_id, store_id),
    FOREIGN KEY(customer_id) REFERENCES customer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS customer_settings (
    owner_id INTEGER PRIMARY KEY,
    default_status TEXT DEFAULT 'active',
    notify_birthday INTEGER DEFAULT 1,
    notify_new_customer INTEGER DEFAULT 1,
    allow_export INTEGER DEFAULT 1,
    dedupe_by_email INTEGER DEFAULT 1,
    dedupe_by_phone INTEGER DEFAULT 1,
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_customer_profiles_owner ON customer_profiles(owner_id);
CREATE INDEX IF NOT EXISTS idx_customer_profiles_email ON customer_profiles(owner_id, email);
CREATE INDEX IF NOT EXISTS idx_customer_activities_customer ON customer_activities(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_activities_owner ON customer_activities(owner_id);
"""


def _customer_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "")[:10].lower()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _norm_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _norm_phone(phone: str | None) -> str:
    return "".join(c for c in (phone or "") if c.isdigit() or c == "+")


def find_or_create_customer(
    conn,
    owner_id: int,
    *,
    email: str | None = None,
    phone: str | None = None,
    full_name: str | None = None,
    preferred_name: str | None = None,
    company: str | None = None,
    store_id: int | None = None,
    source: str = "unknown",
) -> int | None:
    """Resolve one customer record. Returns None if no identifying info."""
    email_n = _norm_email(email)
    phone_n = _norm_phone(phone)
    name = (full_name or preferred_name or "").strip()
    if not email_n and not phone_n and not name:
        return None

    row = None
    if email_n:
        row = conn.execute(
            "SELECT * FROM customer_profiles WHERE owner_id=? AND lower(email)=?",
            (owner_id, email_n),
        ).fetchone()
    if not row and phone_n:
        row = conn.execute(
            "SELECT * FROM customer_profiles WHERE owner_id=? AND phone=?",
            (owner_id, phone_n),
        ).fetchone()

    now = _now()
    if row:
        customer_id = row["id"]
        updates = []
        params = []
        if name and not row["full_name"]:
            updates.append("full_name=?")
            params.append(name)
        if email_n and not row["email"]:
            updates.append("email=?")
            params.append(email_n)
        if phone_n and not row["phone"]:
            updates.append("phone=?")
            params.append(phone_n)
        if company and not row["company"]:
            updates.append("company=?")
            params.append(company)
        if updates:
            updates.append("updated_at=?")
            params.append(now)
            params.append(customer_id)
            conn.execute(f"UPDATE customer_profiles SET {', '.join(updates)} WHERE id=?", params)
    else:
        cur = conn.execute(
            """INSERT INTO customer_profiles
               (owner_id, customer_code, full_name, preferred_name, email, phone, company,
                primary_store_id, last_activity_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_id, _customer_code(), name or email_n or phone_n or "Customer",
                preferred_name, email_n or None, phone_n or None, company,
                store_id, now, now,
            ),
        )
        customer_id = cur.lastrowid
        log_customer_activity(
            conn, customer_id, owner_id, "joined", "Joined business",
            detail=f"Source: {source}", store_id=store_id, source=source, actor="system",
        )

    if store_id:
        touch_store_link(conn, customer_id, store_id)
        ws = conn.execute("SELECT workspace_id FROM stores WHERE id=?", (store_id,)).fetchone()
        if ws and ws["workspace_id"]:
            conn.execute(
                "UPDATE customer_profiles SET workspace_id=? WHERE id=? AND workspace_id IS NULL",
                (ws["workspace_id"], customer_id),
            )
    conn.execute(
        "UPDATE customer_profiles SET last_activity_at=?, updated_at=? WHERE id=?",
        (now, now, customer_id),
    )
    return customer_id


def touch_store_link(conn, customer_id: int, store_id: int) -> None:
    now = _now()
    link = conn.execute(
        "SELECT * FROM customer_store_links WHERE customer_id=? AND store_id=?",
        (customer_id, store_id),
    ).fetchone()
    if link:
        conn.execute(
            """UPDATE customer_store_links SET visit_count=visit_count+1, last_visit_at=?
               WHERE customer_id=? AND store_id=?""",
            (now, customer_id, store_id),
        )
    else:
        conn.execute(
            """INSERT INTO customer_store_links (customer_id, store_id, visit_count, first_visit_at, last_visit_at)
               VALUES (?, ?, 1, ?, ?)""",
            (customer_id, store_id, now, now),
        )


def log_customer_activity(
    conn,
    customer_id: int,
    owner_id: int,
    activity_type: str,
    title: str,
    *,
    detail: str = "",
    store_id: int | None = None,
    related_object_type: str | None = None,
    related_object_id: int | None = None,
    source: str | None = None,
    actor: str = "system",
) -> None:
    from bos.events import emit, event_type as ev_type

    verb = activity_type if activity_type in ("joined", "updated", "feedback", "event", "visit", "purchase", "archived", "note") else "updated"
    emit(
        conn,
        ev_type("customer", verb),
        "customer",
        customer_id,
        owner_id=owner_id,
        store_id=store_id,
        user_id=owner_id if actor == "owner" else None,
        actor=actor,
        title=title,
        detail=detail,
        metadata={
            "customer_id": customer_id,
            "owner_id": owner_id,
            "related_object_type": related_object_type,
            "related_object_id": related_object_id,
            "source": source,
        },
        href="/app/contacts",
    )


def init_customer_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    for table, column, ddl in (
        ("feedback_records", "customer_id", "INTEGER"),
        ("event_attendees", "customer_id", "INTEGER"),
        ("check_in_log", "customer_id", "INTEGER"),
    ):
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    _backfill_customers(conn)


def _backfill_customers(conn) -> None:
    """Import customers from feedback and event attendees once."""
    for row in conn.execute(
        """SELECT fr.id, fr.customer_name, fr.customer_email, fr.is_anonymous,
                  fr.feedback_type, fr.rating, s.owner_id, s.id AS store_id
           FROM feedback_records fr
           JOIN stores s ON s.id = fr.store_id
           WHERE fr.customer_id IS NULL AND fr.is_anonymous = 0
             AND (fr.customer_email != '' OR fr.customer_name != '')"""
    ).fetchall():
        cid = find_or_create_customer(
            conn, row["owner_id"],
            email=row["customer_email"], full_name=row["customer_name"],
            store_id=row["store_id"], source="feedback_backfill",
        )
        if cid:
            conn.execute("UPDATE feedback_records SET customer_id=? WHERE id=?", (cid, row["id"]))
            log_customer_activity(
                conn, cid, row["owner_id"], "feedback",
                f"{(row['feedback_type'] or 'feedback').title()} submitted",
                detail=f"Rating: {row['rating'] or '—'}",
                store_id=row["store_id"],
                related_object_type="feedback", related_object_id=row["id"],
                source="feedback",
            )

    for row in conn.execute(
        """SELECT ea.id, ea.name, ea.email, e.store_id, s.owner_id
           FROM event_attendees ea
           JOIN events e ON e.id = ea.event_id
           JOIN stores s ON s.id = e.store_id
           WHERE ea.customer_id IS NULL AND (ea.email != '' OR ea.name != '')"""
    ).fetchall():
        cid = find_or_create_customer(
            conn, row["owner_id"],
            email=row["email"], full_name=row["name"],
            store_id=row["store_id"], source="event_backfill",
        )
        if cid:
            conn.execute("UPDATE event_attendees SET customer_id=? WHERE id=?", (cid, row["id"]))
            log_customer_activity(
                conn, cid, row["owner_id"], "event", "Event registration",
                store_id=row["store_id"],
                related_object_type="event_attendee", related_object_id=row["id"],
                source="event_pass",
            )


def register_customer_platform(app) -> None:
    from app import current_user, db, login_required, save_uploaded_image

    def owner_id():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def get_settings(oid: int):
        with db() as conn:
            row = conn.execute("SELECT * FROM customer_settings WHERE owner_id=?", (oid,)).fetchone()
            if not row:
                conn.execute("INSERT INTO customer_settings (owner_id) VALUES (?)", (oid,))
                row = conn.execute("SELECT * FROM customer_settings WHERE owner_id=?", (oid,)).fetchone()
        return row

    def get_customer_or_404(oid: int, customer_id: int):
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM customer_profiles WHERE id=? AND owner_id=?", (customer_id, oid),
            ).fetchone()
        if not row:
            abort(404)
        return row

    def customer_tags(customer_id: int):
        with db() as conn:
            return conn.execute(
                """SELECT ct.* FROM customer_tags ct
                   JOIN customer_tag_links ctl ON ctl.tag_id = ct.id
                   WHERE ctl.customer_id = ? ORDER BY ct.name""",
                (customer_id,),
            ).fetchall()

    def customer_groups_for(customer_id: int):
        with db() as conn:
            return conn.execute(
                """SELECT cg.* FROM customer_groups cg
                   JOIN customer_group_members cgm ON cgm.group_id = cg.id
                   WHERE cgm.customer_id = ? ORDER BY cg.name""",
                (customer_id,),
            ).fetchall()

    def customer_insights(customer_id: int, oid: int) -> dict:
        with db() as conn:
            visits = conn.execute(
                "SELECT COALESCE(SUM(visit_count), 0) AS c FROM customer_store_links WHERE customer_id=?",
                (customer_id,),
            ).fetchone()["c"]
            last_visit = conn.execute(
                "SELECT MAX(last_visit_at) AS d FROM customer_store_links WHERE customer_id=?",
                (customer_id,),
            ).fetchone()["d"]
            feedback_count = conn.execute(
                """SELECT COUNT(*) AS c FROM feedback_records fr
                   JOIN stores s ON s.id = fr.store_id
                   WHERE fr.customer_id=? AND s.owner_id=?""",
                (customer_id, oid),
            ).fetchone()["c"]
            avg_rating = conn.execute(
                """SELECT AVG(fr.rating) AS avg FROM feedback_records fr
                   JOIN stores s ON s.id = fr.store_id
                   WHERE fr.customer_id=? AND s.owner_id=? AND fr.rating IS NOT NULL""",
                (customer_id, oid),
            ).fetchone()["avg"]
            events = conn.execute(
                """SELECT COUNT(*) AS c FROM customer_activities
                   WHERE customer_id=? AND activity_type='event'""",
                (customer_id,),
            ).fetchone()["c"]
            activity_count = conn.execute(
                "SELECT COUNT(*) AS c FROM customer_activities WHERE customer_id=?",
                (customer_id,),
            ).fetchone()["c"]
        return {
            "total_visits": int(visits or 0),
            "last_visit": last_visit,
            "feedback_submitted": int(feedback_count or 0),
            "average_rating": round(float(avg_rating or 0), 1) if avg_rating else None,
            "events_attended": int(events or 0),
            "total_activities": int(activity_count or 0),
        }

    def customer_to_api(row, oid: int) -> dict:
        cid = row["id"]
        tags = [dict(t) for t in customer_tags(cid)]
        groups = [dict(g) for g in customer_groups_for(cid)]
        with db() as conn:
            stores = conn.execute(
                """SELECT s.id, s.name, s.slug, csl.visit_count, csl.last_visit_at
                   FROM customer_store_links csl
                   JOIN stores s ON s.id = csl.store_id
                   WHERE csl.customer_id = ?""",
                (cid,),
            ).fetchall()
        payload = dict(row)
        payload["tags"] = tags
        payload["groups"] = groups
        payload["stores"] = [dict(s) for s in stores]
        payload["display_name"] = row["preferred_name"] or row["full_name"] or row["email"] or f"Customer #{row['customer_code']}"
        return payload

    def list_customers(oid: int, filters=None):
        filters = filters or {}
        query = "SELECT * FROM customer_profiles WHERE owner_id=?"
        params: list = [oid]
        if filters.get("status"):
            query += " AND status=?"
            params.append(filters["status"])
        if filters.get("group_id"):
            query += " AND id IN (SELECT customer_id FROM customer_group_members WHERE group_id=?)"
            params.append(int(filters["group_id"]))
        if filters.get("tag_id"):
            query += " AND id IN (SELECT customer_id FROM customer_tag_links WHERE tag_id=?)"
            params.append(int(filters["tag_id"]))
        if filters.get("store_id"):
            query += " AND id IN (SELECT customer_id FROM customer_store_links WHERE store_id=?)"
            params.append(int(filters["store_id"]))
        if filters.get("workspace_id"):
            query += " AND workspace_id=?"
            params.append(int(filters["workspace_id"]))
        if filters.get("q"):
            like = f"%{filters['q']}%"
            query += " AND (full_name LIKE ? OR preferred_name LIKE ? OR email LIKE ? OR phone LIKE ? OR company LIKE ? OR customer_code LIKE ?)"
            params.extend([like] * 6)
        sort = filters.get("sort", "last_activity_at")
        if sort not in ("full_name", "created_at", "last_activity_at", "email"):
            sort = "last_activity_at"
        query += f" ORDER BY {sort} DESC LIMIT 500"
        with db() as conn:
            return conn.execute(query, params).fetchall()

    def platform_summary(oid: int) -> dict:
        with db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM customer_profiles WHERE owner_id=?", (oid,),
            ).fetchone()["c"]
            active = conn.execute(
                "SELECT COUNT(*) AS c FROM customer_profiles WHERE owner_id=? AND status='active'", (oid,),
            ).fetchone()["c"]
            new_month = conn.execute(
                """SELECT COUNT(*) AS c FROM customer_profiles
                   WHERE owner_id=? AND created_at >= date('now', '-30 days')""", (oid,),
            ).fetchone()["c"]
            pending_followup = conn.execute(
                """SELECT COUNT(DISTINCT cp.id) AS c FROM customer_profiles cp
                   JOIN customer_tag_links ctl ON ctl.customer_id = cp.id
                   JOIN customer_tags ct ON ct.id = ctl.tag_id
                   WHERE cp.owner_id=? AND lower(ct.name) LIKE '%follow%'""", (oid,),
            ).fetchone()["c"]
            recent = conn.execute(
                "SELECT * FROM customer_profiles WHERE owner_id=? ORDER BY created_at DESC LIMIT 5", (oid,),
            ).fetchall()
            recent_activity = conn.execute(
                """SELECT ca.*, cp.full_name, cp.customer_code
                   FROM customer_activities ca
                   JOIN customer_profiles cp ON cp.id = ca.customer_id
                   WHERE ca.owner_id=? ORDER BY ca.created_at DESC LIMIT 10""", (oid,),
            ).fetchall()
        return {
            "total": int(total or 0),
            "active": int(active or 0),
            "new_this_month": int(new_month or 0),
            "pending_followup": int(pending_followup or 0),
            "recent": [customer_to_api(r, oid) for r in recent],
            "recent_activity": [dict(a) for a in recent_activity],
        }

    # --- API ---

    @app.get("/api/customers/summary")
    @login_required
    def api_customers_summary():
        return jsonify(platform_summary(owner_id()))

    @app.get("/api/customers")
    @login_required
    def api_customers_list():
        oid = owner_id()
        filters = {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", ""),
            "group_id": request.args.get("group_id", ""),
            "tag_id": request.args.get("tag_id", ""),
            "store_id": request.args.get("store_id", ""),
            "workspace_id": request.args.get("workspace_id", ""),
            "sort": request.args.get("sort", "last_activity_at"),
        }
        if not filters["workspace_id"] and session.get("active_workspace_id"):
            filters["workspace_id"] = str(session.get("active_workspace_id"))
        rows = list_customers(oid, filters)
        return jsonify([customer_to_api(r, oid) for r in rows])

    @app.get("/api/customers/<int:customer_id>")
    @login_required
    def api_customer_detail(customer_id):
        oid = owner_id()
        row = get_customer_or_404(oid, customer_id)
        payload = customer_to_api(row, oid)
        payload["insights"] = customer_insights(customer_id, oid)
        with db() as conn:
            payload["timeline"] = [
                dict(a) for a in conn.execute(
                    """SELECT ca.*, s.name AS store_name FROM customer_activities ca
                       LEFT JOIN stores s ON s.id = ca.store_id
                       WHERE ca.customer_id=? ORDER BY ca.created_at DESC LIMIT 100""",
                    (customer_id,),
                ).fetchall()
            ]
            payload["notes"] = [
                dict(n) for n in conn.execute(
                    "SELECT * FROM customer_notes WHERE customer_id=? ORDER BY is_pinned DESC, created_at DESC",
                    (customer_id,),
                ).fetchall()
            ]
            payload["files"] = [
                dict(f) for f in conn.execute(
                    "SELECT * FROM customer_files WHERE customer_id=? ORDER BY created_at DESC",
                    (customer_id,),
                ).fetchall()
            ]
            payload["feedback"] = [
                dict(f) for f in conn.execute(
                    """SELECT fr.id, fr.rating, fr.comment, fr.feedback_type, fr.created_at, s.name AS store_name
                       FROM feedback_records fr JOIN stores s ON s.id = fr.store_id
                       WHERE fr.customer_id=? AND s.owner_id=? ORDER BY fr.created_at DESC LIMIT 20""",
                    (customer_id, oid),
                ).fetchall()
            ]
        return jsonify(payload)

    @app.post("/api/customers")
    @login_required
    def api_customer_create():
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        now = _now()
        ws_id = data.get("workspace_id") or session.get("active_workspace_id")
        with db() as conn:
            cur = conn.execute(
                """INSERT INTO customer_profiles
                   (owner_id, workspace_id, customer_code, full_name, preferred_name, email, phone, company,
                    birthday, address, language, country, status, primary_store_id, updated_at, last_activity_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    oid, ws_id, _customer_code(),
                    (data.get("full_name") or "").strip() or "Customer",
                    (data.get("preferred_name") or "").strip() or None,
                    _norm_email(data.get("email")) or None,
                    _norm_phone(data.get("phone")) or None,
                    (data.get("company") or "").strip() or None,
                    data.get("birthday"), (data.get("address") or "").strip() or None,
                    data.get("language") or "en", (data.get("country") or "").strip() or None,
                    data.get("status") or "active",
                    data.get("primary_store_id"), now, now,
                ),
            )
            customer_id = cur.lastrowid
            from bos.collaboration import stamp_create
            stamp_create(conn, "customer_profiles", customer_id, oid)
            log_customer_activity(conn, customer_id, oid, "joined", "Customer created", actor="owner")
            if data.get("primary_store_id"):
                touch_store_link(conn, customer_id, int(data["primary_store_id"]))
            for tag_id in data.get("tag_ids") or []:
                conn.execute(
                    "INSERT OR IGNORE INTO customer_tag_links (customer_id, tag_id) VALUES (?, ?)",
                    (customer_id, int(tag_id)),
                )
            for group_id in data.get("group_ids") or []:
                conn.execute(
                    "INSERT OR IGNORE INTO customer_group_members (customer_id, group_id) VALUES (?, ?)",
                    (customer_id, int(group_id)),
                )
            row = conn.execute("SELECT * FROM customer_profiles WHERE id=?", (customer_id,)).fetchone()
        return jsonify(customer_to_api(row, oid)), 201

    @app.patch("/api/customers/<int:customer_id>")
    @login_required
    def api_customer_update(customer_id):
        oid = owner_id()
        get_customer_or_404(oid, customer_id)
        data = request.get_json(silent=True) or {}
        fields = (
            "full_name", "preferred_name", "email", "phone", "company", "birthday",
            "address", "language", "country", "status", "primary_store_id", "avatar_url",
        )
        updates = []
        params = []
        for f in fields:
            if f in data:
                val = data[f]
                if f == "email":
                    val = _norm_email(val) or None
                elif f == "phone":
                    val = _norm_phone(val) or None
                elif isinstance(val, str):
                    val = val.strip() or None
                updates.append(f"{f}=?")
                params.append(val)
        if not updates:
            return jsonify({"ok": True})
        updates.append("updated_at=?")
        params.append(_now())
        params.append(customer_id)
        with db() as conn:
            conn.execute(
                f"UPDATE customer_profiles SET {', '.join(updates)} WHERE id=? AND owner_id=?",
                params + [oid],
            )
            row = conn.execute("SELECT * FROM customer_profiles WHERE id=?", (customer_id,)).fetchone()
            log_customer_activity(
                conn, customer_id, oid, "updated", "Customer updated",
                actor="owner",
            )
        return jsonify(customer_to_api(row, oid))

    @app.delete("/api/customers/<int:customer_id>")
    @login_required
    def api_customer_delete(customer_id):
        oid = owner_id()
        get_customer_or_404(oid, customer_id)
        with db() as conn:
            conn.execute("UPDATE feedback_records SET customer_id=NULL WHERE customer_id=?", (customer_id,))
            conn.execute("DELETE FROM customer_profiles WHERE id=? AND owner_id=?", (customer_id, oid))
            from bos.events import emit, event_type as ev_type
            emit(
                conn, ev_type("customer", "deleted"), "customer", customer_id,
                owner_id=oid, user_id=oid, actor="owner",
                title="Customer deleted", href="/app/contacts",
                metadata={"customer_id": customer_id, "owner_id": oid},
            )
        return jsonify({"ok": True})

    @app.post("/api/customers/batch")
    @login_required
    def api_customers_batch():
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        ids = [int(i) for i in (data.get("ids") or [])]
        if not ids:
            return jsonify({"error": "No customers selected"}), 400
        placeholders = ",".join("?" * len(ids))
        with db() as conn:
            owned = conn.execute(
                f"SELECT id FROM customer_profiles WHERE owner_id=? AND id IN ({placeholders})",
                [oid, *ids],
            ).fetchall()
            valid_ids = [r["id"] for r in owned]
            if action == "archive":
                conn.execute(
                    f"UPDATE customer_profiles SET status='archived', updated_at=? WHERE id IN ({','.join('?'*len(valid_ids))})",
                    [_now(), *valid_ids],
                )
                for cid in valid_ids:
                    log_customer_activity(conn, cid, oid, "archived", "Customer archived", actor="owner")
            elif action == "delete":
                conn.execute(
                    f"UPDATE feedback_records SET customer_id=NULL WHERE customer_id IN ({','.join('?'*len(valid_ids))})",
                    valid_ids,
                )
                conn.execute(
                    f"DELETE FROM customer_profiles WHERE id IN ({','.join('?'*len(valid_ids))})",
                    valid_ids,
                )
                from bos.events import emit, event_type as ev_type
                for cid in valid_ids:
                    emit(
                        conn, ev_type("customer", "deleted"), "customer", cid,
                        owner_id=oid, user_id=oid, actor="owner",
                        title="Customer deleted", metadata={"customer_id": cid, "owner_id": oid},
                    )
            elif action == "add_tags":
                for cid in valid_ids:
                    for tag_id in data.get("tag_ids") or []:
                        conn.execute(
                            "INSERT OR IGNORE INTO customer_tag_links (customer_id, tag_id) VALUES (?, ?)",
                            (cid, int(tag_id)),
                        )
            elif action == "remove_tags":
                for cid in valid_ids:
                    for tag_id in data.get("tag_ids") or []:
                        conn.execute(
                            "DELETE FROM customer_tag_links WHERE customer_id=? AND tag_id=?",
                            (cid, int(tag_id)),
                        )
            elif action == "add_groups":
                for cid in valid_ids:
                    for group_id in data.get("group_ids") or []:
                        conn.execute(
                            "INSERT OR IGNORE INTO customer_group_members (customer_id, group_id) VALUES (?, ?)",
                            (cid, int(group_id)),
                        )
            elif action == "remove_groups":
                for cid in valid_ids:
                    for group_id in data.get("group_ids") or []:
                        conn.execute(
                            "DELETE FROM customer_group_members WHERE customer_id=? AND group_id=?",
                            (cid, int(group_id)),
                        )
            else:
                return jsonify({"error": "Unknown action"}), 400
        return jsonify({"ok": True, "count": len(valid_ids)})

    @app.get("/api/customers/tags")
    @login_required
    def api_customer_tags_list():
        oid = owner_id()
        with db() as conn:
            rows = conn.execute(
                """SELECT ct.*, COUNT(ctl.customer_id) AS usage_count
                   FROM customer_tags ct
                   LEFT JOIN customer_tag_links ctl ON ctl.tag_id = ct.id
                   WHERE ct.owner_id=? GROUP BY ct.id ORDER BY ct.name""",
                (oid,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/customers/tags")
    @login_required
    def api_customer_tags_create():
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        with db() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO customer_tags (owner_id, name, color) VALUES (?, ?, ?)",
                    (oid, name, data.get("color") or "#888888"),
                )
                row = conn.execute("SELECT * FROM customer_tags WHERE id=?", (cur.lastrowid,)).fetchone()
            except Exception:
                return jsonify({"error": "Tag already exists"}), 409
        return jsonify(dict(row)), 201

    @app.delete("/api/customers/tags/<int:tag_id>")
    @login_required
    def api_customer_tags_delete(tag_id):
        oid = owner_id()
        with db() as conn:
            conn.execute("DELETE FROM customer_tags WHERE id=? AND owner_id=?", (tag_id, oid))
        return jsonify({"ok": True})

    @app.get("/api/customers/groups")
    @login_required
    def api_customer_groups_list():
        oid = owner_id()
        with db() as conn:
            rows = conn.execute(
                """SELECT cg.*, COUNT(cgm.customer_id) AS member_count
                   FROM customer_groups cg
                   LEFT JOIN customer_group_members cgm ON cgm.group_id = cg.id
                   WHERE cg.owner_id=? GROUP BY cg.id ORDER BY cg.name""",
                (oid,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/customers/groups")
    @login_required
    def api_customer_groups_create():
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        with db() as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO customer_groups (owner_id, name, description, updated_at) VALUES (?, ?, ?, ?)",
                    (oid, name, (data.get("description") or "").strip(), _now()),
                )
                row = conn.execute("SELECT * FROM customer_groups WHERE id=?", (cur.lastrowid,)).fetchone()
            except Exception:
                return jsonify({"error": "Group already exists"}), 409
        return jsonify(dict(row)), 201

    @app.patch("/api/customers/groups/<int:group_id>")
    @login_required
    def api_customer_groups_update(group_id):
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            if "name" in data:
                conn.execute(
                    "UPDATE customer_groups SET name=?, updated_at=? WHERE id=? AND owner_id=?",
                    (data["name"].strip(), _now(), group_id, oid),
                )
            if "description" in data:
                conn.execute(
                    "UPDATE customer_groups SET description=?, updated_at=? WHERE id=? AND owner_id=?",
                    (data["description"].strip(), _now(), group_id, oid),
                )
            if "status" in data:
                conn.execute(
                    "UPDATE customer_groups SET status=?, updated_at=? WHERE id=? AND owner_id=?",
                    (data["status"], _now(), group_id, oid),
                )
            row = conn.execute(
                "SELECT * FROM customer_groups WHERE id=? AND owner_id=?", (group_id, oid),
            ).fetchone()
        if not row:
            abort(404)
        return jsonify(dict(row))

    @app.delete("/api/customers/groups/<int:group_id>")
    @login_required
    def api_customer_groups_delete(group_id):
        oid = owner_id()
        with db() as conn:
            conn.execute("DELETE FROM customer_groups WHERE id=? AND owner_id=?", (group_id, oid))
        return jsonify({"ok": True})

    @app.get("/api/customers/activity")
    @login_required
    def api_customers_activity():
        oid = owner_id()
        limit = min(request.args.get("limit", 50, type=int), 200)
        with db() as conn:
            rows = conn.execute(
                """SELECT ca.*, cp.full_name, cp.customer_code, cp.email, s.name AS store_name
                   FROM customer_activities ca
                   JOIN customer_profiles cp ON cp.id = ca.customer_id
                   LEFT JOIN stores s ON s.id = ca.store_id
                   WHERE ca.owner_id=? ORDER BY ca.created_at DESC LIMIT ?""",
                (oid, limit),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/customers/settings")
    @login_required
    def api_customer_settings_get():
        return jsonify(dict(get_settings(owner_id())))

    @app.post("/api/customers/settings")
    @login_required
    def api_customer_settings_save():
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        with db() as conn:
            conn.execute(
                """INSERT INTO customer_settings (owner_id, default_status, notify_birthday,
                   notify_new_customer, allow_export, dedupe_by_email, dedupe_by_phone)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(owner_id) DO UPDATE SET
                   default_status=excluded.default_status,
                   notify_birthday=excluded.notify_birthday,
                   notify_new_customer=excluded.notify_new_customer,
                   allow_export=excluded.allow_export,
                   dedupe_by_email=excluded.dedupe_by_email,
                   dedupe_by_phone=excluded.dedupe_by_phone""",
                (
                    oid,
                    data.get("default_status", "active"),
                    1 if data.get("notify_birthday", True) else 0,
                    1 if data.get("notify_new_customer", True) else 0,
                    1 if data.get("allow_export", True) else 0,
                    1 if data.get("dedupe_by_email", True) else 0,
                    1 if data.get("dedupe_by_phone", True) else 0,
                ),
            )
        return jsonify({"ok": True})

    @app.post("/api/customers/<int:customer_id>/notes")
    @login_required
    def api_customer_note_create(customer_id):
        oid = owner_id()
        get_customer_or_404(oid, customer_id)
        data = request.get_json(silent=True) or {}
        body = (data.get("body") or "").strip()
        if not body:
            return jsonify({"error": "Note body required"}), 400
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO customer_notes (customer_id, author_id, body, is_pinned) VALUES (?, ?, ?, ?)",
                (customer_id, oid, body, 1 if data.get("is_pinned") else 0),
            )
            log_customer_activity(
                conn, customer_id, oid, "note", "Note added",
                detail=body[:120], actor="owner",
            )
            row = conn.execute("SELECT * FROM customer_notes WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201

    @app.delete("/api/customers/notes/<int:note_id>")
    @login_required
    def api_customer_note_delete(note_id):
        oid = owner_id()
        with db() as conn:
            note = conn.execute(
                """SELECT n.* FROM customer_notes n
                   JOIN customer_profiles cp ON cp.id = n.customer_id
                   WHERE n.id=? AND cp.owner_id=?""",
                (note_id, oid),
            ).fetchone()
            if not note:
                abort(404)
            conn.execute("DELETE FROM customer_notes WHERE id=?", (note_id,))
        return jsonify({"ok": True})

    @app.get("/api/customers/export")
    @login_required
    def api_customers_export():
        oid = owner_id()
        ids = request.args.get("ids", "")
        if ids:
            id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
            placeholders = ",".join("?" * len(id_list))
            query = f"SELECT * FROM customer_profiles WHERE owner_id=? AND id IN ({placeholders})"
            params = [oid, *id_list]
        else:
            query = "SELECT * FROM customer_profiles WHERE owner_id=?"
            params = [oid]
        with db() as conn:
            rows = conn.execute(query, params).fetchall()
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["customer_code", "full_name", "preferred_name", "email", "phone",
                        "company", "status", "country", "created_at", "last_activity_at"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in writer.fieldnames})
        return output.getvalue(), 200, {
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=customers.csv",
        }

    @app.post("/api/customers/import")
    @login_required
    def api_customers_import():
        oid = owner_id()
        data = request.get_json(silent=True) or {}
        rows = data.get("rows") or []
        created = merged = 0
        with db() as conn:
            for row in rows:
                email = _norm_email(row.get("email"))
                phone = _norm_phone(row.get("phone"))
                name = (row.get("full_name") or row.get("name") or "").strip()
                existing_id = None
                if email:
                    ex = conn.execute(
                        "SELECT id FROM customer_profiles WHERE owner_id=? AND lower(email)=?",
                        (oid, email),
                    ).fetchone()
                    if ex:
                        existing_id = ex["id"]
                if not existing_id and phone:
                    ex = conn.execute(
                        "SELECT id FROM customer_profiles WHERE owner_id=? AND phone=?",
                        (oid, phone),
                    ).fetchone()
                    if ex:
                        existing_id = ex["id"]
                if existing_id:
                    merged += 1
                    continue
                cid = find_or_create_customer(
                    conn, oid, email=email, phone=phone, full_name=name,
                    company=row.get("company"), source="csv_import",
                )
                if cid:
                    created += 1
        return jsonify({"created": created, "merged": merged})

    app.resolve_customer = lambda conn, owner_id, **kw: find_or_create_customer(conn, owner_id, **kw)
    app.log_customer_activity = lambda conn, *a, **kw: log_customer_activity(conn, *a, **kw)
