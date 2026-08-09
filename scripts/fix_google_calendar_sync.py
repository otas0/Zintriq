#!/usr/bin/env python3
"""Fix Google Calendar link for dyl764690@gmail.com and run live sync test."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-dev-secret")
    from app import app, db
    from calendar_platform import upsert_booking_event
    from google_calendar_plugin import sync_pending_calendar_events, _load_access_token, GOOGLE_CALENDAR_LIST, _http_get_json
    from integration_platform import get_user_connection

    with app.app_context():
        with db() as conn:
            user4 = conn.execute("SELECT id, email FROM users WHERE email='dyl764690@gmail.com'").fetchone()
            user8 = conn.execute("SELECT id, email FROM users WHERE email='test@marketqr.com'").fetchone()
            if not user4:
                print("FAIL: dyl764690@gmail.com not found")
                return 1

            uid4 = int(user4["id"])
            ws = conn.execute(
                """SELECT w.id FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id=w.id
                   WHERE wm.user_id=? AND wm.status='active' LIMIT 1""",
                (uid4,),
            ).fetchone()
            if not ws:
                print("FAIL: no workspace for user 4")
                return 1
            ws_id = int(ws["id"])
            print(f"User: {user4['email']} (id={uid4}), workspace={ws_id}")

            # Move Google connection to the correct Business OS account
            plugin = conn.execute(
                "SELECT id FROM integration_plugins WHERE slug='google_calendar'"
            ).fetchone()
            if user8:
                conn8 = conn.execute(
                    "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
                    (int(user8["id"]), plugin["id"]),
                ).fetchone()
                conn4 = conn.execute(
                    "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
                    (uid4, plugin["id"]),
                ).fetchone()
                if conn8 and not conn4:
                    conn.execute(
                        "UPDATE user_integration_connections SET user_id=? WHERE id=?",
                        (uid4, conn8["id"]),
                    )
                    print("OK: moved Google connection from test@marketqr.com to dyl764690@gmail.com")

            connection = get_user_connection(conn, uid4, "google_calendar")
            if not connection:
                print("FAIL: Google not connected for dyl764690@gmail.com — connect in Settings first")
                return 1
            print(f"OK: Google connection status={connection['status']}")

            cal = conn.execute(
                "SELECT * FROM calendar_connections WHERE connection_id=?",
                (connection["id"],),
            ).fetchone()
            if not cal:
                print("FAIL: no Google calendar selected")
                return 1
            print(f"OK: target calendar={cal['calendar_name']}")

            # Verify token + API
            try:
                access = _load_access_token(conn, connection, app)
                data = _http_get_json(GOOGLE_CALENDAR_LIST, access)
                print(f"OK: Google API reachable ({len(data.get('items', []))} calendars)")
            except Exception as exc:
                print(f"FAIL: Google API — {exc}")
                return 1

            # Create a real booking + calendar event in user's workspace
            start = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
            end = start + timedelta(hours=1)
            start_s = start.strftime("%Y-%m-%d %H:%M:%S")
            end_s = end.strftime("%Y-%m-%d %H:%M:%S")

            cur = conn.execute(
                """INSERT INTO bookings
                   (workspace_id, title, customer_name, starts_at, ends_at, status, created_by, updated_by)
                   VALUES (?, 'Google Sync Test', 'Dy', ?, ?, 'confirmed', ?, ?)""",
                (ws_id, start_s, end_s, uid4, uid4),
            )
            booking_id = cur.lastrowid
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            event_id = upsert_booking_event(conn, dict(booking), emit_events=False)
            print(f"OK: created booking #{booking_id} → calendar event #{event_id}")

        # Sync to Google (needs fresh conn after upsert commits - db() context manager commits on exit)
        with db() as conn:
            result = sync_pending_calendar_events(conn, app, uid4)
            print(f"Sync result: {result}")

            ref = conn.execute(
                """SELECT * FROM external_references
                   WHERE object_type='calendar_event' AND business_object_id=? AND user_id=?""",
                (event_id, uid4),
            ).fetchone()
            cal_event = conn.execute(
                "SELECT external_event_id FROM calendar_events WHERE id=?", (event_id,)
            ).fetchone()

            if ref and cal_event and cal_event["external_event_id"]:
                print(f"SUCCESS: linked to Google event {cal_event['external_event_id']}")
                print(f"Check Google Calendar '{cal['calendar_name']}' for 'Google Sync Test' on {start_s[:10]}")
                return 0

            logs = conn.execute(
                """SELECT event_type, status, error_message FROM integration_event_logs
                   WHERE connection_id=? ORDER BY id DESC LIMIT 5""",
                (connection["id"],),
            ).fetchall()
            print("FAIL: no Google link created. Recent logs:")
            for log in logs:
                print(f"  {log['event_type']} | {log['status']} | {log['error_message']}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
