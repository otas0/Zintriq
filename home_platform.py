"""Home & Interactions — operational center API for Business OS."""

from __future__ import annotations

from datetime import datetime

from flask import abort, jsonify, session


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def register_home_platform(app) -> None:
    from app import current_user, db, login_required

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def _base_counts(conn, ws, today: str) -> dict:
        pending_bookings = conn.execute(
            """SELECT COUNT(*) AS c FROM bookings
               WHERE workspace_id=? AND status IN ('pending', 'confirmed')
                 AND date(starts_at) >= date('now')""",
            (ws,),
        ).fetchone()["c"]
        today_bookings = conn.execute(
            """SELECT COUNT(*) AS c FROM bookings
               WHERE workspace_id=? AND date(starts_at)=? AND status NOT IN ('cancelled')""",
            (ws, today),
        ).fetchone()["c"]
        today_checkins = conn.execute(
            "SELECT COUNT(*) AS c FROM check_ins WHERE workspace_id=? AND date(checked_in_at)=?",
            (ws, today),
        ).fetchone()["c"]
        new_feedback = conn.execute(
            """SELECT COUNT(*) AS c FROM feedback_records fr
               JOIN stores s ON s.id=fr.store_id
               WHERE s.workspace_id=? AND fr.status IN ('new', 'open')""",
            (ws,),
        ).fetchone()["c"]
        active_qr = conn.execute(
            "SELECT COUNT(*) AS c FROM qr_experiences WHERE workspace_id=? AND status='active'",
            (ws,),
        ).fetchone()["c"]
        today_scans = 0
        if _table_exists(conn, "qr_experience_analytics_events"):
            today_scans = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_analytics_events e
                   JOIN qr_experiences x ON x.id=e.experience_id
                   WHERE x.workspace_id=? AND e.event_type='qr_scan' AND date(e.created_at)=?""",
                (ws, today),
            ).fetchone()["c"]
        elif _table_exists(conn, "qr_experience_events"):
            today_scans = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_events e
                   JOIN qr_experiences x ON x.id=e.experience_id
                   WHERE x.workspace_id=? AND e.event_type='scan' AND date(e.created_at)=?""",
                (ws, today),
            ).fetchone()["c"]
        return {
            "today_bookings": int(today_bookings or 0),
            "today_checkins": int(today_checkins or 0),
            "new_feedback": int(new_feedback or 0),
            "pending_bookings": int(pending_bookings or 0),
            "active_qr": int(active_qr or 0),
            "today_scans": int(today_scans or 0),
        }

    def _mvp_totals(conn, ws: int) -> dict:
        total_responses = conn.execute(
            "SELECT COUNT(*) AS c FROM responses WHERE workspace_id=?",
            (ws,),
        ).fetchone()["c"]
        if not total_responses:
            total_responses = conn.execute(
                "SELECT COUNT(*) AS c FROM feedback_records WHERE workspace_id=?",
                (ws,),
            ).fetchone()["c"]
        total_views = 0
        if _table_exists(conn, "qr_experience_events"):
            total_views = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_events e
                   JOIN qr_experiences x ON x.id=e.experience_id
                   WHERE x.workspace_id=? AND e.event_type IN ('scan', 'view')""",
                (ws,),
            ).fetchone()["c"]
        elif _table_exists(conn, "qr_experience_analytics_events"):
            total_views = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_analytics_events e
                   JOIN qr_experiences x ON x.id=e.experience_id
                   WHERE x.workspace_id=? AND e.event_type IN ('qr_scan', 'view')""",
                (ws,),
            ).fetchone()["c"]
        return {
            "total_responses": int(total_responses or 0),
            "total_views": int(total_views or 0),
        }

    def _recent_activity(conn, ws: int, limit: int = 10) -> list[dict]:
        items: list[dict] = []
        rows = conn.execute(
            """SELECT id, type, data, created_at FROM responses
               WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?""",
            (ws, limit),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """SELECT fr.id, fr.comment, fr.rating, fr.created_at, fr.feedback_type
                   FROM feedback_records fr WHERE fr.workspace_id=?
                   ORDER BY fr.created_at DESC LIMIT ?""",
                (ws, limit),
            ).fetchall()
            for r in rows:
                kind = "survey" if "survey" in (r["feedback_type"] or "") else "feedback"
                label = "New survey response" if kind == "survey" else "Customer submitted feedback"
                items.append({
                    "title": label,
                    "detail": (r["comment"] or "")[:80],
                    "created_at": r["created_at"],
                    "href": f"/app/responses#{r['id']}",
                })
            return items
        from bos.responses import _parse_data
        for r in rows:
            data = _parse_data(r["data"])
            kind = r["type"] or "feedback"
            label = "New survey response" if kind == "survey" else "Customer submitted feedback"
            items.append({
                "title": label,
                "detail": (data.get("comment") or "")[:80],
                "created_at": r["created_at"],
                "href": f"/app/responses#{r['id']}",
                "kind": kind,
            })
        for r in conn.execute(
            """SELECT wa.title, wa.event_type, wa.created_at
               FROM workspace_activity wa
               WHERE wa.workspace_id=? ORDER BY wa.created_at DESC LIMIT ?""",
            (ws, limit),
        ).fetchall():
            et = r["event_type"] or ""
            if "qr" in et and "created" in et:
                items.append({
                    "title": "QR Experience created",
                    "detail": r["title"] or "",
                    "created_at": r["created_at"],
                    "kind": "qr",
                })
            elif "publish" in et:
                items.append({
                    "title": "QR Experience published",
                    "detail": r["title"] or "",
                    "created_at": r["created_at"],
                    "kind": "qr",
                })
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return items[:limit]

    def _recent_responses(conn, ws: int, limit: int = 5) -> list[dict]:
        import json
        rows = conn.execute(
            """SELECT r.id, r.type, r.data, r.created_at, x.name AS experience_name
               FROM responses r
               LEFT JOIN qr_experiences x ON x.id = r.experience_id
               WHERE r.workspace_id=?
               ORDER BY r.created_at DESC LIMIT ?""",
            (ws, limit),
        ).fetchall()
        items = []
        for r in rows:
            data = {}
            try:
                data = json.loads(r["data"] or "{}")
            except (TypeError, json.JSONDecodeError):
                pass
            items.append({
                "id": r["id"],
                "type": r["type"],
                "rating": data.get("rating"),
                "content": data.get("comment") or "",
                "comment": data.get("comment") or "",
                "customer_name": data.get("customer_name") or "",
                "experience_name": r["experience_name"] or "",
                "created_at": r["created_at"],
            })
        return items

    def _qr_status(conn, ws, today: str) -> list[dict]:
        rows = conn.execute(
            """SELECT id, name, status, experience_config, updated_at FROM qr_experiences
               WHERE workspace_id=? AND status!='archived' ORDER BY updated_at DESC LIMIT 8""",
            (ws,),
        ).fetchall()
        if not rows:
            return []

        ids = [int(r["id"]) for r in rows]
        placeholders = ",".join("?" * len(ids))

        response_counts: dict[int, int] = {}
        for r in conn.execute(
            f"SELECT experience_id, COUNT(*) AS c FROM responses WHERE experience_id IN ({placeholders}) GROUP BY experience_id",
            ids,
        ).fetchall():
            response_counts[int(r["experience_id"])] = int(r["c"] or 0)

        view_counts: dict[int, int] = {}
        scans_today: dict[int, int] = {}
        has_analytics = _table_exists(conn, "qr_experience_analytics_events")
        has_events = _table_exists(conn, "qr_experience_events")

        if has_analytics:
            for r in conn.execute(
                f"""SELECT experience_id, COUNT(*) AS c FROM qr_experience_analytics_events
                    WHERE experience_id IN ({placeholders}) AND event_type='qr_scan' AND date(created_at)=?
                    GROUP BY experience_id""",
                [*ids, today],
            ).fetchall():
                scans_today[int(r["experience_id"])] = int(r["c"] or 0)
        elif has_events:
            for r in conn.execute(
                f"""SELECT experience_id, COUNT(*) AS c FROM qr_experience_events
                    WHERE experience_id IN ({placeholders}) AND event_type='scan' AND date(created_at)=?
                    GROUP BY experience_id""",
                [*ids, today],
            ).fetchall():
                scans_today[int(r["experience_id"])] = int(r["c"] or 0)

        if has_events:
            for r in conn.execute(
                f"""SELECT experience_id, COUNT(*) AS c FROM qr_experience_events
                    WHERE experience_id IN ({placeholders}) AND event_type IN ('scan', 'view')
                    GROUP BY experience_id""",
                ids,
            ).fetchall():
                view_counts[int(r["experience_id"])] = int(r["c"] or 0)
        elif has_analytics:
            for r in conn.execute(
                f"""SELECT experience_id, COUNT(*) AS c FROM qr_experience_analytics_events
                    WHERE experience_id IN ({placeholders}) AND event_type IN ('qr_scan', 'view')
                    GROUP BY experience_id""",
                ids,
            ).fetchall():
                view_counts[int(r["experience_id"])] = int(r["c"] or 0)

        result = []
        for row in rows:
            eid = int(row["id"])
            st = row["status"]
            status = "disabled" if st == "paused" else st
            today_n = scans_today.get(eid, 0)
            hint = ""
            if status == "draft":
                hint = "Needs publish"
            elif status == "disabled":
                hint = "Disabled"
            elif today_n:
                hint = f"{today_n} scans today"
            elif status == "active":
                hint = "Running"
            result.append({
                "id": eid,
                "name": row["name"],
                "status": status,
                "scans_today": today_n,
                "total_views": view_counts.get(eid, 0),
                "response_count": response_counts.get(eid, 0),
                "status_hint": hint,
                "updated_at": row["updated_at"] if "updated_at" in row.keys() else "",
            })
        return result

    def _recommended_actions(counts: dict, qr_status: list) -> list[dict]:
        actions = []
        if counts["new_feedback"]:
            actions.append({
                "title": f"{counts['new_feedback']} new response{'s' if counts['new_feedback'] != 1 else ''}",
                "detail": "Customers responded through your QR Experiences",
                "href": "/app/responses",
                "cta": "View responses",
                "urgent": True,
            })
        drafts = [e for e in qr_status if e["status"] == "draft"]
        if drafts:
            actions.append({
                "title": f"{len(drafts)} QR Experience{'s' if len(drafts) != 1 else ''} ready to publish",
                "detail": drafts[0]["name"],
                "href": f"/app/qr#experience/{drafts[0]['id']}",
                "cta": "Publish QR",
                "urgent": False,
            })
        if not qr_status:
            actions.append({
                "title": "Create your first QR Experience",
                "detail": "Put a QR on your table and start collecting feedback",
                "href": "/app/qr",
                "cta": "Create QR",
                "urgent": False,
            })
        elif not actions:
            actions.append({
                "title": "Check recent responses",
                "detail": "See what customers said through your QR codes",
                "href": "/app/responses",
                "cta": "Open responses",
                "urgent": False,
            })
        return actions[:4]

    def _needs_attention(conn, ws, qr_status: list, counts: dict) -> list[dict]:
        items = []
        if counts.get("new_feedback"):
            items.append({
                "title": "New customer responses",
                "detail": f"{counts['new_feedback']} waiting for review",
                "href": "/app/responses",
                "urgent": True,
            })
        drafts = [e for e in qr_status if e["status"] == "draft"]
        if drafts:
            items.append({
                "title": "QR Experience draft unfinished",
                "detail": drafts[0]["name"],
                "href": f"/app/qr#experience/{drafts[0]['id']}",
                "urgent": False,
            })
        paused = [e for e in qr_status if e["status"] in ("paused", "disabled")]
        if paused:
            items.append({
                "title": f"{paused[0]['name']} is paused",
                "detail": "Customers cannot scan until reactivated",
                "href": f"/app/qr#experience/{paused[0]['id']}",
                "urgent": False,
            })
        return items[:5]

    @app.get("/api/home/summary")
    @login_required
    def api_home_summary():
        ws = session.get("active_workspace_id")
        today = _today()
        payload = {
            "today_bookings": 0,
            "today_checkins": 0,
            "new_feedback": 0,
            "pending_bookings": 0,
            "today_scans": 0,
            "active_qr": 0,
            "team_members": 0,
            "bookings": [],
            "checkins": [],
            "feedback": [],
            "activity": [],
            "qr_status": [],
            "recommended_actions": [],
            "needs_attention": [],
            "total_views": 0,
            "total_responses": 0,
            "recent_activity": [],
            "recent_responses": [],
            "workspace_name": "",
            "qr_experiences": [],
        }
        if not ws:
            return jsonify(payload)
        with db() as conn:
            ws_row = conn.execute("SELECT name FROM workspaces WHERE id=?", (ws,)).fetchone()
            payload["workspace_name"] = ws_row["name"] if ws_row else ""
            qr_list = _qr_status(conn, ws, today)
            payload["qr_experiences"] = qr_list
            payload["qr_status"] = qr_list
            payload["recent_activity"] = _recent_activity(conn, ws)
            payload["recent_responses"] = _recent_responses(conn, ws)
            payload.update(_mvp_totals(conn, ws))
            payload["active_qr"] = conn.execute(
                "SELECT COUNT(*) AS c FROM qr_experiences WHERE workspace_id=? AND status='active'",
                (ws,),
            ).fetchone()["c"]
            payload["new_feedback"] = conn.execute(
                "SELECT COUNT(*) AS c FROM responses WHERE workspace_id=? AND date(created_at) >= date('now', '-7 days')",
                (ws,),
            ).fetchone()["c"]
        return jsonify(payload)

    @app.get("/api/interactions/summary")
    @login_required
    def api_interactions_summary():
        ws = session.get("active_workspace_id")
        today = _today()
        empty = {
            "counts": {"new_feedback": 0, "pending_bookings": 0, "today_checkins": 0, "active_qr": 0},
            "feedback": [], "bookings": [], "checkins": [],
        }
        if not ws:
            return jsonify(empty)
        with db() as conn:
            counts = _base_counts(conn, ws, today)
            feedback = [
                dict(r) for r in conn.execute(
                    """SELECT fr.id, fr.rating, fr.comment, fr.status, fr.created_at
                       FROM feedback_records fr JOIN stores s ON s.id=fr.store_id
                       WHERE s.workspace_id=? AND fr.status IN ('new','open')
                       ORDER BY fr.created_at DESC LIMIT 12""",
                    (ws,),
                ).fetchall()
            ]
            bookings = [
                dict(r) for r in conn.execute(
                    """SELECT id, title, customer_name, starts_at, status FROM bookings
                       WHERE workspace_id=? AND status NOT IN ('cancelled', 'completed')
                       ORDER BY starts_at ASC LIMIT 12""",
                    (ws,),
                ).fetchall()
            ]
            checkins = [
                dict(r) for r in conn.execute(
                    """SELECT id, customer_name, checked_in_at FROM check_ins
                       WHERE workspace_id=? AND date(checked_in_at)=?
                       ORDER BY checked_in_at DESC LIMIT 12""",
                    (ws, today),
                ).fetchall()
            ]
        return jsonify({
            "counts": counts,
            "feedback": feedback,
            "bookings": bookings,
            "checkins": checkins,
        })


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None
