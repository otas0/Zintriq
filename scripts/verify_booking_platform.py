#!/usr/bin/env python3
"""Booking Platform Foundation — spec verification."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS, FAIL, WARN = [], [], []


def ok(name, detail=""):
    PASS.append((name, detail))


def fail(name, detail):
    FAIL.append((name, detail))


def warn(name, detail):
    WARN.append((name, detail))


def login_client(client, user_id, ws_id=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-bk-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-bk-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE") and body is not None:
        return meth(url, json={**body, "csrf_token": "verify-bk-csrf"}, headers=headers)
    return meth(url, headers=headers)


def column_exists(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from bos.permissions import has_permission
    from booking_platform import init_booking_tables, BOOKING_STATUSES
    from calendar_platform import init_calendar_tables

    ts = int(time.time())
    pwd = generate_password_hash("BkVerify!123", method="pbkdf2:sha256:600000")
    start = (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

    with app.app_context():
        client = app.test_client()
        rules = {r.rule for r in app.url_map.iter_rules()}

        with db() as conn:
            init_booking_tables(conn)
            init_calendar_tables(conn)

            for col in (
                "workspace_id", "contact_id", "service_id", "assigned_member_id",
                "calendar_event_id", "status", "starts_at", "ends_at", "location",
                "notes", "created_by", "created_at", "updated_at",
            ):
                if column_exists(conn, "bookings", col):
                    ok(f"Booking.{col}")
                else:
                    fail(f"Booking.{col}", "missing")

            for st in ("pending", "confirmed", "checked_in", "completed", "cancelled", "no_show"):
                if st in BOOKING_STATUSES:
                    ok(f"Status {st}")
                else:
                    fail(f"Status {st}", "not in BOOKING_STATUSES")

            for perm in ("booking.read", "booking.create", "booking.update", "booking.cancel", "booking.assign"):
                if perm in open(os.path.join(ROOT, "bos/permissions.py")).read():
                    ok(f"Permission {perm}")
                else:
                    fail(f"Permission {perm}", "missing")

            # Users + workspace
            for key, email, role in (("owner", f"bk-own-{ts}@test.local", "owner"), ("viewer", f"bk-view-{ts}@test.local", "viewer")):
                try:
                    uid = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, pwd)).lastrowid
                except sqlite3.IntegrityError:
                    uid = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
                if key == "owner":
                    owner_id = uid
                else:
                    viewer_id = uid

            conn.execute("INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                         (f"BK Org {ts}", f"bk-org-{ts}", owner_id))
            org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (f"bk-org-{ts}",)).fetchone()["id"]
            conn.execute("INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                         (org_id, f"BK WS {ts}", f"bk-ws-{ts}"))
            ws_a = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"bk-ws-{ts}",)).fetchone()["id"]
            conn.execute("INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                         (org_id, f"BK WS B {ts}", f"bk-wsb-{ts}"))
            ws_b = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"bk-wsb-{ts}",)).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute("INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", (ws_a, owner_id))
            conn.execute("INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'viewer', 'active')", (ws_a, viewer_id))

            cust = conn.execute(
                """INSERT INTO customer_profiles (owner_id, customer_code, full_name, email, phone, status)
                   VALUES (?, ?, 'Jane Customer', 'jane@test.local', '555-0100', 'active')""",
                (owner_id, f"BK-{ts}"),
            )
            contact_id = cust.lastrowid

        # Create booking
        r = api(client, "POST", "/api/bookings", {
            "contact_id": contact_id,
            "title": "Consultation",
            "starts_at": start,
            "location": "Room A",
            "assigned_member_id": owner_id,
            "notes": "First visit",
        }, owner_id, ws_a)
        if r.status_code == 201:
            booking = r.get_json()
            bid = booking["id"]
            ok("Create booking via API")
        else:
            fail("Create booking via API", r.get_data(as_text=True)[:200])
            bid = None

        if bid:
            with db() as conn:
                cal = conn.execute(
                    "SELECT id FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?",
                    (bid,),
                ).fetchone()
                bk = conn.execute("SELECT calendar_event_id FROM bookings WHERE id=?", (bid,)).fetchone()
                if cal and bk and bk["calendar_event_id"]:
                    ok("Calendar event created and linked")
                else:
                    fail("Calendar integration", f"cal={cal} calendar_event_id={bk['calendar_event_id'] if bk else None}")

            r2 = api(client, "PATCH", f"/api/bookings/{bid}", {
                "starts_at": (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "location": "Room B",
            }, owner_id, ws_a)
            if r2.status_code == 200:
                ok("Reschedule booking")
            else:
                fail("Reschedule booking", str(r2.status_code))

            r3 = api(client, "POST", f"/api/bookings/{bid}/assign", {"assigned_member_id": owner_id}, owner_id, ws_a)
            if r3.status_code == 200:
                ok("Assign staff endpoint")
            else:
                fail("Assign staff", str(r3.status_code))

            r4 = api(client, "POST", f"/api/bookings/{bid}/cancel", {}, owner_id, ws_a)
            if r4.status_code == 200:
                with db() as conn:
                    row = conn.execute("SELECT status FROM bookings WHERE id=?", (bid,)).fetchone()
                    cal = conn.execute("SELECT status FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?", (bid,)).fetchone()
                if row["status"] == "cancelled" and cal and cal["status"] == "cancelled":
                    ok("Cancellation updates booking + calendar")
                else:
                    fail("Cancellation sync", f"booking={row['status']} cal={cal['status'] if cal else None}")
            else:
                fail("Cancel booking", str(r4.status_code))

            act = api(client, "GET", f"/api/bookings/{bid}/activity", user_id=owner_id, ws_id=ws_a)
            if act.status_code == 200 and len(act.get_json()) >= 2:
                ok("Activity history recorded")
            else:
                fail("Activity history", str(act.status_code))

        # Permissions
        with db() as conn:
            if has_permission(conn, owner_id, ws_a, "booking.create") and has_permission(conn, owner_id, ws_a, "booking.cancel"):
                ok("Owner booking permissions")
            else:
                fail("Owner permissions")
            if has_permission(conn, viewer_id, ws_a, "booking.read") and not has_permission(conn, viewer_id, ws_a, "booking.create"):
                ok("Viewer read-only")
            else:
                fail("Viewer permissions")
            if not has_permission(conn, viewer_id, ws_a, "booking.cancel"):
                ok("Viewer cannot cancel")
            else:
                fail("Viewer cancel blocked")

        # Workspace isolation
        with db() as conn:
            conn.execute(
                """INSERT INTO bookings (workspace_id, title, customer_name, starts_at, status, created_by)
                   VALUES (?, 'Secret', 'Bob', ?, 'confirmed', ?)""",
                (ws_b, start, owner_id),
            )
        r_iso = api(client, "GET", "/api/bookings?view=all", user_id=owner_id, ws_id=ws_a)
        titles = [b["title"] for b in r_iso.get_json()]
        if "Secret" not in titles:
            ok("Workspace isolation")
        else:
            fail("Workspace isolation", "WS B booking visible in WS A")

        # UI + routes
        if "/app/booking" in rules:
            ok("Route /app/booking")
        else:
            fail("Route /app/booking")
        bk_js = open(os.path.join(ROOT, "static/bos/features/booking-page.js")).read()
        for token in ("assigned_member_id", "bk-search", "activity", "contact_id"):
            if token in bk_js:
                ok(f"UI includes {token}")
            else:
                fail(f"UI {token}", "missing")

        if "/api/bookings/<int:booking_id>/assign" in rules or any("assign" in r for r in rules if "bookings" in r):
            ok("Assign API route")
        else:
            fail("Assign route")

        with db() as conn:
            mock = conn.execute("SELECT COUNT(*) AS c FROM bookings WHERE title LIKE '%MOCK%' OR customer_name LIKE '%FAKE%'").fetchone()["c"]
            if mock == 0:
                ok("No mock booking titles")
            else:
                warn("Mock data", f"{mock} rows")

    print("\n" + "=" * 60)
    print("Booking Platform Foundation Verification")
    print("=" * 60)
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in WARN:
        print(f"  WARN  {name} — {detail}")
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print("-" * 60)
    print(f"PASS: {len(PASS)}  WARN: {len(WARN)}  FAIL: {len(FAIL)}")
    print("=" * 60)
    print("RESULT: PASSED" if not FAIL else "RESULT: FAILED")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
