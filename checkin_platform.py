"""Check-in Platform — customer arrival and service start for Zintriq."""

from __future__ import annotations

from datetime import datetime

from flask import abort, jsonify, request, session

CHECKIN_SOURCES = ("booking", "qr", "manual", "event", "walk_in")
CHECKIN_STATUSES = ("waiting", "checked_in", "in_progress", "completed", "cancelled", "no_show")
ACTIVE_STATUSES = ("waiting", "checked_in", "in_progress")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    store_id INTEGER,
    point_id INTEGER,
    booking_id INTEGER,
    contact_id INTEGER,
    method TEXT NOT NULL DEFAULT 'manual',
    customer_name TEXT,
    status TEXT NOT NULL DEFAULT 'checked_in',
    notes TEXT,
    checked_in_at TEXT DEFAULT CURRENT_TIMESTAMP,
    checked_in_by INTEGER
);
CREATE INDEX IF NOT EXISTS idx_check_ins_workspace ON check_ins(workspace_id);
CREATE INDEX IF NOT EXISTS idx_check_ins_date ON check_ins(checked_in_at);
"""


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _column_exists(conn, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _migrate_checkin_schema(conn) -> None:
    migrations = (
        ("qr_code_id", "INTEGER"),
        ("event_id", "INTEGER"),
        ("source", "TEXT"),
        ("check_out_time", "TEXT"),
        ("updated_at", "TEXT"),
    )
    for col, typedef in migrations:
        if not _column_exists(conn, "check_ins", col):
            conn.execute(f"ALTER TABLE check_ins ADD COLUMN {col} {typedef}")
    conn.execute(
        """UPDATE check_ins SET source=method WHERE source IS NULL OR source=''"""
    )
    conn.execute(
        """UPDATE check_ins SET updated_at=checked_in_at WHERE updated_at IS NULL OR updated_at=''"""
    )


def _ensure_checkin_indexes(conn) -> None:
    if _column_exists(conn, "check_ins", "booking_id"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_booking ON check_ins(booking_id)")
    if _column_exists(conn, "check_ins", "contact_id"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_contact ON check_ins(contact_id)")
    if _column_exists(conn, "check_ins", "source"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_check_ins_source ON check_ins(source)")


def init_checkin_tables(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    _migrate_checkin_schema(conn)
    _ensure_checkin_indexes(conn)


def _source(row) -> str:
    if "source" in row.keys() and row["source"]:
        return row["source"]
    return row["method"] or "manual"


def checkin_to_api(conn, row) -> dict:
    assignee = None
    if row["checked_in_by"]:
        u = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id=?", (row["checked_in_by"],)
        ).fetchone()
        if u:
            assignee = {"user_id": u["id"], "name": u["display_name"] or u["email"], "email": u["email"]}

    customer = None
    if row["contact_id"]:
        c = conn.execute(
            "SELECT id, full_name, email, phone, owner_id FROM customer_profiles WHERE id=?",
            (row["contact_id"],),
        ).fetchone()
        if c:
            customer = {
                "id": c["id"],
                "name": c["full_name"] or row["customer_name"],
                "email": c["email"],
                "phone": c["phone"],
            }

    booking = None
    if row["booking_id"]:
        b = conn.execute(
            "SELECT id, title, starts_at, status FROM bookings WHERE id=? AND workspace_id=?",
            (row["booking_id"], row["workspace_id"]),
        ).fetchone()
        if b:
            booking = dict(b)

    return {
        "id": row["id"],
        "workspace_id": row["workspace_id"],
        "customer_id": row["contact_id"],
        "contact_id": row["contact_id"],
        "booking_id": row["booking_id"],
        "qr_code_id": row["qr_code_id"] if "qr_code_id" in row.keys() else (row["point_id"] if "point_id" in row.keys() else None),
        "point_id": row["point_id"],
        "event_id": row["event_id"] if "event_id" in row.keys() else None,
        "source": _source(row),
        "method": _source(row),
        "customer_name": customer["name"] if customer else row["customer_name"],
        "customer": customer,
        "booking": booking,
        "status": row["status"],
        "notes": row["notes"],
        "check_in_time": row["checked_in_at"],
        "checked_in_at": row["checked_in_at"],
        "check_out_time": row["check_out_time"] if "check_out_time" in row.keys() else None,
        "checked_in_by": row["checked_in_by"],
        "staff": assignee,
        "store_id": row["store_id"],
        "created_at": row["checked_in_at"],
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else row["checked_in_at"],
    }


def _contact_snapshot(conn, contact_id: int, owner_id: int) -> dict | None:
    row = conn.execute(
        """SELECT id, full_name, email, phone FROM customer_profiles
           WHERE id=? AND owner_id=? AND status!='archived'""",
        (contact_id, owner_id),
    ).fetchone()
    if not row:
        return None
    return {"id": row["id"], "name": row["full_name"] or "", "email": row["email"], "phone": row["phone"]}


def _validate_qr_for_workspace(conn, code: str, workspace_id: int) -> dict:
    """Validate check-in point QR belongs to workspace and is active."""
    point = conn.execute(
        """SELECT cp.*, s.workspace_id, s.name AS store_name
           FROM check_in_points cp
           JOIN stores s ON s.id = cp.store_id
           WHERE cp.point_code=? COLLATE NOCASE""",
        (code.strip().lower(),),
    ).fetchone()
    if not point:
        return {"valid": False, "error": "QR code not found"}
    if not point["workspace_id"] or int(point["workspace_id"]) != int(workspace_id):
        return {"valid": False, "error": "QR code belongs to another workspace"}
    active = point["active_status"] if "active_status" in point.keys() else "active"
    if point["status"] == "archived" or active == "inactive":
        return {"valid": False, "error": "QR code is disabled"}
    return {"valid": True, "point": dict(point)}


def _find_active_checkin(conn, workspace_id: int, booking_id: int | None) -> dict | None:
    if not booking_id:
        return None
    row = conn.execute(
        """SELECT * FROM check_ins
           WHERE workspace_id=? AND booking_id=? AND status IN ('waiting','checked_in','in_progress')
           ORDER BY id DESC LIMIT 1""",
        (workspace_id, booking_id),
    ).fetchone()
    return dict(row) if row else None


def _sync_booking_status(conn, workspace_id: int, booking_id: int, status: str, user_id: int) -> None:
    conn.execute(
        "UPDATE bookings SET status=?, updated_by=?, updated_at=? WHERE id=? AND workspace_id=?",
        (status, user_id, _now(), booking_id, workspace_id),
    )
    booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if booking:
        from calendar_platform import upsert_booking_event
        upsert_booking_event(conn, dict(booking))
        from bos.events import emit
        emit(
            conn, "booking.status_changed", "booking", booking_id,
            workspace_id=workspace_id, user_id=user_id, actor="member",
            title=f"Booking status: {status}",
            href=f"/app/booking#booking/{booking_id}",
            metadata={"status": status},
        )


def _sync_checkin_calendar(conn, checkin: dict) -> None:
    from calendar_platform import upsert_checkin_event
    upsert_checkin_event(conn, checkin, emit_events=True)


def register_checkin_platform(app) -> None:
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

    def get_checkin(conn, checkin_id: int, workspace_id: int):
        row = conn.execute(
            "SELECT * FROM check_ins WHERE id=? AND workspace_id=?", (checkin_id, workspace_id),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def _emit(conn, event_type, checkin_id, title, **kw):
        from bos.events import emit
        emit(
            conn, event_type, "check_in", checkin_id,
            workspace_id=ws_id(), user_id=uid(),
            actor="member", title=title, href=f"/app/check-in#checkin/{checkin_id}", **kw,
        )

    def _create_checkin(conn, ws: int, oid: int, data: dict) -> dict:
        source = data.get("source") or data.get("method") or "manual"
        if source not in CHECKIN_SOURCES:
            source = "manual"
        if source == "walk_in" and not data.get("contact_id"):
            pass  # walk-in without contact is allowed with name only

        contact_id = data.get("contact_id") or data.get("customer_id")
        if contact_id:
            snap = _contact_snapshot(conn, int(contact_id), oid)
            if not snap:
                abort(400, description="Invalid customer reference")
            data.setdefault("customer_name", snap["name"])

        booking_id = data.get("booking_id")
        if booking_id:
            existing = _find_active_checkin(conn, int(ws), int(booking_id))
            if existing:
                return {"duplicate": True, "existing": existing}

        status = data.get("status") or "checked_in"
        if status not in CHECKIN_STATUSES:
            status = "checked_in"

        name = (data.get("customer_name") or "").strip() or "Guest"
        cur = conn.execute(
            """INSERT INTO check_ins
               (workspace_id, store_id, point_id, booking_id, contact_id, qr_code_id, event_id,
                method, source, customer_name, status, notes, checked_in_at, checked_in_by, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ws, data.get("store_id"), data.get("point_id"), booking_id, contact_id,
                data.get("qr_code_id") or data.get("point_id"),
                data.get("event_id"),
                source, source, name, status,
                (data.get("notes") or "").strip() or None,
                data.get("checked_in_at") or _now(), oid, _now(),
            ),
        )
        cid = cur.lastrowid
        row = conn.execute("SELECT * FROM check_ins WHERE id=?", (cid,)).fetchone()
        checkin = dict(row)

        if booking_id and status in ACTIVE_STATUSES:
            _sync_booking_status(conn, int(ws), int(booking_id), "checked_in", oid)

        _sync_checkin_calendar(conn, checkin)

        meta = {"source": source, "status": status}
        if contact_id:
            meta["customer_id"] = int(contact_id)
            meta["owner_id"] = oid
        _emit(conn, "check_in.created", cid, f"Check-in: {name}", metadata=meta)

        if booking_id:
            _emit(conn, "check_in.arrived", cid, f"Customer arrived for booking #{booking_id}", metadata=meta)

        return {"duplicate": False, "checkin": checkin}

    @app.get("/api/check-ins/summary")
    @login_required
    def api_checkins_summary():
        ws = ws_id()
        if not ws:
            return jsonify({"today": 0, "live": 0, "recent": []})
        today = _today()
        with db() as conn:
            _guard(conn, "checkin.read")
            today_count = conn.execute(
                "SELECT COUNT(*) AS c FROM check_ins WHERE workspace_id=? AND date(checked_in_at)=?",
                (ws, today),
            ).fetchone()["c"]
            live = conn.execute(
                """SELECT COUNT(*) AS c FROM check_ins
                   WHERE workspace_id=? AND checked_in_at >= datetime('now', '-2 hours')
                   AND status IN ('checked_in','in_progress','waiting')""",
                (ws,),
            ).fetchone()["c"]
            recent = conn.execute(
                "SELECT * FROM check_ins WHERE workspace_id=? ORDER BY checked_in_at DESC LIMIT 10",
                (ws,),
            ).fetchall()
        return jsonify({
            "today": int(today_count),
            "live": int(live),
            "recent": [checkin_to_api(conn, r) for r in recent],
        })

    @app.get("/api/check-ins")
    @login_required
    def api_checkins_list():
        oid = uid()
        ws = ws_id()
        if not ws:
            return jsonify([])
        view = request.args.get("view", "all")
        status = request.args.get("status", "")
        source = request.args.get("source", "")
        date = request.args.get("date", "")
        staff = request.args.get("checked_in_by", "")
        q = request.args.get("q", "").strip()
        with db() as conn:
            _guard(conn, "checkin.read")
            query = "SELECT * FROM check_ins WHERE workspace_id=?"
            params: list = [ws]
            if view == "today":
                query += " AND date(checked_in_at)=?"
                params.append(_today())
            elif view == "live":
                query += " AND checked_in_at >= datetime('now', '-2 hours') AND status IN ('checked_in','in_progress','waiting')"
            if status:
                query += " AND status=?"
                params.append(status)
            if source:
                query += " AND (source=? OR method=?)"
                params.extend([source, source])
            if date:
                query += " AND date(checked_in_at)=?"
                params.append(date)
            if staff:
                query += " AND checked_in_by=?"
                params.append(int(staff))
            if q:
                query += """ AND (
                    CAST(id AS TEXT) LIKE ? OR customer_name LIKE ?
                    OR CAST(booking_id AS TEXT) LIKE ?
                )"""
                like = f"%{q}%"
                params.extend([like, like, like])
            query += " ORDER BY checked_in_at DESC LIMIT 500"
            rows = conn.execute(query, params).fetchall()
        return jsonify([checkin_to_api(conn, r) for r in rows])

    @app.get("/api/check-ins/<int:checkin_id>")
    @login_required
    def api_checkin_detail(checkin_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "checkin.read")
            row = get_checkin(conn, checkin_id, int(ws))
            return jsonify(checkin_to_api(conn, row))

    @app.get("/api/check-ins/<int:checkin_id>/activity")
    @login_required
    def api_checkin_activity(checkin_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "checkin.read")
            get_checkin(conn, checkin_id, int(ws))
            rows = conn.execute(
                """SELECT event_id, event_type, title, detail, user_id, actor, created_at, metadata
                   FROM domain_events
                   WHERE object_type='check_in' AND object_id=?
                   ORDER BY created_at DESC LIMIT 50""",
                (checkin_id,),
            ).fetchall()
            return jsonify([dict(r) for r in rows])

    @app.post("/api/check-ins")
    @login_required
    def api_checkin_create():
        oid = uid()
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "checkin.create")
            result = _create_checkin(conn, int(ws), oid, data)
            if result.get("duplicate"):
                existing = result["existing"]
                return jsonify({
                    "error": "Active check-in already exists for this booking",
                    "existing_check_in": checkin_to_api(conn, existing),
                }), 409
            row = result["checkin"]
        return jsonify(checkin_to_api(conn, row)), 201

    @app.post("/api/check-ins/scan")
    @login_required
    def api_checkins_qr_scan():
        oid = uid()
        ws = ws_id()
        if not ws:
            return jsonify({"error": "Select a workspace first"}), 400
        data = request.get_json(silent=True) or {}
        code = (data.get("code") or "").strip()
        if not code:
            return jsonify({"error": "QR code required"}), 400
        with db() as conn:
            _guard(conn, "checkin.create")
            validation = _validate_qr_for_workspace(conn, code, int(ws))
            if not validation["valid"]:
                return jsonify({"error": validation["error"], "result": "denied"}), 403
            point = validation["point"]
            payload = {
                "source": "qr",
                "method": "qr",
                "point_id": point["id"],
                "qr_code_id": point["id"],
                "store_id": point["store_id"],
                "customer_name": (data.get("customer_name") or point["name"] or "QR arrival").strip(),
                "contact_id": data.get("contact_id"),
                "booking_id": data.get("booking_id"),
                "event_id": data.get("event_id"),
                "notes": data.get("notes"),
            }
            if data.get("booking_id"):
                existing = _find_active_checkin(conn, int(ws), int(data["booking_id"]))
                if existing:
                    return jsonify({
                        "result": "duplicate",
                        "message": "Customer already checked in for this booking",
                        "check_in": checkin_to_api(conn, existing),
                    }), 409
            result = _create_checkin(conn, int(ws), oid, payload)
            row = result["checkin"]
            conn.execute(
                "INSERT INTO check_in_log (point_id, result, location) VALUES (?, ?, ?)",
                (point["id"], "success", point["location"] if "location" in point else None),
            )
            conn.execute(
                "UPDATE check_in_points SET updated_at = ? WHERE id = ?",
                (_now(), point["id"]),
            )
        return jsonify({
            "result": "success",
            "message": "Check-in recorded",
            "check_in": checkin_to_api(conn, row),
            "point": {"name": point["name"], "location": point["location"] if "location" in point else None},
        }), 201

    @app.patch("/api/check-ins/<int:checkin_id>")
    @login_required
    def api_checkin_update(checkin_id):
        oid = uid()
        ws = ws_id()
        if not ws:
            abort(400)
        data = request.get_json(silent=True) or {}
        with db() as conn:
            _guard(conn, "checkin.update")
            before = get_checkin(conn, checkin_id, int(ws))
            updates, params = [], []
            for field in ("status", "notes", "customer_name", "contact_id", "booking_id", "event_id"):
                if field in data:
                    if field == "status" and data[field] not in CHECKIN_STATUSES:
                        continue
                    updates.append(f"{field}=?")
                    params.append(data[field])
            if updates:
                updates.extend(["updated_at=?"])
                params.extend([_now(), checkin_id, ws])
                conn.execute(
                    f"UPDATE check_ins SET {', '.join(updates)} WHERE id=? AND workspace_id=?",
                    params,
                )
            row = conn.execute("SELECT * FROM check_ins WHERE id=?", (checkin_id,)).fetchone()
            checkin = dict(row)
            _sync_checkin_calendar(conn, checkin)
            if "status" in data and data["status"] != before["status"]:
                _emit(conn, "check_in.status_changed", checkin_id,
                      f"Status changed to {data['status']}",
                      metadata={"from": before["status"], "to": data["status"]})
                if data["status"] == "in_progress":
                    _emit(conn, "check_in.started", checkin_id, "Service started")
                if checkin.get("booking_id") and data["status"] == "checked_in":
                    _sync_booking_status(conn, int(ws), int(checkin["booking_id"]), "checked_in", oid)
            row = conn.execute("SELECT * FROM check_ins WHERE id=?", (checkin_id,)).fetchone()
        return jsonify(checkin_to_api(conn, row))

    @app.post("/api/check-ins/<int:checkin_id>/complete")
    @login_required
    def api_checkin_complete(checkin_id):
        oid = uid()
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "checkin.complete")
            before = get_checkin(conn, checkin_id, int(ws))
            conn.execute(
                """UPDATE check_ins SET status='completed', check_out_time=?, updated_at=?
                   WHERE id=? AND workspace_id=?""",
                (_now(), _now(), checkin_id, ws),
            )
            row = conn.execute("SELECT * FROM check_ins WHERE id=?", (checkin_id,)).fetchone()
            checkin = dict(row)
            if checkin.get("booking_id"):
                _sync_booking_status(conn, int(ws), int(checkin["booking_id"]), "completed", oid)
            _sync_checkin_calendar(conn, checkin)
            meta = {}
            if checkin.get("contact_id"):
                meta["customer_id"] = int(checkin["contact_id"])
                meta["owner_id"] = oid
            _emit(conn, "check_in.completed", checkin_id, "Service completed", metadata=meta)
            if before["status"] != "completed":
                _emit(conn, "check_in.status_changed", checkin_id, "Status changed to completed",
                      metadata={"from": before["status"], "to": "completed"})
            from feedback_core_platform import maybe_create_feedback_request
            maybe_create_feedback_request(
                conn,
                workspace_id=int(ws),
                customer_id=int(checkin["contact_id"]) if checkin.get("contact_id") else None,
                booking_id=int(checkin["booking_id"]) if checkin.get("booking_id") else None,
                check_in_id=checkin_id,
            )
            row = conn.execute("SELECT * FROM check_ins WHERE id=?", (checkin_id,)).fetchone()
        return jsonify(checkin_to_api(conn, row))

    @app.delete("/api/check-ins/<int:checkin_id>")
    @login_required
    def api_checkin_delete(checkin_id):
        ws = ws_id()
        if not ws:
            abort(400)
        with db() as conn:
            _guard(conn, "checkin.delete")
            get_checkin(conn, checkin_id, int(ws))
            conn.execute(
                "UPDATE check_ins SET status='cancelled', updated_at=? WHERE id=? AND workspace_id=?",
                (_now(), checkin_id, ws),
            )
            _emit(conn, "check_in.cancelled", checkin_id, "Check-in cancelled")
        return jsonify({"ok": True})

    app.init_checkin_tables = init_checkin_tables
    app.create_bos_checkin = _create_checkin
    app.validate_checkin_qr = _validate_qr_for_workspace
