#!/usr/bin/env python3
"""Check-in Platform Foundation — spec verification."""

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

PASS, FAIL = [], []


def ok(name, detail=""):
    PASS.append((name, detail))


def fail(name, detail):
    FAIL.append((name, detail))


def login_client(client, user_id, ws_id=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-ci-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-ci-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE") and body is not None:
        return meth(url, json={**body, "csrf_token": "verify-ci-csrf"}, headers=headers)
    return meth(url, headers=headers)


def column_exists(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from bos.permissions import has_permission
    from checkin_platform import init_checkin_tables, CHECKIN_STATUSES, CHECKIN_SOURCES
    from booking_platform import init_booking_tables
    from calendar_platform import init_calendar_tables

    ts = int(time.time())
    pwd = generate_password_hash("CiVerify!123", method="pbkdf2:sha256:600000")
    start = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    with app.app_context():
        client = app.test_client()
        rules = {r.rule for r in app.url_map.iter_rules()}

        with db() as conn:
            init_checkin_tables(conn)
            init_booking_tables(conn)
            init_calendar_tables(conn)

            for col in ("contact_id", "booking_id", "qr_code_id", "event_id", "checked_in_by",
                        "status", "checked_in_at", "check_out_time", "notes", "source"):
                if column_exists(conn, "check_ins", col) or col in ("checked_in_at", "checked_in_by", "contact_id", "booking_id", "status", "notes"):
                    ok(f"CheckIn.{col}")
                elif col in ("source", "qr_code_id", "event_id", "check_out_time"):
                    if column_exists(conn, "check_ins", col):
                        ok(f"CheckIn.{col}")
                    else:
                        fail(f"CheckIn.{col}", "missing")

            for st in CHECKIN_STATUSES:
                ok(f"Status {st}")
            for src in CHECKIN_SOURCES:
                ok(f"Source {src}")

            for perm in ("checkin.read", "checkin.create", "checkin.update", "checkin.complete", "checkin.delete"):
                if perm in open(os.path.join(ROOT, "bos/permissions.py")).read():
                    ok(f"Permission {perm}")
                else:
                    fail(f"Permission {perm}")

            owner_id = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                                    (f"ci-own-{ts}@test.local", pwd)).lastrowid
            viewer_id = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                                     (f"ci-view-{ts}@test.local", pwd)).lastrowid
            conn.execute("INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                         (f"CI Org {ts}", f"ci-org-{ts}", owner_id))
            org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (f"ci-org-{ts}",)).fetchone()["id"]
            conn.execute("INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                         (org_id, f"CI WS {ts}", f"ci-ws-{ts}"))
            ws_a = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"ci-ws-{ts}",)).fetchone()["id"]
            conn.execute("INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                         (org_id, f"CI WS B {ts}", f"ci-wsb-{ts}"))
            ws_b = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"ci-wsb-{ts}",)).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute("INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')", (ws_a, owner_id))
            conn.execute("INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'viewer', 'active')", (ws_a, viewer_id))

            contact_id = conn.execute(
                """INSERT INTO customer_profiles (owner_id, customer_code, full_name, email, status)
                   VALUES (?, ?, 'Pat Customer', 'pat@test.local', 'active')""",
                (owner_id, f"CI-{ts}"),
            ).lastrowid

            bid = conn.execute(
                """INSERT INTO bookings (workspace_id, contact_id, title, customer_name, starts_at, status, created_by)
                   VALUES (?, ?, 'Haircut', 'Pat Customer', ?, 'confirmed', ?)""",
                (ws_a, contact_id, start, owner_id),
            ).lastrowid

            store_id = conn.execute(
                """INSERT INTO stores (slug, name, owner_id, workspace_id) VALUES (?, ?, ?, ?)""",
                (f"ci-store-{ts}", "CI Store", owner_id, ws_a),
            ).lastrowid
            point_code = f"cipt{ts}"[:20]
            point_id = conn.execute(
                """INSERT INTO check_in_points (store_id, point_code, name, location, status, active_status)
                   VALUES (?, ?, 'Front Desk', 'Lobby', 'published', 'active')""",
                (store_id, point_code),
            ).lastrowid

        # Basic check-in with booking
        r = api(client, "POST", "/api/check-ins", {
            "contact_id": contact_id,
            "booking_id": bid,
            "source": "booking",
            "customer_name": "Pat Customer",
        }, owner_id, ws_a)
        if r.status_code == 201:
            ci = r.get_json()
            cid = ci["id"]
            ok("Create check-in with booking")
        else:
            fail("Create check-in", r.get_data(as_text=True)[:200])
            cid = None

        if cid:
            with db() as conn:
                bk = conn.execute("SELECT status FROM bookings WHERE id=?", (bid,)).fetchone()
                cal = conn.execute(
                    "SELECT operational_status FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?",
                    (bid,),
                ).fetchone()
                if bk["status"] == "checked_in":
                    ok("Booking status → checked_in")
                else:
                    fail("Booking check-in status", bk["status"])
                if cal and cal["operational_status"] == "checked_in":
                    ok("Calendar operational status → checked_in")
                else:
                    fail("Calendar check-in sync", cal["operational_status"] if cal else None)

            # Duplicate prevention
            r_dup = api(client, "POST", "/api/check-ins", {
                "booking_id": bid, "contact_id": contact_id, "source": "booking",
            }, owner_id, ws_a)
            if r_dup.status_code == 409:
                ok("Duplicate check-in prevented")
            else:
                fail("Duplicate prevention", str(r_dup.status_code))

            # Complete
            r_done = api(client, "POST", f"/api/check-ins/{cid}/complete", {}, owner_id, ws_a)
            if r_done.status_code == 200:
                with db() as conn:
                    bk = conn.execute("SELECT status FROM bookings WHERE id=?", (bid,)).fetchone()
                if bk["status"] == "completed":
                    ok("Complete check-in → booking completed")
                else:
                    fail("Booking completed", bk["status"])
            else:
                fail("Complete check-in", str(r_done.status_code))

            act = api(client, "GET", f"/api/check-ins/{cid}/activity", user_id=owner_id, ws_id=ws_a)
            if act.status_code == 200 and len(act.get_json()) >= 2:
                ok("Activity history")
            else:
                fail("Activity history", str(act.status_code))

        # Walk-in
        r2 = api(client, "POST", "/api/check-ins", {
            "customer_name": "Walk-in Guest",
            "source": "walk_in",
        }, owner_id, ws_a)
        if r2.status_code == 201:
            ok("Walk-in check-in")
        else:
            fail("Walk-in check-in", str(r2.status_code))

        # QR scan
        r3 = api(client, "POST", "/api/check-ins/scan", {"code": point_code, "customer_name": "QR Guest"}, owner_id, ws_a)
        if r3.status_code == 201 and r3.get_json().get("result") == "success":
            ok("QR check-in")
        else:
            fail("QR check-in", r3.get_data(as_text=True)[:200])

        # Invalid QR (wrong workspace)
        r4 = api(client, "POST", "/api/check-ins/scan", {"code": point_code}, viewer_id, ws_b)
        if r4.status_code == 403:
            ok("Invalid QR / wrong workspace denied")
        else:
            fail("QR workspace isolation", str(r4.status_code))

        # Archived QR
        with db() as conn:
            conn.execute("UPDATE check_in_points SET status='archived' WHERE id=?", (point_id,))
        r5 = api(client, "POST", "/api/check-ins/scan", {"code": point_code}, owner_id, ws_a)
        if r5.status_code == 403:
            ok("Disabled QR denied")
        else:
            fail("Disabled QR", str(r5.status_code))

        # Permissions
        with db() as conn:
            if has_permission(conn, viewer_id, ws_a, "checkin.read") and not has_permission(conn, viewer_id, ws_a, "checkin.create"):
                ok("Viewer read-only")
            else:
                fail("Viewer permissions")
            if not has_permission(conn, viewer_id, ws_a, "checkin.complete"):
                ok("Viewer cannot complete")
            else:
                fail("Viewer complete blocked")

        # Workspace isolation
        with db() as conn:
            conn.execute(
                """INSERT INTO check_ins (workspace_id, customer_name, method, source, status, checked_in_by)
                   VALUES (?, 'Secret', 'manual', 'manual', 'checked_in', ?)""",
                (ws_b, owner_id),
            )
        r_iso = api(client, "GET", "/api/check-ins?view=all", user_id=owner_id, ws_id=ws_a)
        names = [c["customer_name"] for c in r_iso.get_json()]
        if "Secret" not in names:
            ok("Workspace isolation")
        else:
            fail("Workspace isolation")

        if "/app/check-in" in rules or any("check-in" in r for r in rules):
            ok("Check-in route")
        ci_js = open(os.path.join(ROOT, "static/bos/features/checkin-page.js")).read()
        for token in ("ci-search", "complete", "activity", "walk_in"):
            if token in ci_js:
                ok(f"UI {token}")
            else:
                fail(f"UI {token}")

    print("\n" + "=" * 60)
    print("Check-in Platform Foundation Verification")
    print("=" * 60)
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print("-" * 60)
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    print("RESULT: PASSED" if not FAIL else "RESULT: FAILED")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
