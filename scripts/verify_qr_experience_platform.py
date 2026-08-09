#!/usr/bin/env python3
"""QR Experience Platform — architecture verification."""

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
        sess["csrf_token"] = "verify-qr-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-qr-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        payload = {**(body or {}), "csrf_token": "verify-qr-csrf"}
        return meth(url, json=payload, headers=headers)
    return meth(url, headers=headers)


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def column_exists(conn, table, col):
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from qr_experience_platform import (
        init_qr_experience_tables, EXPERIENCE_TYPES, TYPE_TO_PASS,
    )

    ts = int(time.time())
    pwd = generate_password_hash("QrVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()
        rules = {r.rule for r in app.url_map.iter_rules()}

        with db() as conn:
            init_qr_experience_tables(conn)
            from bos.permissions import init_permissions_tables
            init_permissions_tables(conn)

            for table in ("qr_experiences", "qr_experience_events", "qr_experience_blocks", "qr_experience_actions"):
                if table_exists(conn, table):
                    ok(f"Table.{table}")
                else:
                    fail(f"Table.{table}", "missing")

            for col in ("workspace_id", "status", "experience_id", "pass_type", "ref_id"):
                if column_exists(conn, "qr_codes", col):
                    ok(f"QRCode.{col}")
                else:
                    fail(f"QRCode.{col}", "missing")

            for t in EXPERIENCE_TYPES:
                ok(f"Type.{t}", TYPE_TO_PASS[t])

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"qr_exp_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"QR Org {ts}", f"qr-org-{ts}", owner_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"qr-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"QR WS {ts}", f"qr-ws-{ts}"),
            )
            ws_id = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"qr-ws-{ts}",)
            ).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            store_id = conn.execute(
                "INSERT INTO stores (name, slug, owner_id, workspace_id) VALUES (?, ?, ?, ?)",
                (f"QR Store {ts}", f"qr-store-{ts}", owner_id, ws_id),
            ).lastrowid

        for route in ("/api/qr-experiences", "/api/qr-experiences/types", "/api/qr-experiences/summary", "/app/qr"):
            if any(route in r or r == route for r in rules) or route in rules:
                ok(f"Route.{route}")
            else:
                # flask rules may be exact
                if route in rules or any(r.startswith(route) for r in rules):
                    ok(f"Route.{route}")
                else:
                    fail(f"Route.{route}", "missing")

        if "/app/qr" in rules:
            ok("Route./app/qr.exact")
        else:
            fail("Route./app/qr.exact", "missing")

        r = api(client, "GET", "/api/qr-experiences/types", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and len(r.get_json()) >= 8:
            ok("Types.list", f"count={len(r.get_json())}")
        else:
            fail("Types.list", f"status={r.status_code}")

        from bos.permissions import has_permission
        with db() as conn:
            if has_permission(conn, owner_id, ws_id, "qr_experience.create"):
                ok("Permission.qr_experience.create")
            else:
                fail("Permission.qr_experience.create", "owner missing permission")

        r = api(client, "POST", "/api/qr-experiences", {
            "name": f"Restaurant Table {ts}",
            "template_id": "restaurant",
            "description": "Real table experience",
        }, owner_id, ws_id)
        if r.status_code == 201:
            exp = r.get_json()
            ok("Experience.create", f"id={exp['id']} code={exp.get('code')}")
            eid = exp["id"]
            code = exp.get("code")
            if exp.get("blocks") and len(exp["blocks"]) >= 2:
                ok("Builder.blocks_seeded", f"n={len(exp['blocks'])}")
            else:
                fail("Builder.blocks_seeded", "no blocks")
            if exp.get("actions") and len(exp["actions"]) >= 1:
                ok("Builder.actions_seeded", f"n={len(exp['actions'])}")
            else:
                fail("Builder.actions_seeded", "no actions")
            if (exp.get("destination") or "").startswith("/e/"):
                ok("Builder.destination", exp["destination"])
            else:
                fail("Builder.destination", str(exp.get("destination")))
        else:
            fail("Experience.create", f"status={r.status_code} {r.get_data(as_text=True)[:200]}")
            return 1

        r = api(client, "PUT", f"/api/qr-experiences/{eid}/blocks", {
            "blocks": [
                {"type": "header", "content": {"title": "Hello", "subtitle": "Welcome"}},
                {"type": "info", "content": {"title": "About", "body": "Real content"}},
                {"type": "actions", "content": {"title": "Do next"}},
            ],
        }, owner_id, ws_id)
        if r.status_code == 200 and len(r.get_json().get("blocks", [])) == 3:
            ok("Builder.blocks_update", f"n={len(r.get_json()['blocks'])}")
        else:
            fail("Builder.blocks_update", f"status={r.status_code}")

        r = api(client, "PUT", f"/api/qr-experiences/{eid}/actions", {
            "actions": [
                {"type": "open_page", "label": "View Menu", "configuration": {"target": "menu"}},
                {"type": "start_survey", "label": "Feedback", "configuration": {}},
            ],
        }, owner_id, ws_id)
        if r.status_code == 200 and len(r.get_json().get("actions", [])) == 2:
            ok("Builder.actions_update")
        else:
            fail("Builder.actions_update", f"status={r.status_code}")

        r = api(client, "PATCH", f"/api/qr-experiences/{eid}", {
            "branding": {"business_name": f"Biz {ts}", "theme": "light"},
            "description": "Updated description",
        }, owner_id, ws_id)
        if r.status_code == 200 and r.get_json().get("branding", {}).get("business_name") == f"Biz {ts}":
            ok("Builder.settings_update")
        else:
            fail("Builder.settings_update", f"status={r.status_code}")

        r = api(client, "GET", f"/api/qr-experiences/{eid}/preview", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("blocks"):
            ok("Builder.preview_api", f"blocks={len(r.get_json()['blocks'])}")
        else:
            fail("Builder.preview_api", f"status={r.status_code}")

        r = api(client, "POST", f"/api/qr-experiences/{eid}/publish", {}, owner_id, ws_id)
        if r.status_code == 200 and r.get_json().get("status") == "active":
            ok("Experience.publish")
            pub_slug = r.get_json().get("public_slug") or code
        else:
            fail("Experience.publish", f"status={r.status_code}")
            pub_slug = code

        r = api(client, "GET", "/api/qr-experiences", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and any(x["id"] == eid for x in r.get_json()):
            ok("Experience.list")
        else:
            fail("Experience.list", f"status={r.status_code}")

        r = api(client, "GET", f"/api/qr-experiences/{eid}", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("scan_url"):
            ok("Experience.detail", r.get_json()["scan_url"])
        else:
            fail("Experience.detail", f"status={r.status_code}")

        # Public landing + scan tracking via runtime
        if pub_slug:
            r = client.get(f"/e/{pub_slug}", follow_redirects=False)
            if r.status_code == 200 and b"Hello" in r.data:
                ok("Landing.public", f"/e/{pub_slug}")
            else:
                fail("Landing.public", f"status={r.status_code}")

            r = client.get(f"/qr/{code}", follow_redirects=True)
            if r.status_code == 200:
                ok("QR.scan_redirect", f"final=/e/{pub_slug}")
            else:
                fail("QR.scan_redirect", f"status={r.status_code}")
            with db() as conn:
                scans = conn.execute(
                    """SELECT COUNT(*) AS c FROM qr_experience_interactions
                       WHERE experience_id=? AND event_type='scan'""",
                    (eid,),
                ).fetchone()["c"]
            if scans >= 1:
                ok("Analytics.scan_recorded", f"scans={scans}")
            else:
                fail("Analytics.scan_recorded", "no scan interaction")

        r = api(client, "GET", "/api/qr-experiences/summary", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("active", 0) >= 1:
            ok("Summary.active", f"active={r.get_json()['active']}")
        else:
            fail("Summary.active", f"status={r.status_code}")

        r = api(client, "GET", "/app/qr", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200:
            ok("Page./app/qr")
        else:
            fail("Page./app/qr", f"status={r.status_code}")

        # Isolation: other workspace cannot see
        with db() as conn:
            other = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"qr_other_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"Other Org {ts}", f"qr-other-org-{ts}", other),
            )
            oorg = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"qr-other-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (oorg, f"Other WS {ts}", f"qr-other-ws-{ts}"),
            )
            ows = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"qr-other-ws-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ows, other),
            )

        r = api(client, "GET", f"/api/qr-experiences/{eid}", user_id=other, ws_id=ows)
        if r.status_code == 404:
            ok("Isolation.workspace")
        else:
            fail("Isolation.workspace", f"expected 404 got {r.status_code}")

    print(f"\n{'=' * 60}\nQR Experience Platform Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
