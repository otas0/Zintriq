#!/usr/bin/env python3
"""QR Experience Analytics — verification (real events only)."""

from __future__ import annotations

import os
import sys
import time

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
        sess["csrf_token"] = "verify-analytics-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-analytics-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        payload = {**(body or {}), "csrf_token": "verify-analytics-csrf"}
        return meth(url, json=payload, headers=headers)
    return meth(url, headers=headers)


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from qr_experience_platform import init_qr_experience_tables
    from qr_experience_analytics import flush_analytics_queue, init_analytics_tables
    from bos.permissions import has_permission, init_permissions_tables

    ts = int(time.time())
    pwd = generate_password_hash("AnalyticsVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()

        with db() as conn:
            init_qr_experience_tables(conn)
            init_analytics_tables(conn)
            init_permissions_tables(conn)

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"an_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"AN Org {ts}", f"an-org-{ts}", owner_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"an-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"AN WS {ts}", f"an-ws-{ts}"),
            )
            ws_id = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"an-ws-{ts}",)
            ).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            store_id = conn.execute(
                "INSERT INTO stores (name, slug, owner_id, workspace_id) VALUES (?, ?, ?, ?)",
                (f"AN Store {ts}", f"an-store-{ts}", owner_id, ws_id),
            ).lastrowid
            conn.execute(
                """INSERT INTO check_in_points (store_id, point_code, name, status, active_status)
                   VALUES (?, ?, ?, 'published', 'active')""",
                (store_id, f"anci{ts}", f"Gate {ts}"),
            )

            if has_permission(conn, owner_id, ws_id, "analytics.read"):
                ok("Permission.analytics.read")
            else:
                fail("Permission.analytics.read", "missing")

        r = api(client, "POST", "/api/qr-experiences", {
            "name": f"Analytics QR {ts}",
            "template_id": "check_in_only",
        }, owner_id, ws_id)
        if r.status_code != 201:
            fail("Experience.create", f"status={r.status_code}")
            return 1
        eid = r.get_json()["id"]
        ok("Experience.create", f"id={eid}")

        r = api(client, "POST", f"/api/qr-experiences/{eid}/publish", {}, owner_id, ws_id)
        slug = r.get_json().get("public_slug")
        ok("Experience.publish", slug)

        r = client.get(f"/qr/{r.get_json()['code']}", follow_redirects=True)
        if r.status_code == 200:
            ok("Scan.flow")
        else:
            fail("Scan.flow", f"status={r.status_code}")

        flush_analytics_queue()

        with db() as conn:
            scans = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_analytics_events
                   WHERE experience_id=? AND event_type='qr_scan'""",
                (eid,),
            ).fetchone()["c"]
        if scans >= 1:
            ok("Event.qr_scan", f"count={scans}")
        else:
            fail("Event.qr_scan", "missing")

        with db() as conn:
            sess = conn.execute(
                "SELECT session_id FROM qr_experience_sessions WHERE experience_id=? ORDER BY id DESC LIMIT 1",
                (eid,),
            ).fetchone()
        sid = sess["session_id"]

        r = api(client, "POST", f"/api/runtime/sessions/{sid}/checkin", {
            "customer_name": "Patron",
        }, user_id=owner_id, ws_id=ws_id)
        if r.status_code == 201:
            ok("Action.checkin_complete")
        else:
            fail("Action.checkin_complete", f"status={r.status_code}")

        flush_analytics_queue()

        with db() as conn:
            completed = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_analytics_events
                   WHERE experience_id=? AND event_type='checkin_completed'""",
                (eid,),
            ).fetchone()["c"]
        if completed >= 1:
            ok("Event.checkin_completed", f"count={completed}")
        else:
            fail("Event.checkin_completed", "missing")

        r = api(client, "GET", f"/api/qr-experiences/{eid}/analytics?period=all", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200:
            body = r.get_json()
            if body.get("total_scans", 0) >= 1 and body.get("completed_actions", 0) >= 1:
                ok("Dashboard.detail", f"scans={body['total_scans']} conv={body['conversion_rate']}")
            else:
                fail("Dashboard.detail", str(body))
        else:
            fail("Dashboard.detail", f"status={r.status_code} body={r.get_data(as_text=True)[:120]}")

        r = api(client, "GET", "/api/qr-experiences/analytics/dashboard?period=all", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("overview", {}).get("total_scans", 0) >= 1:
            ok("Dashboard.workspace", f"scans={r.get_json()['overview']['total_scans']}")
        else:
            fail("Dashboard.workspace", f"status={r.status_code}")

        # Workspace isolation
        with db() as conn:
            other = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"an_other_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"Other AN {ts}", f"an-other-{ts}", other),
            )
            oorg = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"an-other-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (oorg, f"Other WS {ts}", f"an-other-ws-{ts}"),
            )
            ows = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"an-other-ws-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ows, other),
            )
        r = api(client, "GET", f"/api/qr-experiences/{eid}/analytics", user_id=other, ws_id=ows)
        if r.status_code == 404:
            ok("Permission.isolation")
        else:
            fail("Permission.isolation", f"status={r.status_code}")

    print(f"\n{'=' * 60}\nQR Experience Analytics Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
