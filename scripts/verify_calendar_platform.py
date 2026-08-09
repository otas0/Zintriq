#!/usr/bin/env python3
"""Verify Calendar Core platform against real DB + APIs."""

from __future__ import annotations

import os
import sys
import time

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS = []
FAIL = []


def ok(name: str):
    PASS.append(name)


def fail(name: str, detail: str = ""):
    FAIL.append((name, detail))


def login_client(client, user_id: int, ws_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["active_workspace_id"] = ws_id
        sess["csrf_token"] = "cal-verify-csrf"


def main() -> int:
    os.environ.setdefault("SECRET_KEY", "calendar-verify")
    from app import app, db
    from calendar_platform import init_calendar_tables, upsert_booking_event
    from bos.permissions import has_permission

    ts = int(time.time())
    email = f"cal-verify-{ts}@test.local"
    pwd = generate_password_hash("CalVerify123!", method="pbkdf2:sha256:600000")

    with app.app_context():
        with db() as conn:
            init_calendar_tables(conn)
            cur = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (email, pwd),
            )
            user_id = cur.lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"Cal Org {ts}", f"cal-org-{ts}", user_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE owner_id=? ORDER BY id DESC LIMIT 1", (user_id,)
            ).fetchone()["id"]
            ws_cur = conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"Cal WS {ts}", f"cal-ws-{ts}"),
            )
            ws_id = ws_cur.lastrowid
            conn.execute(
                """INSERT INTO workspace_members (workspace_id, user_id, role, status)
                   VALUES (?, ?, 'owner', 'active')""",
                (ws_id, user_id),
            )
            from team_platform import init_team_tables
            init_team_tables(conn)

            if has_permission(conn, user_id, ws_id, "calendar.read"):
                ok("calendar.read permission for owner")
            else:
                fail("calendar.read permission")

            bcur = conn.execute(
                """INSERT INTO bookings
                   (workspace_id, title, customer_name, starts_at, ends_at, status, created_by, updated_by)
                   VALUES (?, 'Verify Booking', 'Jane Doe', '2030-06-15 10:00:00', '2030-06-15 11:00:00', 'confirmed', ?, ?)""",
                (ws_id, user_id, user_id),
            )
            booking_id = bcur.lastrowid
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            eid = upsert_booking_event(conn, dict(booking), emit_events=False)
            if eid:
                ok("booking projects to calendar_events")
            else:
                fail("booking calendar projection")

            cal_row = conn.execute(
                "SELECT * FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?",
                (booking_id,),
            ).fetchone()
            if cal_row and cal_row["event_type"] == "booking":
                ok("calendar event linked to booking")
            else:
                fail("calendar event link")

        client = app.test_client()
        login_client(client, user_id, ws_id)

        r = client.get("/api/calendar?view=month&date=2030-06-01")
        if r.status_code == 200 and any(e["title"] == "Verify Booking" for e in r.get_json()):
            ok("GET /api/calendar returns booking event")
        else:
            fail("GET /api/calendar", str(r.status_code))

        r2 = client.post(
            "/api/calendar",
            json={
                "title": "Team Standup",
                "event_type": "meeting",
                "start_time": "2030-06-16 09:00:00",
                "visibility": "workspace",
                "csrf_token": "cal-verify-csrf",
            },
            headers={"X-CSRF-Token": "cal-verify-csrf"},
        )
        if r2.status_code == 201:
            ok("POST /api/calendar creates native event")
        else:
            fail("POST /api/calendar", r2.get_data(as_text=True)[:200])

        rules = {rule.rule for rule in app.url_map.iter_rules()}
        if "/api/calendar" in rules and "/app/calendar" in {r.rule for r in app.url_map.iter_rules()}:
            ok("calendar routes registered")
        elif "/api/calendar" in rules:
            ok("calendar API routes registered")

    print("Calendar Core verification")
    print("=" * 40)
    for p in PASS:
        print(f"  OK  {p}")
    for name, detail in FAIL:
        print(f"FAIL  {name}" + (f" — {detail}" if detail else ""))
    print("=" * 40)
    print("PASSED" if not FAIL else "FAILED")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
