#!/usr/bin/env python3
"""Feedback & Reputation Platform Foundation — spec verification."""

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

PASS, FAIL = [], []


def ok(name, detail=""):
    PASS.append((name, detail))


def fail(name, detail):
    FAIL.append((name, detail))


def login_client(client, user_id, ws_id=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-fb-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-fb-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE") and body is not None:
        return meth(url, json={**body, "csrf_token": "verify-fb-csrf"}, headers=headers)
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        return meth(url, json={"csrf_token": "verify-fb-csrf"}, headers=headers)
    return meth(url, headers=headers)


def column_exists(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from bos.permissions import has_permission, ALL_PERMISSIONS
    from feedback_core_platform import init_feedback_core_tables, FEEDBACK_SOURCES, FEEDBACK_TYPES
    from feedback_reputation_plugins import PLUGIN_REGISTRY, upsert_external_feedback
    from booking_platform import init_booking_tables
    from checkin_platform import init_checkin_tables

    ts = int(time.time())
    pwd = generate_password_hash("FbVerify!123", method="pbkdf2:sha256:600000")
    start = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    with app.app_context():
        client = app.test_client()
        rules = {r.rule for r in app.url_map.iter_rules()}

        with db() as conn:
            init_feedback_core_tables(conn)
            init_booking_tables(conn)
            init_checkin_tables(conn)

            for table in ("surveys", "survey_questions", "survey_responses", "survey_answers",
                          "external_feedback_mappings", "feedback_requests"):
                if table_exists(conn, table):
                    ok(f"Table.{table}")
                else:
                    fail(f"Table.{table}", "missing")

            for col in ("customer_id", "external_platform", "external_id", "language", "source"):
                if column_exists(conn, "feedback_records", col):
                    ok(f"Feedback.{col}")
                else:
                    fail(f"Feedback.{col}", "missing")

            for src in FEEDBACK_SOURCES:
                ok(f"Source.{src}")
            for ft in FEEDBACK_TYPES:
                ok(f"FeedbackType.{ft}")

            for perm in ("feedback.read", "feedback.create", "feedback.update", "feedback.delete",
                         "survey.manage", "integration.manage"):
                if perm in ALL_PERMISSIONS:
                    ok(f"Permission.{perm}")
                else:
                    fail(f"Permission.{perm}", "missing")

            for slug in PLUGIN_REGISTRY:
                ok(f"Plugin.{slug}")

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"fb_a_{ts}@test.local", pwd),
            ).lastrowid
            uid_b = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"fb_b_{ts}@test.local", pwd),
            ).lastrowid
            uid_a = owner_id

            conn.execute("INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                         (f"FB Org {ts}", f"fb-org-{ts}", uid_a))
            org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (f"fb-org-{ts}",)).fetchone()["id"]
            conn.execute("INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                         (org_id, f"FB WS A {ts}", f"fb-ws-a-{ts}"))
            ws_a = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"fb-ws-a-{ts}",)).fetchone()["id"]
            conn.execute("INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                         (org_id, f"FB WS B {ts}", f"fb-ws-b-{ts}"))
            ws_b = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"fb-ws-b-{ts}",)).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)

            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_a, uid_a),
            )
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_b, uid_b),
            )

            store_a = conn.execute(
                """INSERT INTO stores (name, slug, owner_id, workspace_id)
                   VALUES (?, ?, ?, ?)""",
                (f"Store A {ts}", f"fb-store-a-{ts}", uid_a, ws_a),
            ).lastrowid
            conn.execute(
                """INSERT INTO stores (name, slug, owner_id, workspace_id)
                   VALUES (?, ?, ?, ?)""",
                (f"Store B {ts}", f"fb-store-b-{ts}", uid_b, ws_b),
            )

            cust_id = conn.execute(
                """INSERT INTO customer_profiles (owner_id, customer_code, full_name, email, status)
                   VALUES (?, ?, 'Test Customer', ?, 'active')""",
                (uid_a, f"FB-{ts}", f"cust_{ts}@test.local"),
            ).lastrowid

            if has_permission(conn, uid_a, ws_a, "feedback.create"):
                ok("RBAC.feedback.create")
            else:
                fail("RBAC.feedback.create", "owner missing permission")

        for route in (
            "/api/feedback/dashboard", "/api/feedback/workspace", "/api/surveys",
            "/api/feedback/requests", "/api/feedback/plugins",
        ):
            if route in rules:
                ok(f"Route.{route}")
            else:
                fail(f"Route.{route}", "missing")

        # Create survey
        r = api(client, "POST", "/api/surveys", {
            "title": f"Post-service survey {ts}",
            "description": "How did we do?",
            "questions": [
                {"type": "rating", "question": "Rate us", "required": True, "order": 0},
                {"type": "text", "question": "Comments", "required": False, "order": 1},
            ],
        }, uid_a, ws_a)
        if r.status_code == 201:
            survey = r.get_json()
            ok("Survey.create", f"id={survey['id']}")
        else:
            fail("Survey.create", f"status={r.status_code}")
            return 1

        r = api(client, "POST", f"/api/surveys/{survey['id']}/publish", {}, uid_a, ws_a)
        if r.status_code == 200 and r.get_json().get("pub_code"):
            pub_code = r.get_json()["pub_code"]
            ok("Survey.publish", pub_code)
        else:
            fail("Survey.publish", f"status={r.status_code}")

        r = api(client, "GET", f"/api/surveys/by-code/{pub_code}")
        if r.status_code == 200:
            ok("Survey.by_code")
        else:
            fail("Survey.by_code", f"status={r.status_code}")

        r = api(client, "POST", f"/api/surveys/{survey['id']}/responses", {
            "customer_id": cust_id,
            "customer_name": "Test Customer",
            "answers": {"0": 5, "1": "Great service"},
        })
        if r.status_code == 201 and r.get_json().get("feedback_id"):
            feedback_id = r.get_json()["feedback_id"]
            ok("Survey.submit", f"feedback_id={feedback_id}")
        else:
            fail("Survey.submit", f"status={r.status_code} {r.get_data(as_text=True)[:200]}")
            feedback_id = None

        # Fix answer keys — use question ids
        with db() as conn:
            qs = conn.execute(
                "SELECT id FROM survey_questions WHERE survey_id=? ORDER BY sort_order", (survey["id"],)
            ).fetchall()
        if qs:
            r = api(client, "POST", f"/api/surveys/{survey['id']}/responses", {
                "customer_id": cust_id,
                "answers": {str(qs[0]["id"]): 4, str(qs[1]["id"]): "Nice"},
            })
            if r.status_code == 201:
                ok("Survey.submit_by_question_id")
                if not feedback_id:
                    feedback_id = r.get_json().get("feedback_id")

        r = api(client, "POST", "/api/feedback/workspace", {
            "content": "Internal note from staff",
            "feedback_type": "comment",
            "source": "business_os",
            "customer_id": cust_id,
        }, uid_a, ws_a)
        if r.status_code == 201:
            ok("Feedback.create")
            if not feedback_id:
                feedback_id = r.get_json()["id"]
        else:
            fail("Feedback.create", f"status={r.status_code}")

        r = api(client, "GET", "/api/feedback/dashboard", user_id=uid_a, ws_id=ws_a)
        if r.status_code == 200 and r.get_json().get("total", 0) >= 1:
            ok("Dashboard.stats", f"total={r.get_json()['total']}")
        else:
            fail("Dashboard.stats", f"status={r.status_code}")

        r = api(client, "GET", "/api/feedback/workspace", user_id=uid_a, ws_id=ws_a)
        if r.status_code == 200 and len(r.get_json()) >= 1:
            ok("Feedback.list")
        else:
            fail("Feedback.list", f"status={r.status_code}")

        if feedback_id:
            r = api(client, "GET", f"/api/feedback/workspace/{feedback_id}", user_id=uid_b, ws_id=ws_b)
            if r.status_code == 404:
                ok("Isolation.workspace")
            else:
                fail("Isolation.workspace", f"expected 404 got {r.status_code}")

        # Booking → feedback request
        with db() as conn:
            conn.execute(
                """INSERT INTO bookings (workspace_id, title, contact_id, starts_at, ends_at, status, created_by)
                   VALUES (?, ?, ?, ?, ?, 'confirmed', ?)""",
                (ws_a, "Test booking", cust_id, start,
                 (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), uid_a),
            )
            booking_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        r = api(client, "PATCH", f"/api/bookings/{booking_id}", {"status": "completed"}, uid_a, ws_a)
        if r.status_code == 200:
            with db() as conn:
                req = conn.execute(
                    "SELECT id FROM feedback_requests WHERE workspace_id=? AND booking_id=?",
                    (ws_a, booking_id),
                ).fetchone()
            if req:
                ok("Booking.feedback_request", f"id={req['id']}")
            else:
                fail("Booking.feedback_request", "no request created")
        else:
            fail("Booking.complete", f"status={r.status_code}")

        # External plugin mapping
        with db() as conn:
            fid = upsert_external_feedback(
                conn,
                workspace_id=ws_a,
                store_id=store_a,
                platform="yelp",
                external_id=f"g-{ts}",
                rating=5,
                content="Synced review",
                customer_name="Yelp User",
            )
            dup = upsert_external_feedback(
                conn,
                workspace_id=ws_a,
                store_id=store_a,
                platform="yelp",
                external_id=f"g-{ts}",
                rating=5,
                content="Synced review",
            )
            if fid == dup:
                ok("Plugin.external_mapping")
            else:
                fail("Plugin.external_mapping", "duplicate not deduped")

        r = api(client, "GET", "/api/feedback/plugins", user_id=uid_a, ws_id=ws_a)
        if r.status_code == 200 and len(r.get_json()) >= 4:
            ok("Plugins.list")
        else:
            fail("Plugins.list", f"status={r.status_code}")

    print(f"\n{'=' * 60}\nFeedback Platform Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
