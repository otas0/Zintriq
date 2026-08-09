#!/usr/bin/env python3
"""QR Experience Template Library — verification."""

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
        sess["csrf_token"] = "verify-tpl-csrf"
        if ws_id is not None:
            sess["active_workspace_id"] = ws_id


def api(client, method, url, body=None, user_id=None, ws_id=None):
    if user_id is not None:
        login_client(client, user_id, ws_id)
    headers = {"X-CSRF-Token": "verify-tpl-csrf"}
    meth = getattr(client, method.lower())
    if method.upper() in ("POST", "PATCH", "PUT", "DELETE"):
        payload = {**(body or {}), "csrf_token": "verify-tpl-csrf"}
        return meth(url, json=payload, headers=headers)
    return meth(url, headers=headers)


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from qr_experience_platform import init_qr_experience_tables
    from qr_experience_templates import (
        TEMPLATE_CATEGORIES, init_template_tables, list_templates, get_template,
    )
    from bos.permissions import has_permission, init_permissions_tables

    ts = int(time.time())
    pwd = generate_password_hash("TplVerify!123", method="pbkdf2:sha256:600000")

    with app.app_context():
        client = app.test_client()

        with db() as conn:
            init_qr_experience_tables(conn)
            init_permissions_tables(conn)

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (f"tpl_{ts}@test.local", pwd),
            ).lastrowid
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                (f"TPL Org {ts}", f"tpl-org-{ts}", owner_id),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE slug=?", (f"tpl-org-{ts}",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, f"TPL WS {ts}", f"tpl-ws-{ts}"),
            )
            ws_id = conn.execute(
                "SELECT id FROM workspaces WHERE slug=?", (f"tpl-ws-{ts}",)
            ).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            store_id = conn.execute(
                "INSERT INTO stores (name, slug, owner_id, workspace_id) VALUES (?, ?, ?, ?)",
                (f"TPL Store {ts}", f"tpl-store-{ts}", owner_id, ws_id),
            ).lastrowid
            conn.execute(
                """INSERT INTO check_in_points (store_id, point_code, name, status, active_status)
                   VALUES (?, ?, ?, 'published', 'active')""",
                (store_id, f"tplci{ts}", f"Gate {ts}"),
            )

            if has_permission(conn, owner_id, ws_id, "template.read"):
                ok("Permission.template.read")
            else:
                fail("Permission.template.read", "missing")

            templates = list_templates(conn)
            if len(templates) >= 5:
                ok("Template.seed", f"count={len(templates)}")
            else:
                fail("Template.seed", f"count={len(templates)}")

            core_ids = {"restaurant", "feedback_only", "check_in_only", "product", "service"}
            found = {t["id"] for t in templates}
            if core_ids.issubset(found):
                ok("Template.core", ",".join(sorted(core_ids)))
            else:
                fail("Template.core", f"missing={core_ids - found}")

            cats = {t["category"] for t in templates}
            if any(c in cats for c in ("Restaurant", "Event", "Retail", "Service")):
                ok("Template.categories")
            else:
                fail("Template.categories", str(cats))

            restaurant = get_template(conn, "restaurant")
            if restaurant and restaurant.get("blocks") and restaurant.get("actions"):
                ok("Template.config", f"blocks={len(restaurant['blocks'])} actions={len(restaurant['actions'])}")
            else:
                fail("Template.config", "missing blocks/actions")

        # API: grouped templates
        r = api(client, "GET", "/api/qr-templates?grouped=true", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and len(r.get_json().get("categories", [])) >= 4:
            ok("API.grouped", f"categories={len(r.get_json()['categories'])}")
        else:
            fail("API.grouped", f"status={r.status_code}")

        # API: template detail
        r = api(client, "GET", "/api/qr-templates/restaurant", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("name"):
            ok("API.detail", r.get_json()["name"])
        else:
            fail("API.detail", f"status={r.status_code}")

        # Create from template
        r = api(client, "POST", "/api/qr-experiences", {
            "name": f"Template Test {ts}",
            "template_id": "restaurant",
        }, user_id=owner_id, ws_id=ws_id)
        if r.status_code != 201:
            fail("Experience.create", f"status={r.status_code}")
            return 1
        eid = r.get_json()["id"]
        body = r.get_json()
        if body.get("template_id") == "restaurant" and body.get("blocks"):
            ok("Experience.create", f"id={eid} blocks={len(body['blocks'])}")
        else:
            fail("Experience.create", "missing template_id or blocks")

        if body.get("template_version") == 1:
            ok("Experience.template_version")
        else:
            fail("Experience.template_version", str(body.get("template_version")))

        # Customize
        r = api(client, "PATCH", f"/api/qr-experiences/{eid}", {
            "name": f"Custom Restaurant {ts}",
            "description": "Updated description",
        }, user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("name") == f"Custom Restaurant {ts}":
            ok("Experience.customize")
        else:
            fail("Experience.customize", f"status={r.status_code}")

        # Publish
        r = api(client, "POST", f"/api/qr-experiences/{eid}/publish", {}, user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and r.get_json().get("status") == "active":
            ok("Experience.publish", r.get_json().get("public_slug"))
        else:
            fail("Experience.publish", f"status={r.status_code}")

        # Runtime — customer sees correct flow
        slug = r.get_json().get("public_slug")
        r = client.get(f"/e/{slug}", follow_redirects=True)
        if r.status_code == 200 and (b"Welcome" in r.data or b"Custom Restaurant" in r.data):
            ok("Runtime.landing")
        else:
            fail("Runtime.landing", f"status={r.status_code}")

        # Template usage analytics
        r = api(client, "GET", "/api/qr-templates/usage?period=all", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200:
            usage = r.get_json().get("usage") or []
            restaurant_usage = next((u for u in usage if u.get("template_id") == "restaurant"), None)
            if restaurant_usage and restaurant_usage.get("experiences_created", 0) >= 1:
                ok("Analytics.template_usage", f"created={restaurant_usage['experiences_created']}")
            else:
                fail("Analytics.template_usage", str(usage))
        else:
            fail("Analytics.template_usage", f"status={r.status_code}")

        # Legacy templates API still works
        r = api(client, "GET", "/api/qr-experiences/templates", user_id=owner_id, ws_id=ws_id)
        if r.status_code == 200 and len(r.get_json()) >= 5:
            ok("API.legacy_templates")
        else:
            fail("API.legacy_templates", f"status={r.status_code}")

        # Versioning — experience keeps snapshot
        with db() as conn:
            row = conn.execute("SELECT experience_config FROM qr_experiences WHERE id=?", (eid,)).fetchone()
            cfg = json.loads(row["experience_config"] or "{}")
            if cfg.get("template_id") == "restaurant" and cfg.get("template_version") == 1:
                ok("Versioning.snapshot")
            else:
                fail("Versioning.snapshot", str(cfg))

    print(f"\n{'=' * 60}\nQR Experience Template Library Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
