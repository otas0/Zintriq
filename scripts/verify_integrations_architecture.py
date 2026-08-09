#!/usr/bin/env python3
"""Integration layer architecture verification."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PASS, FAIL = [], []


def ok(name, detail=""):
    PASS.append((name, detail))


def fail(name, detail):
    FAIL.append((name, detail))


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    from app import app, db
    from integrations import init_integrations_core_tables
    from integrations.auth.service import AuthService
    from integrations.config import integration_status
    from integrations.payment.service import PaymentService
    from integrations.payment import get_payment_provider, NullPaymentProvider
    from integrations.user_profile import upsert_user_profile, get_user_profile
    from integrations.subscription import ensure_workspace_subscription, update_subscription_from_provider
    from integrations.webhooks import handle_payment_webhook

    with app.app_context():
        with db() as conn:
            init_integrations_core_tables(conn)
            for table in ("user_profiles", "workspace_subscriptions", "integration_webhook_events"):
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
                ).fetchone()
                if exists:
                    ok(f"Table.{table}")
                else:
                    fail(f"Table.{table}", "missing")

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, 'x')",
                (f"intarch_{os.getpid()}@test.local",),
            ).lastrowid
            upsert_user_profile(
                conn, owner_id,
                auth_provider="local",
                auth_provider_id=str(owner_id),
                email=f"intarch_{os.getpid()}@test.local",
                full_name="Integration Test",
            )
            profile = get_user_profile(conn, owner_id)
            if profile and profile["auth_provider"] == "local":
                ok("UserProfile.upsert", f"id={profile['id']}")
            else:
                fail("UserProfile.upsert", "missing profile")

            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                ("Int Org", f"int-org-{os.getpid()}", owner_id),
            )
            org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (f"int-org-{os.getpid()}",)).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, ?, ?)",
                (org_id, "Int WS", f"int-ws-{os.getpid()}"),
            )
            ws_id = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"int-ws-{os.getpid()}",)).fetchone()["id"]
            from team_platform import init_team_tables
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )

            sub = ensure_workspace_subscription(conn, ws_id)
            if sub and sub["plan"] == "free" and sub["status"] == "inactive":
                ok("Subscription.ensure_free")
            else:
                fail("Subscription.ensure_free", str(sub))

            updated = update_subscription_from_provider(
                conn, ws_id,
                provider="stripe",
                provider_customer_id="cus_test_arch",
                provider_subscription_id="sub_test_arch",
                plan="starter",
                status="active",
            )
            if updated["status"] == "active" and updated["provider"] == "stripe":
                ok("Subscription.update_from_provider")
            else:
                fail("Subscription.update_from_provider", str(updated))

            null_provider = get_payment_provider("none")
            if isinstance(null_provider, NullPaymentProvider) and not null_provider.is_configured():
                ok("PaymentProvider.null")
            else:
                fail("PaymentProvider.null", type(null_provider).__name__)

            try:
                PaymentService.create_customer(conn, ws_id, email="x@test.local")
                fail("PaymentService.unconfigured", "should raise")
            except RuntimeError:
                ok("PaymentService.unconfigured")

            status = integration_status()
            if "auth" in status and "payment" in status and "email" in status:
                ok("Integration.status")
            else:
                fail("Integration.status", str(status))

            result = handle_payment_webhook(conn, "stripe", b'{"type":"unknown.event"}', None)
            if result.get("ok"):
                ok("Webhook.unconfigured_graceful")
            else:
                fail("Webhook.unconfigured_graceful", str(result))

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = owner_id
            sess["active_workspace_id"] = ws_id
            sess["csrf_token"] = "verify-int-csrf"
        r = client.get("/api/integrations/status", headers={"X-CSRF-Token": "verify-int-csrf"})
        if r.status_code == 200 and "auth" in r.get_json():
            ok("API.integrations_status")
        else:
            fail("API.integrations_status", f"status={r.status_code}")

        r = client.get("/api/me/profile", headers={"X-CSRF-Token": "verify-int-csrf"})
        if r.status_code == 200 and r.get_json().get("profile"):
            ok("API.me_profile")
        else:
            fail("API.me_profile", f"status={r.status_code}")

        r = client.get(f"/api/workspaces/{ws_id}/subscription", headers={"X-CSRF-Token": "verify-int-csrf"})
        if r.status_code == 200 and r.get_json().get("plan"):
            ok("API.workspace_subscription")
        else:
            fail("API.workspace_subscription", f"status={r.status_code}")

    print(f"\n{'=' * 60}\nIntegration Layer Architecture Verification\n{'=' * 60}")
    for name, detail in PASS:
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f"  FAIL  {name} — {detail}")
    print(f"\n{len(PASS)} PASS, {len(FAIL)} FAIL\n")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(run())
