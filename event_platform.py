"""Event Platform — API for domain events, notifications, and analytics."""

from __future__ import annotations

import json

from flask import abort, jsonify, request, session

from bos.events import init_event_tables, register_default_subscribers


def register_event_platform(app) -> None:
    from app import current_user, db, login_required

    register_default_subscribers()

    def user_id():
        user = current_user()
        if not user:
            abort(401)
        return user["id"]

    def active_workspace_id(uid: int) -> int:
        ws_id = session.get("active_workspace_id")
        if ws_id:
            with db() as conn:
                row = conn.execute(
                    """SELECT 1 FROM workspace_members
                       WHERE user_id=? AND workspace_id=? AND status='active'""",
                    (uid, ws_id),
                ).fetchone()
                if row:
                    return int(ws_id)
        with db() as conn:
            row = conn.execute(
                """SELECT w.id FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   WHERE wm.user_id=? AND wm.status='active'
                   ORDER BY w.id LIMIT 1""",
                (uid,),
            ).fetchone()
            if row:
                return int(row["id"])
        abort(404)

    def event_row_to_api(row) -> dict:
        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        return {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "object_type": row["object_type"],
            "object_id": row["object_id"],
            "workspace_id": row["workspace_id"],
            "store_id": row["store_id"],
            "user_id": row["user_id"],
            "actor": row["actor"],
            "title": row["title"],
            "detail": row["detail"],
            "metadata": meta,
            "href": row["href"],
            "created_at": row["created_at"],
        }

    @app.get("/api/events")
    @login_required
    def api_events_feed():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        limit = min(request.args.get("limit", 50, type=int), 200)
        object_type = request.args.get("object_type")
        object_id = request.args.get("object_id", type=int)

        with db() as conn:
            if object_type and object_id:
                rows = conn.execute(
                    """SELECT * FROM domain_events
                       WHERE object_type=? AND object_id=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (object_type, object_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM domain_events
                       WHERE workspace_id=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (ws_id, limit),
                ).fetchall()
        return jsonify([event_row_to_api(r) for r in rows])

    @app.get("/api/events/<object_type>/<int:object_id>/timeline")
    @login_required
    def api_object_timeline(object_type, object_id):
        limit = min(request.args.get("limit", 50, type=int), 200)
        with db() as conn:
            rows = conn.execute(
                """SELECT * FROM domain_events
                   WHERE object_type=? AND object_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (object_type, object_id, limit),
            ).fetchall()
        return jsonify([event_row_to_api(r) for r in rows])

    @app.get("/api/notifications")
    @login_required
    def api_notifications():
        uid = user_id()
        limit = min(request.args.get("limit", 50, type=int), 200)
        unread_only = request.args.get("unread") == "1"
        with db() as conn:
            q = """SELECT * FROM event_notifications WHERE user_id=?"""
            params: list = [uid]
            if unread_only:
                q += " AND read=0"
            q += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
        return jsonify([
            {
                "id": r["id"],
                "event_id": r["event_id"],
                "title": r["title"],
                "body": r["body"],
                "priority": r["priority"],
                "object_type": r["object_type"],
                "object_id": r["object_id"],
                "href": r["href"],
                "read": bool(r["read"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ])

    @app.get("/api/notifications/unread-count")
    @login_required
    def api_notifications_unread():
        uid = user_id()
        with db() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM event_notifications WHERE user_id=? AND read=0",
                (uid,),
            ).fetchone()["c"]
        return jsonify({"count": n})

    @app.post("/api/notifications/read-all")
    @login_required
    def api_notifications_read_all():
        uid = user_id()
        with db() as conn:
            conn.execute(
                "UPDATE event_notifications SET read=1 WHERE user_id=? AND read=0",
                (uid,),
            )
        return jsonify({"ok": True})

    @app.post("/api/notifications/<int:notification_id>/read")
    @login_required
    def api_notification_read(notification_id):
        uid = user_id()
        with db() as conn:
            conn.execute(
                "UPDATE event_notifications SET read=1 WHERE id=? AND user_id=?",
                (notification_id, uid),
            )
        return jsonify({"ok": True})

    @app.get("/api/analytics/summary")
    @login_required
    def api_analytics_summary():
        uid = user_id()
        ws_id = request.args.get("workspace_id", type=int) or active_workspace_id(uid)
        with db() as conn:
            rows = conn.execute(
                "SELECT metric_key, metric_value FROM event_analytics WHERE workspace_id=?",
                (ws_id,),
            ).fetchall()
        metrics = {r["metric_key"]: r["metric_value"] for r in rows}
        rating_sum = metrics.pop("feedback_rating_sum", 0)
        rating_count = metrics.pop("feedback_rating_count", 0)
        if rating_count:
            metrics["feedback_avg_rating"] = round(rating_sum / rating_count, 2)
        return jsonify({"workspace_id": ws_id, "metrics": metrics})

    app.init_event_tables = init_event_tables
