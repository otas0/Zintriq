"""Calendar Core Platform — native operational timeline for Business OS."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from flask import abort, jsonify, request, session

EVENT_TYPES = ("booking", "meeting", "appointment", "check_in", "business_event", "reminder")
EVENT_SOURCES = ("business_os", "google_calendar", "microsoft_calendar")
VISIBILITY_LEVELS = ("private", "team", "workspace")
EVENT_STATUSES = ("confirmed", "cancelled", "deleted", "archived")
OPERATIONAL_STATUSES = ("scheduled", "checked_in", "completed")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    created_by INTEGER,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    event_type TEXT NOT NULL DEFAULT 'business_event',
    start_time TEXT NOT NULL,
    end_time TEXT,
    location TEXT DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'workspace',
    source TEXT NOT NULL DEFAULT 'business_os',
    external_provider TEXT,
    external_event_id TEXT,
    related_entity_type TEXT,
    related_entity_id INTEGER,
    status TEXT NOT NULL DEFAULT 'confirmed',
    operational_status TEXT DEFAULT 'scheduled',
    updated_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_calendar_events_workspace ON calendar_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_calendar_events_related
    ON calendar_events(workspace_id, related_entity_type, related_entity_id);

CREATE TABLE IF NOT EXISTS calendar_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_id INTEGER,
    email TEXT,
    name TEXT DEFAULT '',
    role TEXT DEFAULT 'attendee',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(event_id) REFERENCES calendar_events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_calendar_participants_event ON calendar_participants(event_id);
CREATE INDEX IF NOT EXISTS idx_calendar_participants_user ON calendar_participants(user_id);

CREATE TABLE IF NOT EXISTS calendar_sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    connection_id INTEGER,
    direction TEXT NOT NULL DEFAULT 'outbound',
    status TEXT NOT NULL,
    error_message TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_calendar_sync_logs_event ON calendar_sync_logs(event_id, created_at DESC);

CREATE TABLE IF NOT EXISTS calendar_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER,
    role TEXT,
    permission TEXT NOT NULL,
    granted INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workspace_id, user_id, role, permission)
);
CREATE INDEX IF NOT EXISTS idx_calendar_permissions_ws ON calendar_permissions(workspace_id, role);

CREATE TABLE IF NOT EXISTS calendar_sync_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    calendar_event_id INTEGER NOT NULL,
    external_event_id TEXT NOT NULL,
    os_start_time TEXT NOT NULL,
    google_start_time TEXT NOT NULL,
    os_title TEXT DEFAULT '',
    google_title TEXT DEFAULT '',
    os_end_time TEXT,
    google_end_time TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    resolution TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY(calendar_event_id) REFERENCES calendar_events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_calendar_conflicts_ws ON calendar_sync_conflicts(workspace_id, status);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _normalize_time(value: str | None) -> str:
    """Store/compare times as YYYY-MM-DD HH:MM:SS (handles datetime-local T format)."""
    if not value:
        return value or ""
    s = value.strip().replace("T", " ").replace("Z", "")
    if len(s) == 10:
        return f"{s} 00:00:00"
    if len(s) == 16:
        return f"{s}:00"
    return s


def _default_end(start_time: str) -> str:
    try:
        raw = _normalize_time(start_time).replace(" ", "T")
        start = datetime.fromisoformat(raw)
        return (start + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return _normalize_time(start_time)


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s[:10], "%Y-%m-%d")


def _week_range(date_str: str) -> tuple[str, str]:
    d = _parse_date(date_str)
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d 23:59:59")


def _month_range(date_str: str) -> tuple[str, str]:
    d = _parse_date(date_str)
    start = d.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1, day=1)
    else:
        next_month = start.replace(month=start.month + 1, day=1)
    end = next_month - timedelta(seconds=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d 23:59:59")


def _column_exists(conn, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def _migrate_calendar_schema(conn) -> None:
    if not _column_exists(conn, "calendar_events", "operational_status"):
        conn.execute(
            "ALTER TABLE calendar_events ADD COLUMN operational_status TEXT DEFAULT 'scheduled'"
        )
    conn.execute(
        """UPDATE calendar_events SET operational_status='scheduled'
           WHERE operational_status IS NULL OR operational_status=''"""
    )


def seed_calendar_permissions(conn) -> None:
    from bos.permissions import ROLE_PERMISSIONS

    cal_perms = ("calendar.read", "calendar.create", "calendar.update")
    for role, perms in ROLE_PERMISSIONS.items():
        for perm in cal_perms:
            if perm in perms:
                conn.execute(
                    """INSERT OR IGNORE INTO calendar_permissions
                       (workspace_id, role, permission, granted)
                       VALUES (0, ?, ?, 1)""",
                    (role, perm),
                )


def init_calendar_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _migrate_calendar_schema(conn)
    seed_calendar_permissions(conn)
    conn.execute(
        """UPDATE calendar_events SET
           start_time=replace(start_time, 'T', ' '),
           end_time=CASE WHEN end_time IS NOT NULL THEN replace(end_time, 'T', ' ') ELSE end_time END
           WHERE start_time LIKE '%T%'"""
    )
    for booking in conn.execute("SELECT * FROM bookings").fetchall():
        upsert_booking_event(conn, dict(booking), emit_events=False)
    for checkin in conn.execute("SELECT * FROM check_ins").fetchall():
        upsert_checkin_event(conn, dict(checkin), emit_events=False)


def _participants_for_event(conn, event_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM calendar_participants WHERE event_id=? ORDER BY id",
        (event_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "email": r["email"],
            "name": r["name"],
            "role": r["role"],
        }
        for r in rows
    ]


def event_to_api(conn, row) -> dict:
    participants = _participants_for_event(conn, row["id"])
    related = None
    if row["related_entity_type"] and row["related_entity_id"]:
        related = {
            "type": row["related_entity_type"],
            "id": row["related_entity_id"],
        }
    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "created_by": row["created_by"],
        "title": row["title"],
        "description": row["description"],
        "event_type": row["event_type"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "location": row["location"],
        "visibility": row["visibility"],
        "source": row["source"],
        "external_provider": row["external_provider"],
        "external_event_id": row["external_event_id"],
        "related": related,
        "status": row["status"],
        "operational_status": row["operational_status"] if "operational_status" in row.keys() else "scheduled",
        "participants": participants,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _visibility_clause(user_id: int) -> tuple[str, list]:
    """SQL fragment: user can see workspace, own, or participant events."""
    clause = """(
        visibility = 'workspace'
        OR created_by = ?
        OR id IN (SELECT event_id FROM calendar_participants WHERE user_id = ?)
        OR (visibility = 'team' AND id IN (SELECT event_id FROM calendar_participants WHERE user_id = ?))
    )"""
    return clause, [user_id, user_id, user_id]


def _save_participants(conn, event_id: int, participants: list | None) -> None:
    conn.execute("DELETE FROM calendar_participants WHERE event_id=?", (event_id,))
    if not participants:
        return
    for p in participants:
        conn.execute(
            """INSERT INTO calendar_participants (event_id, user_id, email, name, role)
               VALUES (?, ?, ?, ?, ?)""",
            (
                event_id,
                p.get("user_id"),
                (p.get("email") or "").strip() or None,
                (p.get("name") or "").strip() or "",
                p.get("role") or "attendee",
            ),
        )


def upsert_booking_event(conn, booking: dict, *, emit_events: bool = True) -> int | None:
    """Project a booking row into calendar_events."""
    existing = conn.execute(
        """SELECT id FROM calendar_events
           WHERE workspace_id=? AND related_entity_type='booking' AND related_entity_id=?""",
        (booking["workspace_id"], booking["id"]),
    ).fetchone()

    status = booking.get("status") or "confirmed"
    if status == "cancelled":
        cal_status = "cancelled"
        op_status = "scheduled"
    elif status == "checked_in":
        cal_status = "confirmed"
        op_status = "checked_in"
    elif status in ("completed", "no_show"):
        cal_status = "confirmed"
        op_status = "completed"
    else:
        cal_status = "confirmed"
        op_status = "scheduled"

    title = booking.get("title") or booking.get("customer_name") or "Booking"
    desc_parts = [f"Booking #{booking['id']}"]
    if booking.get("customer_name"):
        desc_parts.append(f"Customer: {booking['customer_name']}")
    if booking.get("customer_email"):
        desc_parts.append(f"Email: {booking['customer_email']}")
    if booking.get("customer_phone"):
        desc_parts.append(f"Phone: {booking['customer_phone']}")
    if booking.get("location"):
        desc_parts.append(f"Location: {booking['location']}")
    if booking.get("notes"):
        desc_parts.append(booking["notes"])
    description = "\n".join(desc_parts)
    location = (booking.get("location") or "").strip()

    if existing:
        conn.execute(
            """UPDATE calendar_events SET
               title=?, description=?, event_type='booking', start_time=?, end_time=?,
               location=?, status=?, operational_status=?, updated_by=?, updated_at=?
               WHERE id=?""",
            (
                title, description,
                booking["starts_at"], booking.get("ends_at") or _default_end(booking["starts_at"]),
                location, cal_status, op_status, booking.get("updated_by"), _now(), existing["id"],
            ),
        )
        event_id = existing["id"]
        if cal_status == "cancelled":
            event_type = "calendar.cancelled"
        else:
            event_type = "calendar.updated"
    else:
        cur = conn.execute(
            """INSERT INTO calendar_events
               (workspace_id, created_by, title, description, event_type, start_time, end_time,
                location, visibility, source, related_entity_type, related_entity_id, status, operational_status,
                updated_by, updated_at)
               VALUES (?, ?, ?, ?, 'booking', ?, ?, ?, 'workspace', 'business_os', 'booking', ?, ?, ?, ?, ?)""",
            (
                booking["workspace_id"], booking.get("created_by"),
                title, description,
                booking["starts_at"], booking.get("ends_at") or _default_end(booking["starts_at"]),
                location,
                booking["id"], cal_status, op_status, booking.get("updated_by"), _now(),
            ),
        )
        event_id = cur.lastrowid
        event_type = "calendar.created"

    if booking.get("created_by"):
        conn.execute(
            """INSERT OR IGNORE INTO calendar_participants (event_id, user_id, role)
               SELECT ?, ?, 'organizer'
               WHERE NOT EXISTS (
                 SELECT 1 FROM calendar_participants WHERE event_id=? AND user_id=?
               )""",
            (event_id, booking["created_by"], event_id, booking["created_by"]),
        )
    assigned = booking.get("assigned_member_id")
    if assigned:
        conn.execute(
            """INSERT OR IGNORE INTO calendar_participants (event_id, user_id, role)
               SELECT ?, ?, 'attendee'
               WHERE NOT EXISTS (
                 SELECT 1 FROM calendar_participants WHERE event_id=? AND user_id=?
               )""",
            (event_id, int(assigned), event_id, int(assigned)),
        )
        conn.execute(
            "UPDATE calendar_participants SET role='organizer' WHERE event_id=? AND user_id=?",
            (event_id, int(assigned)),
        )

    if emit_events:
        from bos.events import emit
        emit(
            conn, event_type, "calendar_event", int(event_id),
            workspace_id=booking["workspace_id"],
            user_id=booking.get("created_by"),
            actor="system",
            title=f"Calendar: {title}",
            href="/app/calendar",
            metadata={"related_entity_type": "booking", "related_entity_id": booking["id"]},
        )
    return int(event_id)


def _update_booking_operational_status(conn, workspace_id: int, booking_id: int, op_status: str) -> None:
    conn.execute(
        """UPDATE calendar_events SET operational_status=?, updated_at=?
           WHERE workspace_id=? AND related_entity_type='booking' AND related_entity_id=?""",
        (op_status, _now(), workspace_id, booking_id),
    )


def upsert_checkin_event(conn, checkin: dict, *, emit_events: bool = True) -> int | None:
    existing = conn.execute(
        """SELECT id FROM calendar_events
           WHERE workspace_id=? AND related_entity_type='check_in' AND related_entity_id=?""",
        (checkin["workspace_id"], checkin["id"]),
    ).fetchone()
    name = checkin.get("customer_name") or "Check-in"
    title = f"Check-in: {name}"
    start = checkin.get("checked_in_at") or _now()
    end = start
    checkin_status = checkin.get("status") or "checked_in"
    if checkin_status == "completed":
        op_status = "completed"
    elif checkin_status in ("checked_in", "in_progress"):
        op_status = "checked_in"
    elif checkin_status == "waiting":
        op_status = "scheduled"
    else:
        op_status = "scheduled"

    if existing:
        conn.execute(
            """UPDATE calendar_events SET title=?, start_time=?, end_time=?, status='confirmed',
               operational_status=?, updated_at=?
               WHERE id=?""",
            (title, start, end, op_status, _now(), existing["id"]),
        )
        event_id = existing["id"]
        event_type = "calendar.updated"
    else:
        cur = conn.execute(
            """INSERT INTO calendar_events
               (workspace_id, created_by, title, event_type, start_time, end_time,
                visibility, source, related_entity_type, related_entity_id, status, operational_status, updated_at)
               VALUES (?, ?, ?, 'check_in', ?, ?, 'workspace', 'business_os', 'check_in', ?, 'confirmed', ?, ?)""",
            (
                checkin["workspace_id"], checkin.get("checked_in_by"),
                title, start, end, checkin["id"], op_status, _now(),
            ),
        )
        event_id = cur.lastrowid
        event_type = "calendar.created"

    booking_id = checkin.get("booking_id")
    if booking_id:
        _update_booking_operational_status(
            conn, int(checkin["workspace_id"]), int(booking_id),
            "completed" if checkin_status == "completed" else "checked_in",
        )

    if emit_events:
        from bos.events import emit
        emit(
            conn, event_type, "calendar_event", int(event_id),
            workspace_id=checkin["workspace_id"],
            user_id=checkin.get("checked_in_by"),
            actor="system",
            title=title,
            href="/app/calendar",
        )
    return int(event_id)


def _domain_event_handler(conn, event) -> None:
    if event.object_type == "booking" and event.event_type in (
        "booking.created", "booking.updated", "booking.cancelled",
        "booking.status_changed", "booking.assigned",
    ):
        booking = conn.execute("SELECT * FROM bookings WHERE id=?", (event.object_id,)).fetchone()
        if booking:
            upsert_booking_event(conn, dict(booking))
    elif event.object_type == "check_in" and event.event_type in (
        "check_in.created", "check_in.updated", "check_in.status_changed", "check_in.completed",
    ):
        checkin = conn.execute("SELECT * FROM check_ins WHERE id=?", (event.object_id,)).fetchone()
        if checkin:
            upsert_checkin_event(conn, dict(checkin))


def register_calendar_platform(app) -> None:
    from app import current_user, db, login_required
    from bos.events import subscribe
    from bos.permissions import has_permission

    subscribe(_domain_event_handler)

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

    def get_event(conn, event_id: int, workspace_id: int, user_id: int):
        vis, vis_params = _visibility_clause(user_id)
        row = conn.execute(
            f"""SELECT * FROM calendar_events
                WHERE id=? AND workspace_id=? AND status NOT IN ('deleted')
                AND {vis}""",
            (event_id, workspace_id, *vis_params),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def _emit(conn, event_type, event_id, title, **kw):
        from bos.events import emit
        emit(conn, event_type, "calendar_event", event_id, workspace_id=ws_id(), user_id=uid(),
             actor="member", title=title, href="/app/calendar", **kw)

    @app.get("/api/calendar/summary")
    @login_required
    def api_calendar_summary():
        ws = ws_id()
        if not ws:
            return jsonify({"today": 0, "upcoming": 0})
        user_id = uid()
        today = _today()
        vis, vis_params = _visibility_clause(user_id)
        with db() as conn:
            _guard(conn, "calendar.read")
            today_count = conn.execute(
                f"""SELECT COUNT(*) AS c FROM calendar_events
                    WHERE workspace_id=? AND date(start_time)=? AND status='confirmed' AND {vis}""",
                (ws, today, *vis_params),
            ).fetchone()["c"]
            upcoming = conn.execute(
                f"""SELECT COUNT(*) AS c FROM calendar_events
                    WHERE workspace_id=? AND start_time >= ? AND status='confirmed' AND {vis}""",
                (ws, _now(), *vis_params),
            ).fetchone()["c"]
        return jsonify({"today": int(today_count), "upcoming": int(upcoming)})

    @app.get("/api/calendar")
    @login_required
    def api_calendar_list():
        ws = ws_id()
        if not ws:
            return jsonify([])
        user_id = uid()
        view = request.args.get("view", "day")
        date = request.args.get("date") or _today()
        status = request.args.get("status", "")
        vis, vis_params = _visibility_clause(user_id)

        if view == "week":
            start, end = _week_range(date)
            time_filter = " AND datetime(replace(start_time, 'T', ' ')) >= datetime(?) AND datetime(replace(start_time, 'T', ' ')) <= datetime(?)"
            time_params = [start, end]
        elif view == "month":
            start, end = _month_range(date)
            time_filter = " AND datetime(replace(start_time, 'T', ' ')) >= datetime(?) AND datetime(replace(start_time, 'T', ' ')) <= datetime(?)"
            time_params = [start, end]
        else:
            time_filter = " AND date(replace(start_time, 'T', ' ')) = ?"
            time_params = [date]

        with db() as conn:
            _guard(conn, "calendar.read")
            query = f"""SELECT * FROM calendar_events
                        WHERE workspace_id=?
                        {time_filter}
                        AND status NOT IN ('deleted', 'archived')
                        AND {vis}"""
            params: list = [ws, *time_params, *vis_params]
            if status:
                query += " AND status=?"
                params.append(status)
            query += " ORDER BY start_time ASC LIMIT 1000"
            rows = conn.execute(query, params).fetchall()
            return jsonify([event_to_api(conn, r) for r in rows])

    @app.get("/api/calendar/<int:event_id>")
    @login_required
    def api_calendar_detail(event_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "calendar.read")
            row = get_event(conn, event_id, int(ws), uid())
            return jsonify(event_to_api(conn, row))

    @app.post("/api/calendar")
    @login_required
    def api_calendar_create():
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        start_time = _normalize_time((data.get("start_time") or "").strip())
        if not title or not start_time:
            return jsonify({"error": "Title and start time required"}), 400
        event_type = data.get("event_type") or "business_event"
        if event_type not in EVENT_TYPES:
            event_type = "business_event"
        visibility = data.get("visibility") or "workspace"
        if visibility not in VISIBILITY_LEVELS:
            visibility = "workspace"

        with db() as conn:
            _guard(conn, "calendar.create")
            cur = conn.execute(
                """INSERT INTO calendar_events
                   (workspace_id, created_by, title, description, event_type, start_time, end_time,
                    location, visibility, source, status, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'business_os', 'confirmed', ?, ?)""",
                (
                    ws, uid(), title,
                    (data.get("description") or "").strip(),
                    event_type, start_time,
                    _normalize_time(data.get("end_time")) if data.get("end_time") else _default_end(start_time),
                    (data.get("location") or "").strip(),
                    visibility, uid(), _now(),
                ),
            )
            eid = cur.lastrowid
            participants = data.get("participants") or []
            if data.get("participant_user_ids"):
                participants = participants + [{"user_id": int(x)} for x in data["participant_user_ids"]]
            if not any(p.get("user_id") == uid() for p in participants):
                participants.append({"user_id": uid(), "role": "organizer"})
            _save_participants(conn, eid, participants)
            _emit(conn, "calendar.created", eid, f"Event created: {title}")
            row = conn.execute("SELECT * FROM calendar_events WHERE id=?", (eid,)).fetchone()
        with db() as conn:
            return jsonify(event_to_api(conn, row)), 201

    @app.patch("/api/calendar/<int:event_id>")
    @login_required
    def api_calendar_update(event_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        user_id = uid()
        with db() as conn:
            _guard(conn, "calendar.update")
            row = get_event(conn, event_id, int(ws), user_id)
            if row["source"] != "business_os" and row["related_entity_type"]:
                return jsonify({"error": "Linked events must be edited from their source module"}), 403
            if row["created_by"] != user_id and not has_permission(conn, user_id, int(ws), "calendar.update"):
                pass  # already guarded by calendar.update permission for managers+

            fields = (
                "title", "description", "event_type", "start_time", "end_time",
                "location", "visibility", "status",
            )
            updates, params = [], []
            for f in fields:
                if f in data:
                    updates.append(f"{f}=?")
                    val = data[f]
                    if f in ("start_time", "end_time") and val:
                        val = _normalize_time(val)
                    params.append(val)
            if updates:
                updates.extend(["updated_by=?", "updated_at=?"])
                params.extend([user_id, _now(), event_id])
                conn.execute(
                    f"UPDATE calendar_events SET {', '.join(updates)} WHERE id=?",
                    params,
                )
            if "participants" in data:
                _save_participants(conn, event_id, data["participants"])
            _emit(conn, "calendar.updated", event_id, "Calendar event updated")
            row = conn.execute("SELECT * FROM calendar_events WHERE id=?", (event_id,)).fetchone()
        with db() as conn:
            return jsonify(event_to_api(conn, row))

    @app.post("/api/calendar/<int:event_id>/cancel")
    @login_required
    def api_calendar_cancel(event_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "calendar.update")
            get_event(conn, event_id, int(ws), uid())
            conn.execute(
                "UPDATE calendar_events SET status='cancelled', updated_by=?, updated_at=? WHERE id=?",
                (uid(), _now(), event_id),
            )
            _emit(conn, "calendar.cancelled", event_id, "Calendar event cancelled")
        return jsonify({"ok": True})

    @app.delete("/api/calendar/<int:event_id>")
    @login_required
    def api_calendar_delete(event_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "calendar.update")
            row = get_event(conn, event_id, int(ws), uid())
            if row["related_entity_type"] in ("booking", "check_in"):
                return jsonify({"error": "Remove the linked booking or check-in instead"}), 403
            conn.execute(
                "UPDATE calendar_events SET status='archived', updated_by=?, updated_at=? WHERE id=?",
                (uid(), _now(), event_id),
            )
            _emit(conn, "calendar.deleted", event_id, "Calendar event archived")
        return jsonify({"ok": True})

    def conflict_to_api(row) -> dict:
        return {
            "id": row["id"],
            "calendar_event_id": row["calendar_event_id"],
            "external_event_id": row["external_event_id"],
            "os_start_time": row["os_start_time"],
            "google_start_time": row["google_start_time"],
            "os_title": row["os_title"],
            "google_title": row["google_title"],
            "os_end_time": row["os_end_time"],
            "google_end_time": row["google_end_time"],
            "status": row["status"],
            "resolution": row["resolution"],
            "created_at": row["created_at"],
            "resolved_at": row["resolved_at"],
        }

    @app.get("/api/calendar/conflicts")
    @login_required
    def api_calendar_conflicts():
        ws = ws_id()
        if not ws:
            return jsonify([])
        with db() as conn:
            _guard(conn, "calendar.read")
            rows = conn.execute(
                """SELECT * FROM calendar_sync_conflicts
                   WHERE workspace_id=? AND user_id=? AND status='open'
                   ORDER BY created_at DESC LIMIT 50""",
                (int(ws), uid()),
            ).fetchall()
            return jsonify([conflict_to_api(r) for r in rows])

    @app.post("/api/calendar/conflicts/<int:conflict_id>/resolve")
    @login_required
    def api_calendar_resolve_conflict(conflict_id):
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        action = (data.get("action") or "").strip()
        if action not in ("keep_os", "keep_google", "duplicate"):
            return jsonify({"error": "action must be keep_os, keep_google, or duplicate"}), 400
        user_id = uid()
        with db() as conn:
            _guard(conn, "calendar.update")
            conflict = conn.execute(
                """SELECT * FROM calendar_sync_conflicts
                   WHERE id=? AND workspace_id=? AND user_id=? AND status='open'""",
                (conflict_id, int(ws), user_id),
            ).fetchone()
            if not conflict:
                abort(404)
            event = conn.execute(
                "SELECT * FROM calendar_events WHERE id=? AND workspace_id=?",
                (conflict["calendar_event_id"], int(ws)),
            ).fetchone()
            if not event:
                abort(404)

            if action == "keep_os":
                from google_calendar_plugin import sync_calendar_event_to_google
                sync_calendar_event_to_google(conn, app, user_id, int(event["id"]), "calendar.updated")
            elif action == "keep_google":
                conn.execute(
                    """UPDATE calendar_events SET title=?, start_time=?, end_time=?,
                       updated_by=?, updated_at=? WHERE id=?""",
                    (
                        conflict["google_title"], conflict["google_start_time"],
                        conflict["google_end_time"], user_id, _now(), event["id"],
                    ),
                )
                conn.execute(
                    "UPDATE external_references SET updated_at=? WHERE object_type='calendar_event' AND business_object_id=? AND user_id=?",
                    (_now(), event["id"], user_id),
                )
            elif action == "duplicate":
                conn.execute(
                    """INSERT INTO calendar_events
                       (workspace_id, created_by, title, description, event_type, start_time, end_time,
                        location, visibility, source, status, operational_status, updated_by, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'business_os', 'confirmed', 'scheduled', ?, ?)""",
                    (
                        event["workspace_id"], user_id,
                        conflict["google_title"], event["description"], event["event_type"],
                        conflict["google_start_time"], conflict["google_end_time"],
                        event["location"], event["visibility"], user_id, _now(),
                    ),
                )

            conn.execute(
                """UPDATE calendar_sync_conflicts SET status='resolved', resolution=?, resolved_at=?
                   WHERE id=?""",
                (action, _now(), conflict_id),
            )
            row = conn.execute(
                "SELECT * FROM calendar_sync_conflicts WHERE id=?", (conflict_id,)
            ).fetchone()
        return jsonify(conflict_to_api(row))

    app.init_calendar_tables = init_calendar_tables
