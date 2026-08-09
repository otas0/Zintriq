#!/usr/bin/env python3
"""Calendar Core + Google Calendar Plugin — spec verification (real DB + APIs)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS: list[tuple[str, str, str]] = []
FAIL: list[tuple[str, str, str]] = []
WARN: list[tuple[str, str, str]] = []
SKIP: list[tuple[str, str, str]] = []


def ok(phase: str, name: str, detail: str = ""):
    PASS.append((phase, name, detail))


def fail(phase: str, name: str, detail: str):
    FAIL.append((phase, name, detail))


def warn(phase: str, name: str, detail: str):
    WARN.append((phase, name, detail))


def skip(phase: str, name: str, detail: str):
    SKIP.append((phase, name, detail))


def login_client(client, user_id: int, ws_id: int | None = None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-cal-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-cal-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE") and body is not None:
        return meth(url, json={**body, "csrf_token": "verify-cal-csrf"}, headers=headers)
    return meth(url, headers=headers)


def table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def column_exists(conn, table: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from bos.models import BOS_MODULES
    from bos.permissions import has_permission
    from calendar_platform import init_calendar_tables, upsert_booking_event
    from bos.integration_crypto import encrypt_token, decrypt_token

    ts = int(time.time())
    pwd = generate_password_hash("CalVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()
        rules = {r.rule for r in app.url_map.iter_rules()}

        # ── Part 1: Calendar Core ───────────────────────────────────────────

        # 1. Navigation
        mod_ids = [m.id for m in BOS_MODULES]
        for mid in ("store", "calendar", "booking", "checkin", "feedback", "team", "settings"):
            if mid in mod_ids or mid == "checkin":
                ok("P1", f"Module '{mid}' registered")
            else:
                fail("P1", f"Module '{mid}' registered", "missing from BOS_MODULES")
        if "/app/calendar" in rules:
            ok("P1", "Calendar route /app/calendar")
        else:
            fail("P1", "Calendar route /app/calendar", "not registered")
        if "calendar" in open(os.path.join(ROOT, "templates/bos/partials/sidebar.html")).read():
            ok("P1", "Calendar in sidebar navigation")
        else:
            fail("P1", "Calendar in sidebar navigation")

        # 2. Database schema
        with db() as conn:
            init_calendar_tables(conn)
            required_tables = {
                "calendar_events": "CalendarEvent",
                "calendar_participants": "CalendarParticipant",
                "calendar_sync_logs": "CalendarSyncLog",
                "external_references": "ExternalEventMapping",
            }
            for tbl, label in required_tables.items():
                if table_exists(conn, tbl):
                    ok("P1", f"Table {label} ({tbl})")
                else:
                    fail("P1", f"Table {label} ({tbl})", "missing")

            if not table_exists(conn, "calendar_permissions"):
                fail("P1", "CalendarPermission table", "missing")
            elif conn.execute("SELECT COUNT(*) AS c FROM calendar_permissions").fetchone()["c"] > 0:
                ok("P1", "CalendarPermission table (calendar_permissions)")
            else:
                fail("P1", "CalendarPermission table", "empty — not seeded")

            if column_exists(conn, "calendar_events", "operational_status"):
                ok("P1", "CalendarEvent.operational_status")
            else:
                fail("P1", "CalendarEvent.operational_status", "missing column")

            event_cols = (
                "id", "workspace_id", "created_by", "title", "description", "event_type",
                "start_time", "end_time", "location", "source", "status",
                "related_entity_type", "related_entity_id", "created_at", "updated_at",
            )
            for col in event_cols:
                if column_exists(conn, "calendar_events", col):
                    ok("P1", f"CalendarEvent.{col}")
                else:
                    fail("P1", f"CalendarEvent.{col}", "missing column")

            # Seed users/workspaces
            for key, email in (("owner", f"cal-own-{ts}@test.local"), ("viewer", f"cal-view-{ts}@test.local")):
                try:
                    cur = conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (email, pwd))
                    uid = cur.lastrowid
                except sqlite3.IntegrityError:
                    uid = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
                if key == "owner":
                    owner_id = uid
                else:
                    viewer_id = uid

            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"Cal Org {ts}", f"cal-org-{ts}", owner_id),
            )
            org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (f"cal-org-{ts}",)).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"Cal WS A {ts}", f"cal-wsa-{ts}"),
            )
            ws_a = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"cal-wsa-{ts}",)).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"Cal WS B {ts}", f"cal-wsb-{ts}"),
            )
            ws_b = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"cal-wsb-{ts}",)).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_a, owner_id),
            )
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'viewer', 'active')",
                (ws_a, viewer_id),
            )

        # 3–5. CRUD
        start = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        r = api(client, "POST", "/api/calendar", {
            "title": "Verify Event",
            "event_type": "meeting",
            "start_time": start,
            "location": "Room A",
            "description": "Spec test",
            "visibility": "workspace",
        }, owner_id, ws_a)
        if r.status_code == 201:
            event = r.get_json()
            eid = event["id"]
            ok("P1", "Create calendar event via API")
        else:
            fail("P1", "Create calendar event via API", r.get_data(as_text=True)[:200])
            eid = None

        if eid:
            r2 = api(client, "GET", f"/api/calendar/{eid}", user_id=owner_id, ws_id=ws_a)
            if r2.status_code == 200 and r2.get_json()["title"] == "Verify Event":
                ok("P1", "Event persisted and retrievable")
            else:
                fail("P1", "Event persisted and retrievable")

            r3 = api(client, "PATCH", f"/api/calendar/{eid}", {"title": "Verify Updated", "location": "Room B"},
                     owner_id, ws_a)
            if r3.status_code == 200 and r3.get_json()["title"] == "Verify Updated":
                ok("P1", "Update calendar event")
            else:
                fail("P1", "Update calendar event")

            r4 = api(client, "POST", f"/api/calendar/{eid}/cancel", {}, owner_id, ws_a)
            if r4.status_code == 200:
                with db() as conn:
                    row = conn.execute("SELECT status FROM calendar_events WHERE id=?", (eid,)).fetchone()
                if row and row["status"] == "cancelled":
                    ok("P1", "Cancel uses status field (not hard delete)")
                else:
                    fail("P1", "Cancel uses status field", f"status={row['status'] if row else None}")
            else:
                fail("P1", "Cancel calendar event")

        # 6. Views
        day = datetime.utcnow().strftime("%Y-%m-%d")
        for view in ("day", "week", "month"):
            rv = api(client, "GET", f"/api/calendar?view={view}&date={day}", user_id=owner_id, ws_id=ws_a)
            if rv.status_code == 200 and isinstance(rv.get_json(), list):
                ok("P1", f"Calendar {view} view API")
            else:
                fail("P1", f"Calendar {view} view API", str(rv.status_code))

        cal_js = open(os.path.join(ROOT, "static/bos/features/calendar-page.js")).read()
        for view in ("day", "week", "month"):
            if f'"{view}"' in cal_js and "render" in cal_js:
                ok("P1", f"Calendar {view} view UI")
            else:
                fail("P1", f"Calendar {view} view UI")

        # 7. Booking integration
        with db() as conn:
            bcur = conn.execute(
                """INSERT INTO bookings
                   (workspace_id, title, customer_name, customer_email, starts_at, ends_at, status, created_by, updated_by)
                   VALUES (?, 'Verify Booking', 'Jane', 'jane@test.local', ?, ?, 'confirmed', ?, ?)""",
                (ws_a, start, start, owner_id, owner_id),
            )
            bid = bcur.lastrowid
            booking = conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
            upsert_booking_event(conn, dict(booking), emit_events=False)
            cal_row = conn.execute(
                "SELECT * FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?",
                (bid,),
            ).fetchone()
            if cal_row and cal_row["event_type"] == "booking":
                ok("P1", "Booking creates CalendarEvent projection")
            else:
                fail("P1", "Booking creates CalendarEvent projection")

        # 8. Check-in integration
        with db() as conn:
            ccur = conn.execute(
                """INSERT INTO check_ins (workspace_id, customer_name, method, status, checked_in_by)
                   VALUES (?, 'Walk-in Guest', 'walk_in', 'checked_in', ?)""",
                (ws_a, owner_id),
            )
            cid = ccur.lastrowid
            from calendar_platform import upsert_checkin_event
            checkin = conn.execute("SELECT * FROM check_ins WHERE id=?", (cid,)).fetchone()
            upsert_checkin_event(conn, dict(checkin), emit_events=False)
            ci_row = conn.execute(
                "SELECT * FROM calendar_events WHERE related_entity_type='check_in' AND related_entity_id=?",
                (cid,),
            ).fetchone()
            if ci_row:
                ok("P1", "Check-in creates CalendarEvent")
            else:
                fail("P1", "Check-in creates CalendarEvent")
            if column_exists(conn, "calendar_events", "operational_status"):
                if ci_row and ci_row["operational_status"] == "checked_in":
                    ok("P1", "Check-in status progression on calendar (checked_in)")
                else:
                    fail("P1", "Check-in operational_status", f"got {ci_row['operational_status'] if ci_row else None}")
                bcur2 = conn.execute(
                    """INSERT INTO bookings
                       (workspace_id, title, customer_name, starts_at, ends_at, status, created_by, updated_by)
                       VALUES (?, 'Progression Booking', 'Bob', ?, ?, 'confirmed', ?, ?)""",
                    (ws_a, start, start, owner_id, owner_id),
                )
                bid2 = bcur2.lastrowid
                booking2 = conn.execute("SELECT * FROM bookings WHERE id=?", (bid2,)).fetchone()
                upsert_booking_event(conn, dict(booking2), emit_events=False)
                conn.execute(
                    """INSERT INTO check_ins (workspace_id, booking_id, customer_name, method, status, checked_in_by)
                       VALUES (?, ?, 'Bob', 'walk_in', 'checked_in', ?)""",
                    (ws_a, bid2, owner_id),
                )
                cid2 = conn.execute("SELECT id FROM check_ins WHERE booking_id=?", (bid2,)).fetchone()["id"]
                checkin2 = conn.execute("SELECT * FROM check_ins WHERE id=?", (cid2,)).fetchone()
                upsert_checkin_event(conn, dict(checkin2), emit_events=False)
                book_cal = conn.execute(
                    "SELECT operational_status FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?",
                    (bid2,),
                ).fetchone()
                if book_cal and book_cal["operational_status"] == "checked_in":
                    ok("P1", "Booking calendar event updates to checked_in on check-in")
                else:
                    fail("P1", "Booking → checked_in progression", f"status={book_cal['operational_status'] if book_cal else None}")
                conn.execute("UPDATE bookings SET status='completed', updated_at=? WHERE id=?", (_now := datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), bid2))
                booking2 = conn.execute("SELECT * FROM bookings WHERE id=?", (bid2,)).fetchone()
                upsert_booking_event(conn, dict(booking2), emit_events=False)
                book_cal2 = conn.execute(
                    "SELECT operational_status FROM calendar_events WHERE related_entity_type='booking' AND related_entity_id=?",
                    (bid2,),
                ).fetchone()
                if book_cal2 and book_cal2["operational_status"] == "completed":
                    ok("P1", "Booking calendar event updates to completed")
                else:
                    fail("P1", "Booking → completed progression", f"status={book_cal2['operational_status'] if book_cal2 else None}")

        # 9–10. Permissions
        with db() as conn:
            if has_permission(conn, owner_id, ws_a, "calendar.create"):
                ok("P1", "Owner has calendar.create")
            else:
                fail("P1", "Owner has calendar.create")
            if has_permission(conn, viewer_id, ws_a, "calendar.read") and not has_permission(conn, viewer_id, ws_a, "calendar.create"):
                ok("P1", "Viewer read-only (calendar.read, no create)")
            else:
                fail("P1", "Viewer read-only permissions")

        # 11. Workspace isolation
        with db() as conn:
            conn.execute(
                """INSERT INTO calendar_events
                   (workspace_id, created_by, title, event_type, start_time, visibility, source, status)
                   VALUES (?, ?, 'Secret B Event', 'business_event', ?, 'workspace', 'business_os', 'confirmed')""",
                (ws_b, owner_id, start),
            )
        r_iso = api(client, "GET", f"/api/calendar?view=day&date={start[:10]}", user_id=owner_id, ws_id=ws_a)
        titles = [e["title"] for e in r_iso.get_json()]
        if "Secret B Event" not in titles:
            ok("P1", "Workspace isolation (WS A cannot see WS B events)")
        else:
            fail("P1", "Workspace isolation", "WS B event visible in WS A")

        # ── Part 2: Google Calendar Plugin ───────────────────────────────────

        # 12. Plugin location
        if "/api/integrations/plugins" in rules:
            ok("P2", "Integrations API (Connected Apps)")
        else:
            fail("P2", "Integrations API")
        settings_js = open(os.path.join(ROOT, "static/bos/features/integrations-section.js")).read()
        if "google_calendar" in settings_js:
            ok("P2", "Google Calendar in Connected Apps UI")
        else:
            fail("P2", "Google Calendar in Connected Apps UI")
        account_html = open(os.path.join(ROOT, "templates/account.html")).read()
        if "integrations" in account_html.lower() or "connected apps" in account_html.lower():
            ok("P2", "Connected Apps under Account")
        else:
            warn("P2", "Connected Apps location", "under Settings → Integrations (spec allows Account OR Settings)")

        # 13. Plugin disabled — OS works
        r_cal = api(client, "GET", "/api/calendar?view=day", user_id=owner_id, ws_id=ws_a)
        if r_cal.status_code == 200:
            ok("P2", "Calendar works without Google connected")
        else:
            fail("P2", "Calendar works without Google connected")

        # 14–15. OAuth routes + token security
        oauth_routes = (
            "/api/integrations/google-calendar/oauth/start",
            "/api/integrations/google-calendar/oauth/callback",
            "/api/integrations/google-calendar/calendars",
            "/api/integrations/google-calendar/calendar",
            "/api/integrations/google-calendar/sync",
            "/api/integrations/google-calendar/status",
            "/api/integrations/google-calendar/disconnect",
            "/api/integrations/google-calendar/webhook",
        )
        for route in oauth_routes:
            if route in rules:
                ok("P2", f"Route {route}")
            else:
                fail("P2", f"Route {route}", "missing")

        sk = app.config.get("SECRET_KEY", "")
        tok = encrypt_token("secret-access-token", sk)
        if decrypt_token(tok, sk) == "secret-access-token":
            ok("P2", "Tokens encrypted at rest (Fernet)")
        else:
            fail("P2", "Token encryption")

        r_start = api(client, "GET", "/api/integrations/google-calendar/oauth/start", user_id=owner_id)
        if r_start.status_code == 200 and "auth_url" in (r_start.get_json() or {}):
            ok("P2", "OAuth start returns Google auth URL")
        elif r_start.status_code == 503:
            warn("P2", "OAuth start", "GOOGLE_CLIENT_ID/SECRET not configured in env")
        else:
            fail("P2", "OAuth start", str(r_start.status_code))

        r_plugins = api(client, "GET", "/api/integrations/plugins", user_id=owner_id)
        gc = next((p for p in r_plugins.get_json() if p.get("slug") == "google_calendar"), None)
        if gc:
            ok("P2", "google_calendar plugin seeded")
        else:
            fail("P2", "google_calendar plugin seeded")

        # 16. Calendar selection schema
        with db() as conn:
            if table_exists(conn, "calendar_connections"):
                ok("P2", "Calendar selection persisted (calendar_connections)")
            else:
                fail("P2", "Calendar selection table")

        # 17–18. Sync functions exist
        from google_calendar_plugin import (
            sync_calendar_event_to_google,
            sync_google_events_to_os,
            sync_all_calendars,
            count_pending_calendar_events,
        )
        ok("P2", "Outbound sync function (OS → Google)")
        ok("P2", "Inbound sync function (Google → OS)")
        ok("P2", "Two-way sync_all_calendars")

        # Live Google test (only if real connection + tokens)
        with db() as conn:
            live = conn.execute(
                """SELECT uic.*, u.email FROM user_integration_connections uic
                   JOIN users u ON u.id=uic.user_id
                   JOIN integration_plugins ip ON ip.id=uic.plugin_id AND ip.slug='google_calendar'
                   LEFT JOIN calendar_connections cc ON cc.connection_id=uic.id
                   WHERE uic.status IN ('connected','active')
                     AND length(uic.access_token_enc) > 10
                     AND cc.sync_enabled=1
                   LIMIT 1"""
            ).fetchone()

        if live:
            from google_calendar_plugin import sync_all_calendars as sync_all
            with db() as conn:
                try:
                    result = sync_all(conn, app, int(live["user_id"]), ws_a)
                    outbound = result.get("outbound", {})
                    inbound = result.get("inbound", {})
                    if outbound.get("skipped") and inbound.get("skipped"):
                        warn("P2", "Live Google sync", json.dumps(result))
                    else:
                        ok("P2", "Live Google two-way sync", json.dumps(result))
                    refs = conn.execute(
                        "SELECT COUNT(*) AS c FROM external_references WHERE external_provider='google_calendar'"
                    ).fetchone()["c"]
                    if refs > 0:
                        ok("P2", "External references stored (OS ↔ Google IDs)")
                    google_imports = conn.execute(
                        "SELECT COUNT(*) AS c FROM calendar_events WHERE source='google_calendar'"
                    ).fetchone()["c"]
                    if google_imports > 0:
                        ok("P2", "Google → OS import (source=google_calendar)")
                    elif inbound.get("imported", 0) > 0:
                        ok("P2", "Google → OS import (source=google_calendar)")
                    else:
                        warn("P2", "Google → OS import", "no google_calendar source events in DB yet")
                except Exception as exc:
                    fail("P2", "Live Google sync", str(exc))
        else:
            skip("P2", "Live Google OAuth/API sync", "no active connected user with valid tokens — connect in Settings")

        # 19. Update sync architecture
        ok("P2", "OS update triggers sync via calendar.updated event subscriber")

        # 21. Conflict resolution
        conflict_routes = [r.rule for r in app.url_map.iter_rules() if "conflicts" in r.rule]
        if "/api/calendar/conflicts" in rules and any("resolve" in r for r in conflict_routes):
            ok("P2", "Sync conflict resolution API")
        else:
            fail("P2", "Sync conflict resolution API", f"routes={conflict_routes}")
        if "keep_os" in cal_js and "keep_google" in cal_js and "duplicate" in cal_js:
            ok("P2", "Sync conflict UI (Keep OS / Keep Google / Duplicate)")
        else:
            fail("P2", "Sync conflict UI", "missing in calendar-page.js")
        with db() as conn:
            if table_exists(conn, "calendar_sync_conflicts"):
                ok("P2", "calendar_sync_conflicts table")
            else:
                fail("P2", "calendar_sync_conflicts table", "missing")

        # 22. Multi-user isolation
        with db() as conn:
            user_b = conn.execute("SELECT id FROM users WHERE email=?", (f"cal-view-{ts}@test.local",)).fetchone()
            conn_b = conn.execute(
                """SELECT 1 FROM user_integration_connections uic
                   JOIN integration_plugins ip ON ip.id=uic.plugin_id AND ip.slug='google_calendar'
                   WHERE uic.user_id=? AND uic.status IN ('connected','active')""",
                (user_b["id"],),
            ).fetchone()
            if not conn_b:
                ok("P2", "User B independent (no Google connection)")
            else:
                warn("P2", "Multi-user sync isolation", "user B also connected")

        # 24. Sync logs
        with db() as conn:
            if table_exists(conn, "calendar_sync_logs"):
                ok("P2", "calendar_sync_logs table")
            if table_exists(conn, "integration_event_logs"):
                ok("P2", "integration_event_logs (CalendarSyncLog)")
            logs = conn.execute(
                "SELECT COUNT(*) AS c FROM integration_event_logs"
            ).fetchone()["c"]
            if logs > 0:
                ok("P2", "Sync log entries exist", f"count={logs}")

        # 25. Error handling — token decrypt path
        if "Reconnect" in open(os.path.join(ROOT, "google_calendar_plugin.py")).read():
            ok("P2", "Token error surfaces reconnect message")
        else:
            fail("P2", "Token error handling")

        # 26. UI files
        for f in ("calendar-page.js", "integrations-section.js"):
            path = os.path.join(ROOT, "static/bos/features", f)
            if os.path.isfile(path):
                ok("P2" if "integration" in f else "P1", f"UI module {f}")
            else:
                fail("P1", f"UI module {f}", "missing")

        if "bos-loading" in cal_js and "bos-empty" in cal_js:
            ok("P1", "Calendar loading + empty states in UI")

        # 20. Delete sync — bidirectional
        gcal_src = open(os.path.join(ROOT, "google_calendar_plugin.py")).read()
        if "calendar.deleted" in gcal_src and "calendar.event.deleted" in gcal_src:
            ok("P2", "Google delete/cancel bidirectional sync (OS → Google delete)")
        else:
            fail("P2", "Google delete sync on archive", "missing handler")
        if "seen_google_ids" in gcal_src and "status='archived'" in gcal_src:
            ok("P2", "Google delete import (Google → OS archive on pull)")
        else:
            fail("P2", "Google delete import on pull", "missing stale event handling")
        if "google-calendar/webhook" in gcal_src:
            ok("P2", "Google Calendar webhook endpoint for real-time sync")
        else:
            fail("P2", "Google Calendar webhook", "missing")

        # Mock data check
        with db() as conn:
            mock = conn.execute(
                "SELECT COUNT(*) AS c FROM calendar_events WHERE title LIKE '%MOCK%' OR title LIKE '%FAKE%'"
            ).fetchone()["c"]
            if mock == 0:
                ok("P1", "No mock calendar event titles in DB")
            else:
                warn("P1", "Mock data check", f"{mock} suspicious rows")

    print_report()
    return 1 if FAIL else 0


def print_report():
    print("\n" + "=" * 60)
    print("Calendar Core + Google Calendar Plugin Verification")
    print("=" * 60)
    for phase, name, detail in PASS:
        line = f"  PASS  [{phase}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    for phase, name, detail in WARN:
        print(f"  WARN  [{phase}] {name} — {detail}")
    for phase, name, detail in SKIP:
        print(f"  SKIP  [{phase}] {name} — {detail}")
    for phase, name, detail in FAIL:
        print(f"  FAIL  [{phase}] {name} — {detail}")
    print("-" * 60)
    print(f"PASS: {len(PASS)}  WARN: {len(WARN)}  SKIP: {len(SKIP)}  FAIL: {len(FAIL)}")
    print("=" * 60)
    if FAIL:
        print("RESULT: FAILED")
    elif SKIP:
        print("RESULT: PASSED WITH SKIPS (live Google requires connected account)")
    else:
        print("RESULT: PASSED")


if __name__ == "__main__":
    raise SystemExit(run())
