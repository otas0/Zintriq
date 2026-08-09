#!/usr/bin/env python3
"""QR Customer Experience Runtime — verification (real DB, no mock data)."""

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
        sess["csrf_token"] = "verify-runtime-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-runtime-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        payload = {**(body or {}), "csrf_token": "verify-runtime-csrf"}
        return meth(url, json=payload, headers=headers)
    return meth(url, headers=headers)


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from qr_experience_platform import init_qr_experience_tables
    from qr_experience_runtime import init_runtime_tables
    from qr_experience_analytics import flush_analytics_queue

    ts = int(time.time())
    pwd = generate_password_hash("RuntimeVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()

        with db() as conn:
            init_qr_experience_tables(conn)
            init_runtime_tables(conn)

            for table in ("qr_experience_sessions", "qr_experience_interactions"):
                if table_exists(conn, table):
                    ok(f"Table.{table}")
                else:
                    fail(f"Table.{table}", "missing")

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"rt_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"RT Org {ts}", f"rt-org-{ts}", owner_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"rt-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"RT WS {ts}", f"rt-ws-{ts}"),
            )
            ws_id = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"rt-ws-{ts}",)
            ).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            store_id = conn.execute(
                "INSERT INTO stores (name, slug, owner_id, workspace_id) VALUES (?, ?, ?, ?)",
                (f"RT Store {ts}", f"rt-store-{ts}", owner_id, ws_id),
            ).lastrowid
            conn.execute(
                """INSERT INTO check_in_points (store_id, point_code, name, status, active_status)
                   VALUES (?, ?, ?, 'published', 'active')""",
                (store_id, f"rtci{ts}", f"Arrival {ts}"),
            )
            from feedback_core_platform import init_feedback_core_tables
            init_feedback_core_tables(conn)
            conn.execute(
                """INSERT INTO surveys (workspace_id, title, status, pub_code, updated_at)
                   VALUES (?, ?, 'published', ?, datetime('now'))""",
                (ws_id, f"RT Survey {ts}", f"rtsv{ts}"),
            )

        r = api(client, "POST", "/api/qr-experiences", {
            "name": f"Runtime Experience {ts}",
            "template_id": "feedback_only",
        }, owner_id, ws_id)
        if r.status_code != 201:
            fail("Experience.create", f"status={r.status_code}")
            return 1
        exp = r.get_json()
        eid = exp["id"]
        code = exp.get("code")
        ok("Experience.create", f"id={eid}")

        r = api(client, "POST", f"/api/qr-experiences/{eid}/publish", {}, owner_id, ws_id)
        if r.status_code != 200:
            fail("Experience.publish", f"status={r.status_code}")
            return 1
        published = r.get_json()
        slug = published.get("public_slug")
        if slug and (published.get("public_url") or "").startswith(f"/e/{slug}"):
            ok("Runtime.public_url", published["public_url"])
        else:
            fail("Runtime.public_url", str(published.get("public_url")))

        r = client.get(f"/e/{slug}", follow_redirects=False)
        if r.status_code == 200 and b"Runtime Experience" in r.data:
            ok("Runtime.landing", f"/e/{slug}")
        else:
            fail("Runtime.landing", f"status={r.status_code}")

        with db() as conn:
            sessions = conn.execute(
                "SELECT COUNT(*) AS c FROM qr_experience_sessions WHERE experience_id=?", (eid,)
            ).fetchone()["c"]
            views = conn.execute(
                """SELECT COUNT(*) AS c FROM qr_experience_interactions
                   WHERE experience_id=? AND event_type='view'""",
                (eid,),
            ).fetchone()["c"]
        if sessions >= 1 and views >= 1:
            ok("Runtime.session_view", f"sessions={sessions} views={views}")
        else:
            fail("Runtime.session_view", f"sessions={sessions} views={views}")

        r = client.get(f"/qr/{code}", follow_redirects=False)
        if r.status_code in (302, 303) and f"/e/{slug}" in (r.headers.get("Location") or ""):
            ok("QR.redirect_to_e", r.headers.get("Location"))
        else:
            fail("QR.redirect_to_e", f"status={r.status_code} loc={r.headers.get('Location')}")

        with db() as conn:
            sess_row = conn.execute(
                "SELECT session_id FROM qr_experience_sessions WHERE experience_id=? ORDER BY id DESC LIMIT 1",
                (eid,),
            ).fetchone()
        sid = sess_row["session_id"]

        r = api(client, "POST", f"/api/runtime/sessions/{sid}/booking", {
            "customer_name": "Alex Customer",
            "starts_at": "2026-08-15 14:00:00",
            "customer_email": f"alex{ts}@test.local",
        })
        if r.status_code == 201 and r.get_json().get("booking_id"):
            ok("Runtime.booking", f"id={r.get_json()['booking_id']}")
        else:
            fail("Runtime.booking", f"status={r.status_code}")

        flush_analytics_queue()

        with db() as conn:
            bookings = conn.execute(
                "SELECT COUNT(*) AS c FROM bookings WHERE workspace_id=?", (ws_id,)
            ).fetchone()["c"]
        if bookings >= 1:
            ok("Runtime.booking_record", f"count={bookings}")
        else:
            fail("Runtime.booking_record", "no booking row")

        login_client(client, owner_id, ws_id)
        r = api(client, "POST", f"/api/runtime/sessions/{sid}/checkin", {
            "customer_name": "Jordan Guest",
        })
        if r.status_code == 201 and r.get_json().get("check_in_id"):
            ok("Runtime.checkin", f"id={r.get_json()['check_in_id']}")
        else:
            fail("Runtime.checkin", f"status={r.status_code}")

        with db() as conn:
            checkins = conn.execute(
                "SELECT COUNT(*) AS c FROM check_ins WHERE workspace_id=?", (ws_id,)
            ).fetchone()["c"]
        if checkins >= 1:
            ok("Runtime.checkin_record", f"count={checkins}")
        else:
            fail("Runtime.checkin_record", "no check_in row")

        login_client(client, owner_id, ws_id)
        r = client.get(f"/e/{slug}/preview")
        if r.status_code == 200:
            ok("Runtime.preview")
        else:
            fail("Runtime.preview", f"status={r.status_code}")

        r = client.get(f"/e/draft-nonexistent-{ts}")
        if r.status_code == 404:
            ok("Runtime.draft_blocked")
        else:
            fail("Runtime.draft_blocked", f"status={r.status_code}")

        r = api(client, "PUT", f"/api/qr-experiences/{eid}/blocks", {
            "blocks": [
                {"type": "header", "content": {"title": "Rendered Block Test"}},
                {"type": "booking", "content": {"title": "Book"}},
            ],
        }, owner_id, ws_id)
        if r.status_code == 200:
            ok("Runtime.blocks_update")
        else:
            fail("Runtime.blocks_update", f"status={r.status_code}")

        r = client.get(f"/e/{slug}")
        if r.status_code == 200 and b"Rendered Block Test" in r.data:
            ok("Runtime.block_render")
        else:
            fail("Runtime.block_render", f"status={r.status_code}")

        flush_analytics_queue()

    print(f"\n{'=' * 60}\nQR Experience Runtime Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
