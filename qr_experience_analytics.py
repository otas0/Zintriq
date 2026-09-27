"""QR Experience Analytics — event collection and aggregation (per experience)."""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
from datetime import datetime

from observability.trace import slow_query

_log = logging.getLogger("app.qr_experience")

# Spec-aligned experience event types
ANALYTICS_EVENT_TYPES = (
    "qr_scan",
    "experience_view",
    "survey_started",
    "booking_started",
    "checkin_started",
    "survey_completed",
    "booking_completed",
    "checkin_completed",
    "workflow_started",
    "workflow_step_completed",
    "workflow_completed",
    "workflow_abandoned",
)

ACTION_START_MAP = {
    "start_survey": "survey_started",
    "create_booking": "booking_started",
    "start_checkin": "checkin_started",
}

ACTION_COMPLETE_MAP = {
    "start_survey": "survey_completed",
    "create_booking": "booking_completed",
    "start_checkin": "checkin_completed",
}

COMPLETED_EVENT_TYPES = (
    "survey_completed",
    "booking_completed",
    "checkin_completed",
)

STARTED_EVENT_TYPES = (
    "survey_started",
    "booking_started",
    "checkin_started",
)

ANALYTICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS qr_experience_analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,
    device_type TEXT DEFAULT 'unknown',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(experience_id) REFERENCES qr_experiences(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qrx_analytics_exp ON qr_experience_analytics_events(experience_id, event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_qrx_analytics_sess ON qr_experience_analytics_events(session_id);
"""

_event_queue: queue.Queue | None = None
_worker_started = False


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def detect_device(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "unknown"
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    if "mobile" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    return "desktop"


def period_filter(period: str) -> tuple[str, list]:
    """Return SQL fragment and params for time window."""
    if period == "today":
        return "date(created_at)=date('now')", []
    if period == "7d":
        return "created_at >= datetime('now', '-7 days')", []
    if period == "30d":
        return "created_at >= datetime('now', '-30 days')", []
    return "1=1", []


def init_analytics_tables(conn) -> None:
    conn.executescript(ANALYTICS_SCHEMA_SQL)
    _backfill_from_interactions(conn)


def _backfill_from_interactions(conn) -> None:
    """One-time sync of legacy interaction rows into analytics events."""
    if not _table_exists(conn, "qr_experience_interactions"):
        return
    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM qr_experience_analytics_events"
    ).fetchone()["c"]
    if existing:
        return
    with slow_query("qr_analytics_backfill", threshold_ms=2000):
        rows = conn.execute(
            """SELECT i.*, s.session_id
            FROM qr_experience_interactions i
            JOIN qr_experience_sessions s ON s.id=i.experience_session_id
            ORDER BY i.id"""
        ).fetchall()
        for r in rows:
            etype = _interaction_to_analytics(r["event_type"], r["action_type"])
            if not etype:
                continue
            conn.execute(
                """INSERT INTO qr_experience_analytics_events
                (experience_id, session_id, event_type, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (r["experience_id"], r["session_id"], etype, r["metadata"] or "{}", r["created_at"]),
            )


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _interaction_to_analytics(interaction_type: str, action_type: str | None) -> str | None:
    if interaction_type == "scan":
        return "qr_scan"
    if interaction_type == "view":
        return "experience_view"
    if interaction_type == "click" and action_type:
        return ACTION_START_MAP.get(action_type)
    if interaction_type == "complete" and action_type:
        return ACTION_COMPLETE_MAP.get(action_type)
    return None


def insert_analytics_event(conn, payload: dict) -> int:
    cur = conn.execute(
        """INSERT INTO qr_experience_analytics_events
           (experience_id, session_id, event_type, device_type, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            payload["experience_id"],
            payload.get("session_id"),
            payload["event_type"],
            payload.get("device_type") or "unknown",
            json.dumps(payload.get("metadata") or {}),
            payload.get("created_at") or _now(),
        ),
    )
    return int(cur.lastrowid)


def map_runtime_to_analytics(
    interaction_type: str,
    action_type: str | None = None,
) -> str | None:
    return _interaction_to_analytics(interaction_type, action_type)


def enqueue_analytics_event(app, payload: dict) -> None:
    """Non-blocking enqueue — worker persists asynchronously."""
    global _event_queue
    if _event_queue is None:
        return
    try:
        _event_queue.put_nowait(payload)
    except queue.Full:
        _log.debug("analytics_queue_full", exc_info=True, extra={"op": "enqueue_analytics_event"})
        pass


def start_analytics_worker(app) -> None:
    global _event_queue, _worker_started
    if _worker_started:
        return
    _event_queue = queue.Queue(maxsize=5000)
    _worker_started = True

    def _worker():
        from app import db
        while True:
            item = _event_queue.get()
            if item is None:
                break
            try:
                with app.app_context():
                    with db() as conn:
                        insert_analytics_event(conn, item)
            except Exception:
                logging.getLogger("app.qr_experience").debug("analytics_worker_insert_failed", exc_info=True)
            finally:
                _event_queue.task_done()

    t = threading.Thread(target=_worker, daemon=True, name="qr-analytics-worker")
    t.start()


def _count_events(conn, experience_id: int, event_type: str, period: str) -> int:
    pf, params = period_filter(period)
    row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM qr_experience_analytics_events
            WHERE experience_id=? AND event_type=? AND {pf}""",
        [experience_id, event_type, *params],
    ).fetchone()
    return int(row["c"] or 0)


def _count_events_in(conn, experience_id: int, types: tuple, period: str) -> int:
    if not types:
        return 0
    pf, params = period_filter(period)
    placeholders = ",".join("?" * len(types))
    row = conn.execute(
        f"""SELECT COUNT(*) AS c FROM qr_experience_analytics_events
            WHERE experience_id=? AND event_type IN ({placeholders}) AND {pf}""",
        [experience_id, *types, *params],
    ).fetchone()
    return int(row["c"] or 0)


def _unique_sessions(conn, experience_id: int, period: str) -> int:
    pf, params = period_filter(period)
    row = conn.execute(
        f"""SELECT COUNT(DISTINCT session_id) AS c FROM qr_experience_analytics_events
            WHERE experience_id=? AND session_id IS NOT NULL
            AND event_type IN ('qr_scan','experience_view') AND {pf}""",
        [experience_id, *params],
    ).fetchone()
    return int(row["c"] or 0)


def _device_breakdown(conn, experience_id: int, period: str) -> dict:
    pf, params = period_filter(period)
    rows = conn.execute(
        f"""SELECT device_type, COUNT(*) AS c FROM qr_experience_analytics_events
            WHERE experience_id=? AND {pf}
            GROUP BY device_type""",
        [experience_id, *params],
    ).fetchall()
    out = {"mobile": 0, "desktop": 0, "tablet": 0, "unknown": 0}
    for r in rows:
        key = r["device_type"] if r["device_type"] in out else "unknown"
        out[key] = int(r["c"] or 0)
    return out


def customer_flow(conn, experience_id: int, period: str) -> list[dict]:
    scans = _count_events(conn, experience_id, "qr_scan", period)
    views = _count_events(conn, experience_id, "experience_view", period)
    started = _count_events_in(conn, experience_id, STARTED_EVENT_TYPES, period)
    completed = _count_events_in(conn, experience_id, COMPLETED_EVENT_TYPES, period)
    return [
        {"step": "scan", "label": "QR Scan", "count": scans},
        {"step": "view", "label": "Experience Opened", "count": views},
        {"step": "action_start", "label": "Action Started", "count": started},
        {"step": "complete", "label": "Completed", "count": completed},
    ]


def drop_offs(conn, experience_id: int, period: str) -> list[dict]:
    pairs = (
        ("survey_started", "survey_completed", "Survey"),
        ("booking_started", "booking_completed", "Booking"),
        ("checkin_started", "checkin_completed", "Check-in"),
    )
    result = []
    for start, end, label in pairs:
        s = _count_events(conn, experience_id, start, period)
        e = _count_events(conn, experience_id, end, period)
        if s > 0 or e > 0:
            result.append({
                "action": label,
                "started": s,
                "completed": e,
                "drop_off": max(0, s - e),
            })
    return result


def experience_analytics_summary(conn, experience_id: int, period: str = "30d") -> dict:
    scans = _count_events(conn, experience_id, "qr_scan", period)
    views = _count_events(conn, experience_id, "experience_view", period)
    completed = _count_events_in(conn, experience_id, COMPLETED_EVENT_TYPES, period)
    unique = _unique_sessions(conn, experience_id, period)
    conversion = round((completed / scans) * 100, 1) if scans else 0.0
    return {
        "experience_id": experience_id,
        "period": period,
        "total_scans": scans,
        "unique_visitors": unique,
        "page_views": views,
        "completed_actions": completed,
        "conversion_rate": conversion,
        "flow": customer_flow(conn, experience_id, period),
        "drop_offs": drop_offs(conn, experience_id, period),
        "devices": _device_breakdown(conn, experience_id, period),
        "by_action": {
            "survey_completed": _count_events(conn, experience_id, "survey_completed", period),
            "booking_completed": _count_events(conn, experience_id, "booking_completed", period),
            "checkin_completed": _count_events(conn, experience_id, "checkin_completed", period),
        },
    }


def workspace_analytics_dashboard(conn, workspace_id: int, period: str = "30d") -> dict:
    experiences = conn.execute(
        """SELECT id, name, type, status, public_slug FROM qr_experiences
           WHERE workspace_id=? AND status!='archived' ORDER BY name""",
        (workspace_id,),
    ).fetchall()

    performance = []
    totals = {"scans": 0, "unique": 0, "completed": 0}

    for exp in experiences:
        summary = experience_analytics_summary(conn, exp["id"], period)
        totals["scans"] += summary["total_scans"]
        totals["unique"] += summary["unique_visitors"]
        totals["completed"] += summary["completed_actions"]
        performance.append({
            "id": exp["id"],
            "name": exp["name"],
            "type": exp["type"],
            "status": exp["status"],
            "public_slug": exp["public_slug"] if "public_slug" in exp.keys() else None,
            "scans": summary["total_scans"],
            "unique_visitors": summary["unique_visitors"],
            "completed_actions": summary["completed_actions"],
            "conversion_rate": summary["conversion_rate"],
            "survey_completed": summary["by_action"]["survey_completed"],
            "booking_completed": summary["by_action"]["booking_completed"],
            "checkin_completed": summary["by_action"]["checkin_completed"],
        })

    performance.sort(key=lambda x: x["scans"], reverse=True)
    conv = round((totals["completed"] / totals["scans"]) * 100, 1) if totals["scans"] else 0.0

    from qr_experience_templates import template_usage_stats
    template_usage = template_usage_stats(conn, workspace_id, period)

    return {
        "period": period,
        "overview": {
            "total_scans": totals["scans"],
            "unique_visitors": totals["unique"],
            "completed_actions": totals["completed"],
            "conversion_rate": conv,
            "experience_count": len(performance),
        },
        "performance": performance,
        "template_usage": template_usage,
    }


def flush_analytics_queue(timeout: float = 3.0) -> None:
    """Wait for async analytics worker to drain (tests / verification)."""
    if _event_queue is not None:
        _event_queue.join()


def register_qr_experience_analytics(app) -> None:
    from flask import abort, jsonify, request, session
    from app import db, login_required
    from bos.permissions import has_permission

    def uid():
        from app import current_user
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    def ws_id():
        return session.get("active_workspace_id")

    def _guard(conn, permission: str):
        ws = ws_id()
        if not ws:
            abort(400)
        if has_permission(conn, uid(), int(ws), permission):
            return
        fallback = {
            "analytics.read": "qr_experience.read",
            "analytics.export": "qr_experience.read",
        }.get(permission)
        if fallback and has_permission(conn, uid(), int(ws), fallback):
            return
        abort(403)

    @app.get("/api/qr-experiences/analytics/dashboard")
    @login_required
    def api_qr_analytics_dashboard():
        ws = ws_id()
        if not ws:
            return jsonify({"overview": {}, "performance": []})
        period = request.args.get("period", "30d")
        if period not in ("today", "7d", "30d", "all"):
            period = "30d"
        with db() as conn:
            _guard(conn, "analytics.read")
            return jsonify(workspace_analytics_dashboard(conn, int(ws), period))

    @app.get("/api/qr-experiences/<int:experience_id>/analytics")
    @login_required
    def api_qr_experience_analytics(experience_id):
        ws = ws_id()
        if not ws:
            abort(400)
        period = request.args.get("period", "30d")
        if period not in ("today", "7d", "30d", "all"):
            period = "30d"
        with db() as conn:
            _guard(conn, "analytics.read")
            row = conn.execute(
                "SELECT id, name FROM qr_experiences WHERE id=? AND workspace_id=?",
                (experience_id, ws),
            ).fetchone()
            if not row:
                abort(404)
            summary = experience_analytics_summary(conn, experience_id, period)
            recent = conn.execute(
                """SELECT event_type, session_id, device_type, metadata, created_at
                   FROM qr_experience_analytics_events
                   WHERE experience_id=? ORDER BY created_at DESC LIMIT 40""",
                (experience_id,),
            ).fetchall()
            summary["recent_events"] = [dict(r) for r in recent]
            summary["name"] = row["name"]
            return jsonify(summary)

    app.init_qr_experience_analytics_tables = init_analytics_tables
