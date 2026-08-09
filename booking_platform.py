"""Booking Platform — core operational scheduling for Business OS."""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import abort, jsonify, request, session

BOOKING_STATUSES = ("pending", "confirmed", "checked_in", "completed", "cancelled", "no_show")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    contact_id INTEGER,
    title TEXT NOT NULL,
    customer_name TEXT,
    customer_email TEXT,
    customer_phone TEXT,
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed',
    notes TEXT,
    created_by INTEGER,
    updated_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bookings_workspace ON bookings(workspace_id);
CREATE INDEX IF NOT EXISTS idx_bookings_starts ON bookings(starts_at);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
"""


def _ensure_booking_indexes(conn) -> None:
    if _column_exists(conn, "bookings", "contact_id"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_contact ON bookings(contact_id)")
    if _column_exists(conn, "bookings", "assigned_member_id"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_assigned ON bookings(assigned_member_id)")


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _default_end(starts_at: str) -> str:
    try:
        raw = starts_at.replace(" ", "T")
        start = datetime.fromisoformat(raw)
        return (start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return starts_at


def _column_exists(conn, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def _migrate_booking_schema(conn) -> None:
    migrations = (
        ("service_id", "INTEGER"),
        ("assigned_member_id", "INTEGER"),
        ("calendar_event_id", "INTEGER"),
        ("location", "TEXT DEFAULT ''"),
    )
    for col, typedef in migrations:
        if not _column_exists(conn, table="bookings", col=col):
            conn.execute(f"ALTER TABLE bookings ADD COLUMN {col} {typedef}")


def init_booking_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _migrate_booking_schema(conn)
    _ensure_booking_indexes(conn)


def _contact_snapshot(conn, contact_id: int | None, owner_id: int) -> dict | None:
    if not contact_id:
        return None
    row = conn.execute(
        """SELECT id, full_name, email, phone FROM customer_profiles
           WHERE id=? AND owner_id=? AND status!='archived'""",
        (contact_id, owner_id),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["full_name"] or "",
        "email": row["email"] or "",
        "phone": row["phone"] or "",
    }


def _member_snapshot(conn, workspace_id: int, user_id: int | None) -> dict | None:
    if not user_id:
        return None
    row = conn.execute(
        """SELECT wm.user_id, wm.role, u.email, u.display_name
           FROM workspace_members wm
           JOIN users u ON u.id = wm.user_id
           WHERE wm.workspace_id=? AND wm.user_id=? AND wm.status='active'""",
        (workspace_id, user_id),
    ).fetchone()
    if not row:
        return None
    return {
        "user_id": row["user_id"],
        "name": row["display_name"] or row["email"],
        "email": row["email"],
        "role": row["role"],
    }


def _sync_calendar(conn, booking: dict) -> int | None:
    from calendar_platform import upsert_booking_event

    event_id = upsert_booking_event(conn, booking, emit_events=True)
    if event_id:
        conn.execute(
            "UPDATE bookings SET calendar_event_id=? WHERE id=?",
            (event_id, booking["id"]),
        )
    return event_id


def register_booking_platform(app) -> None:
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

    def booking_to_api(conn, row, *, viewer_id: int | None = None) -> dict:
        contact = None
        if row["contact_id"] and viewer_id:
            contact = _contact_snapshot(conn, int(row["contact_id"]), viewer_id)
        assignee = _member_snapshot(conn, int(row["workspace_id"]), row["assigned_member_id"])
        customer_name = (contact or {}).get("name") or row["customer_name"]
        customer_email = (contact or {}).get("email") or row["customer_email"]
        customer_phone = (contact or {}).get("phone") or row["customer_phone"]
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "contact_id": row["contact_id"],
            "customer_id": row["contact_id"],
            "service_id": row["service_id"] if "service_id" in row.keys() else None,
            "assigned_member_id": row["assigned_member_id"] if "assigned_member_id" in row.keys() else None,
            "calendar_event_id": row["calendar_event_id"] if "calendar_event_id" in row.keys() else None,
            "title": row["title"],
            "customer": {
                "id": row["contact_id"],
                "name": customer_name,
                "email": customer_email,
                "phone": customer_phone,
            },
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "assignee": assignee,
            "starts_at": row["starts_at"],
            "ends_at": row["ends_at"],
            "location": row["location"] if "location" in row.keys() else "",
            "status": row["status"],
            "notes": row["notes"],
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_booking(conn, booking_id: int, workspace_id: int):
        row = conn.execute(
            "SELECT * FROM bookings WHERE id=? AND workspace_id=?", (booking_id, workspace_id),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def _validate_contact(conn, contact_id: int | None, owner_id: int) -> None:
        if contact_id is None:
            return
        row = conn.execute(
            "SELECT 1 FROM customer_profiles WHERE id=? AND owner_id=? AND status!='archived'",
            (contact_id, owner_id),
        ).fetchone()
        if not row:
            abort(400, description="Invalid customer reference")

    def _validate_assignee(conn, workspace_id: int, member_id: int | None) -> None:
        if member_id is None:
            return
        row = conn.execute(
            """SELECT 1 FROM workspace_members
               WHERE workspace_id=? AND user_id=? AND status='active'""",
            (workspace_id, member_id),
        ).fetchone()
        if not row:
            abort(400, description="Assigned member must be an active workspace member")

    def _apply_contact_fields(conn, data: dict, owner_id: int) -> dict:
        contact_id = data.get("contact_id") or data.get("customer_id")
        if not contact_id:
            return data
        snap = _contact_snapshot(conn, int(contact_id), owner_id)
        if not snap:
            abort(400, description="Invalid customer reference")
        out = dict(data)
        out["contact_id"] = int(contact_id)
        out.setdefault("customer_name", snap["name"])
        out.setdefault("customer_email", snap["email"])
        out.setdefault("customer_phone", snap["phone"])
        if not out.get("title"):
            out["title"] = snap["name"] or "Booking"
        return out

    def _emit(conn, event_type, booking_id, title, **kw):
        from bos.events import emit
        emit(conn, event_type, "booking", booking_id, workspace_id=ws_id(), user_id=uid(),
             actor="member", title=title, href=f"/app/booking#booking/{booking_id}", **kw)

    @app.get("/api/bookings/summary")
    @login_required
    def api_bookings_summary():
        oid = uid()
        ws = ws_id()
        if not ws:
            return jsonify({"today": 0, "upcoming": 0, "recent": []})
        today = _today()
        with db() as conn:
            _guard(conn, "booking.read")
            today_count = conn.execute(
                """SELECT COUNT(*) AS c FROM bookings
                   WHERE workspace_id=? AND date(starts_at)=? AND status NOT IN ('cancelled')""",
                (ws, today),
            ).fetchone()["c"]
            upcoming = conn.execute(
                """SELECT COUNT(*) AS c FROM bookings
                   WHERE workspace_id=? AND starts_at >= ? AND status IN ('pending','confirmed')""",
                (ws, _now()),
            ).fetchone()["c"]
            recent = conn.execute(
                """SELECT * FROM bookings WHERE workspace_id=?
                   ORDER BY starts_at DESC LIMIT 5""",
                (ws,),
            ).fetchall()
        return jsonify({
            "today": int(today_count),
            "upcoming": int(upcoming),
            "recent": [booking_to_api(conn, r, viewer_id=oid) for r in recent],
        })

    @app.get("/api/bookings")
    @login_required
    def api_bookings_list():
        oid = uid()
        ws = ws_id()
        if not ws:
            return jsonify([])
        view = request.args.get("view", "all")
        status = request.args.get("status", "")
        date = request.args.get("date", "")
        assigned = request.args.get("assigned_member_id", "")
        q = request.args.get("q", "").strip()
        with db() as conn:
            _guard(conn, "booking.read")
            query = "SELECT * FROM bookings WHERE workspace_id=?"
            params: list = [ws]
            if view == "today":
                query += " AND date(starts_at)=?"
                params.append(_today())
            elif view == "upcoming":
                query += " AND starts_at >= ? AND status IN ('pending','confirmed','checked_in')"
                params.append(_now())
            if status:
                query += " AND status=?"
                params.append(status)
            if date:
                query += " AND date(starts_at)=?"
                params.append(date)
            if assigned:
                query += " AND assigned_member_id=?"
                params.append(int(assigned))
            if q:
                query += """ AND (
                    CAST(id AS TEXT) LIKE ?
                    OR customer_name LIKE ?
                    OR title LIKE ?
                    OR customer_email LIKE ?
                    OR customer_phone LIKE ?
                )"""
                like = f"%{q}%"
                params.extend([like, like, like, like, like])
            query += " ORDER BY starts_at ASC LIMIT 500"
            rows = conn.execute(query, params).fetchall()
        return jsonify([booking_to_api(conn, r, viewer_id=oid) for r in rows])

    @app.get("/api/bookings/<int:booking_id>")
    @login_required
    def api_booking_detail(booking_id):
        oid = uid()
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "booking.read")
            row = get_booking(conn, booking_id, int(ws))
            payload = booking_to_api(conn, row, viewer_id=oid)
            if row["calendar_event_id"]:
                cal = conn.execute(
                    "SELECT id, start_time, end_time, status FROM calendar_events WHERE id=?",
                    (row["calendar_event_id"],),
                ).fetchone()
                if cal:
                    payload["calendar"] = dict(cal)
            return jsonify(payload)

    @app.get("/api/bookings/<int:booking_id>/activity")
    @login_required
    def api_booking_activity(booking_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "booking.read")
            get_booking(conn, booking_id, int(ws))
            rows = conn.execute(
                """SELECT event_id, event_type, title, detail, user_id, actor, created_at, metadata
                   FROM domain_events
                   WHERE object_type='booking' AND object_id=?
                   ORDER BY created_at DESC LIMIT 50""",
                (booking_id,),
            ).fetchall()
            return jsonify([dict(r) for r in rows])

    @app.post("/api/bookings")
    @login_required
    def api_booking_create():
        oid = uid()
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "booking.create")
            data = _apply_contact_fields(conn, data, oid)
            contact_id = data.get("contact_id")
            if not contact_id and not (data.get("customer_name") or "").strip():
                return jsonify({"error": "Customer is required (select a contact or enter a name)"}), 400
            title = (data.get("title") or data.get("customer_name") or "").strip()
            starts_at = (data.get("starts_at") or "").strip()
            if not title or not starts_at:
                return jsonify({"error": "Service/title and start time required"}), 400
            assigned = data.get("assigned_member_id")
            if assigned:
                _guard(conn, "booking.assign")
                _validate_assignee(conn, int(ws), int(assigned))
            status = data.get("status") or "confirmed"
            if status not in BOOKING_STATUSES:
                status = "confirmed"
            cur = conn.execute(
                """INSERT INTO bookings
                   (workspace_id, contact_id, service_id, assigned_member_id, title,
                    customer_name, customer_email, customer_phone,
                    starts_at, ends_at, location, status, notes, created_by, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ws, contact_id, data.get("service_id"), assigned,
                    title,
                    (data.get("customer_name") or "").strip() or None,
                    (data.get("customer_email") or "").strip() or None,
                    (data.get("customer_phone") or "").strip() or None,
                    starts_at, data.get("ends_at") or _default_end(starts_at),
                    (data.get("location") or "").strip(),
                    status,
                    (data.get("notes") or "").strip() or None,
                    oid, oid, _now(),
                ),
            )
            bid = cur.lastrowid
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
            _sync_calendar(conn, dict(row))
            _emit(conn, "booking.created", bid, f"Booking created: {title}",
                  metadata={"status": status, "contact_id": contact_id})
            if assigned:
                _emit(conn, "booking.assigned", bid, "Staff assigned to booking",
                      metadata={"assigned_member_id": assigned})
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
            payload = booking_to_api(conn, row, viewer_id=oid)
        return jsonify(payload), 201

    @app.patch("/api/bookings/<int:booking_id>")
    @login_required
    def api_booking_update(booking_id):
        oid = uid()
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "booking.update")
            before = get_booking(conn, booking_id, int(ws))
            if "contact_id" in data or "customer_id" in data:
                data = _apply_contact_fields(conn, data, oid)
            if "assigned_member_id" in data:
                _guard(conn, "booking.assign")
                _validate_assignee(conn, int(ws), data["assigned_member_id"])
            fields = (
                "title", "customer_name", "customer_email", "customer_phone",
                "starts_at", "ends_at", "status", "notes", "contact_id",
                "service_id", "assigned_member_id", "location",
            )
            updates, params = [], []
            for f in fields:
                if f in data:
                    if f == "status" and data[f] not in BOOKING_STATUSES:
                        continue
                    updates.append(f"{f}=?")
                    params.append(data[f])
            if updates:
                updates.extend(["updated_by=?", "updated_at=?"])
                params.extend([oid, _now(), booking_id, ws])
                conn.execute(
                    f"UPDATE bookings SET {', '.join(updates)} WHERE id=? AND workspace_id=?",
                    params,
                )
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            _sync_calendar(conn, dict(row))
            _emit(conn, "booking.updated", booking_id, "Booking updated")
            if "status" in data and data["status"] != before["status"]:
                _emit(conn, "booking.status_changed", booking_id,
                      f"Status changed to {data['status']}",
                      metadata={"from": before["status"], "to": data["status"]})
                if data["status"] == "completed":
                    from feedback_core_platform import maybe_create_feedback_request
                    row_now = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
                    maybe_create_feedback_request(
                        conn,
                        workspace_id=int(ws),
                        customer_id=int(row_now["contact_id"]) if row_now["contact_id"] else None,
                        booking_id=booking_id,
                    )
            if "assigned_member_id" in data and data["assigned_member_id"] != before["assigned_member_id"]:
                _emit(conn, "booking.assigned", booking_id, "Staff assignment updated",
                      metadata={"assigned_member_id": data["assigned_member_id"]})
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        return jsonify(booking_to_api(conn, row, viewer_id=oid))

    @app.post("/api/bookings/<int:booking_id>/assign")
    @login_required
    def api_booking_assign(booking_id):
        oid = uid()
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        member_id = data.get("assigned_member_id")
        if member_id is None:
            return jsonify({"error": "assigned_member_id required"}), 400
        with db() as conn:
            _guard(conn, "booking.assign")
            before = get_booking(conn, booking_id, int(ws))
            _validate_assignee(conn, int(ws), int(member_id))
            conn.execute(
                "UPDATE bookings SET assigned_member_id=?, updated_by=?, updated_at=? WHERE id=?",
                (int(member_id), oid, _now(), booking_id),
            )
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            _sync_calendar(conn, dict(row))
            _emit(conn, "booking.assigned", booking_id, "Staff assigned to booking",
                  metadata={"assigned_member_id": member_id, "previous": before["assigned_member_id"]})
        return jsonify(booking_to_api(conn, row, viewer_id=oid))

    @app.post("/api/bookings/<int:booking_id>/cancel")
    @login_required
    def api_booking_cancel(booking_id):
        oid = uid()
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "booking.cancel")
            before = get_booking(conn, booking_id, int(ws))
            conn.execute(
                "UPDATE bookings SET status='cancelled', updated_by=?, updated_at=? WHERE id=?",
                (oid, _now(), booking_id),
            )
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            _sync_calendar(conn, dict(row))
            _emit(conn, "booking.cancelled", booking_id, "Booking cancelled",
                  metadata={"previous_status": before["status"]})
        return jsonify({"ok": True})

    app.init_booking_tables = init_booking_tables
