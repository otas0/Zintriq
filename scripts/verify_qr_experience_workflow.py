#!/usr/bin/env python3
"""QR Experience Workflow Engine — verification (real DB, no mock data)."""

from __future__ import annotations

import json
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
        sess["csrf_token"] = "verify-wf-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-wf-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        payload = {**(body or {}), "csrf_token": "verify-wf-csrf"}
        return meth(url, json=payload, headers=headers)
    return meth(url, headers=headers)


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from qr_experience_platform import init_qr_experience_tables
    from qr_experience_workflow import init_workflow_tables, get_workflow_for_experience

    ts = int(time.time())
    pwd = generate_password_hash("WorkflowVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()

        with db() as conn:
            init_qr_experience_tables(conn)
            init_workflow_tables(conn)

            for table in ("qr_experience_workflows", "qr_experience_workflow_progress"):
                if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone():
                    ok(f"Table.{table}")
                else:
                    fail(f"Table.{table}", "missing")

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"wf_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"WF Org {ts}", f"wf-org-{ts}", owner_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"wf-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"WF WS {ts}", f"wf-ws-{ts}"),
            )
            ws_id = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"wf-ws-{ts}",)
            ).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            store_id = conn.execute(
                "INSERT INTO stores (name, slug, owner_id, workspace_id) VALUES (?, ?, ?, ?)",
                (f"WF Store {ts}", f"wf-store-{ts}", owner_id, ws_id),
            ).lastrowid

            code = f"wf{ts % 100000}"
            qr_id = conn.execute(
                """INSERT INTO qr_codes (store_id, name, code, pass_type, status, workspace_id, updated_at)
                   VALUES (?, ?, ?, 'experience', 'draft', ?, datetime('now'))""",
                (store_id, "WF QR", code, ws_id),
            ).lastrowid
            exp_id = conn.execute(
                """INSERT INTO qr_experiences
                   (workspace_id, store_id, qr_code_id, name, type, status, experience_config, destination, created_by, updated_at, public_slug)
                   VALUES (?, ?, ?, ?, 'feedback', 'active', ?, ?, ?, datetime('now'), ?)""",
                (
                    ws_id, store_id, qr_id, f"WF Exp {ts}",
                    json.dumps({"template_id": "feedback_only", "description": "Test"}),
                    f"/e/{code}", owner_id, f"wf-exp-{ts}",
                ),
            ).lastrowid
            conn.execute("UPDATE qr_codes SET experience_id=? WHERE id=?", (exp_id, qr_id))

        # GET workflow (auto-creates default)
        r = api(client, "GET", f"/api/qr-experiences/{exp_id}/workflow", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("steps"):
            ok("API.get_workflow", f"{len(r.get_json()['steps'])} steps")
            wf_id = r.get_json()["id"]
        else:
            fail("API.get_workflow", f"status={r.status_code}")

        # Save custom workflow
        steps = [
            {"type": "display_content", "label": "Welcome", "config": {"content_type": "header", "title": "Hi"}},
            {"type": "feedback", "label": "Feedback", "config": {}},
            {"type": "display_content", "label": "Thank You", "config": {"content_type": "text", "body": "Thanks!"}},
        ]
        r = api(client, "PUT", f"/api/qr-experiences/{exp_id}/workflow",
                {"name": "Test Workflow", "steps": steps}, user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and len(r.get_json().get("steps", [])) == 3:
            ok("API.save_workflow")
        else:
            fail("API.save_workflow", f"status={r.status_code}")

        # Publish workflow
        r = api(client, "POST", f"/api/qr-experiences/{exp_id}/workflow/publish", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("status") == "active":
            ok("API.publish_workflow")
        else:
            fail("API.publish_workflow", f"status={r.status_code}")

        # Preview
        r = api(client, "GET", f"/api/qr-experiences/{exp_id}/workflow/preview", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and len(r.get_json().get("journey", [])) == 3:
            ok("API.preview_workflow")
        else:
            fail("API.preview_workflow", f"status={r.status_code}")

        # Runtime: scan starts workflow
        r = client.get(f"/e/wf-exp-{ts}?from=qr")
        if r.status_code == 200:
            ok("Runtime.landing")
        else:
            fail("Runtime.landing", f"status={r.status_code}")

        sess = None
        with db() as conn:
            row = conn.execute(
                "SELECT session_id FROM qr_experience_sessions WHERE experience_id=? ORDER BY id DESC LIMIT 1",
                (exp_id,),
            ).fetchone()
            if row:
                ok("Runtime.session_created")
                sid = row["session_id"]
                sess = sid
                prog = conn.execute(
                    "SELECT * FROM qr_experience_workflow_progress WHERE session_id=?", (sid,)
                ).fetchone()
                if prog and prog["status"] == "running":
                    ok("Workflow.start_on_scan")
                else:
                    fail("Workflow.start_on_scan", "no progress row")

                ev = conn.execute(
                    """SELECT event_type FROM qr_experience_analytics_events
                       WHERE experience_id=? AND event_type='workflow_started'""",
                    (exp_id,),
                ).fetchone()
                if ev:
                    ok("Analytics.workflow_started")
                else:
                    fail("Analytics.workflow_started", "missing event")
            else:
                fail("Runtime.session_created", "none")

        if sess:
            # Advance steps
            for i in range(3):
                r = api(client, "POST", f"/api/runtime/sessions/{sid}/workflow/advance", {"data": {}})
                if r.status_code != 200:
                    fail(f"Runtime.advance_step_{i+1}", f"status={r.status_code}")
                    break
            else:
                ok("Runtime.advance_all_steps")
                body = r.get_json()
                if body.get("completed"):
                    ok("Runtime.workflow_completed")
                else:
                    fail("Runtime.workflow_completed", "not marked completed")

            with db() as conn:
                completed = conn.execute(
                    """SELECT COUNT(*) AS c FROM qr_experience_analytics_events
                       WHERE experience_id=? AND event_type='workflow_step_completed'""",
                    (exp_id,),
                ).fetchone()["c"]
                if completed >= 3:
                    ok("Analytics.step_completed", str(completed))
                else:
                    fail("Analytics.step_completed", f"count={completed}")

                wf_done = conn.execute(
                    """SELECT 1 FROM qr_experience_analytics_events
                       WHERE experience_id=? AND event_type='workflow_completed'""",
                    (exp_id,),
                ).fetchone()
                if wf_done:
                    ok("Analytics.workflow_completed")
                else:
                    fail("Analytics.workflow_completed", "missing")

        with db() as conn:
            viewer_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"wf_view_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'viewer', 'active')",
                (ws_id, viewer_id),
            )

        r = api(client, "POST", f"/api/qr-experiences/{exp_id}/workflow/publish", user_id=viewer_id, ws_id=ws_id)
        if r.status_code == 403:
            ok("Permissions.viewer_blocked")
        else:
            fail("Permissions.viewer_blocked", f"status={r.status_code}")

    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name}  — {detail}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(run())
