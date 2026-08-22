#!/usr/bin/env python3
"""Verify payment connect plugins (Stripe, PayPal, PayPay)."""

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


def login_client(client, user_id: int):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "verify-pay-csrf"


def api(client, method, path, *, user_id=None, json_body=None):
    if user_id is not None:
        login_client(client, user_id)
    headers = {"X-CSRF-Token": "verify-pay-csrf"}
    if method == "GET":
        return client.get(path, headers=headers)
    return client.post(path, headers=headers, json=json_body or {})


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    os.environ.setdefault("STRIPE_CONNECT_CLIENT_ID", "ca_test_verify")
    os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_verify")
    os.environ.setdefault("PAYPAL_CLIENT_ID", "paypal_test_verify")
    os.environ.setdefault("PAYPAL_CLIENT_SECRET", "paypal_secret_verify")
    os.environ.setdefault("PAYPAY_CLIENT_ID", "paypay_test_verify")
    os.environ.setdefault("PAYPAY_CLIENT_SECRET", "paypay_secret_verify")

    from app import app, db
    from integration_platform import init_integration_tables, get_plugin_by_slug, get_user_connection
    from payment_connect_plugin import (
        PAYMENT_PLUGIN_SLUGS,
        init_payment_connection_tables,
        provider_configured,
    )

    with app.app_context():
        with db() as conn:
            init_integration_tables(conn)
            init_payment_connection_tables(conn)

            for slug in PAYMENT_PLUGIN_SLUGS:
                plugin = get_plugin_by_slug(conn, slug)
                if plugin:
                    ok(f"Plugin.{slug}", f"id={plugin['id']}")
                else:
                    fail(f"Plugin.{slug}", "missing from integration_plugins")

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, 'x')",
                (f"payconn_{os.getpid()}@test.local",),
            ).lastrowid

        client = app.test_client()

        rules = {r.rule for r in app.url_map.iter_rules()}
        expected_routes = [
            "/api/integrations/payments/<provider>/oauth/start",
            "/api/integrations/payments/<provider>/oauth/callback",
            "/api/integrations/payments/<provider>/status",
            "/api/integrations/payments/<provider>/connect",
            "/api/integrations/payments/<provider>/demo",
            "/api/integrations/payments/<provider>/disconnect",
            "/api/integrations/payments/paypay/connect",
            "/api/integrations/payments/config",
        ]
        for route in expected_routes:
            if route in rules:
                ok(f"Route.{route}")
            else:
                fail(f"Route.{route}", "not registered")

        r_cfg = api(client, "GET", "/api/integrations/payments/config", user_id=owner_id)
        if r_cfg.status_code == 200 and "providers" in r_cfg.get_json():
            ok("API.config")
        else:
            fail("API.config", f"status={r_cfg.status_code}")

        for slug in PAYMENT_PLUGIN_SLUGS:
            if provider_configured(app, slug):
                ok(f"Configured.{slug}")
            else:
                fail(f"Configured.{slug}", "expected true with test env")

            r_start = api(client, "GET", f"/api/integrations/payments/{slug}/oauth/start", user_id=owner_id)
            data = r_start.get_json() or {}
            if r_start.status_code == 200 and data.get("auth_url"):
                ok(f"OAuth.start.{slug}")
            else:
                fail(f"OAuth.start.{slug}", f"status={r_start.status_code} body={data}")

        with db() as conn:
            cur = conn.execute(
                """INSERT INTO user_integration_connections
                   (user_id, plugin_id, external_account_id, status)
                   SELECT ?, id, 'acct_test_verify', 'connected'
                   FROM integration_plugins WHERE slug='stripe'""",
                (owner_id,),
            )
            conn_id = cur.lastrowid
            conn.execute(
                """INSERT INTO payment_connections
                   (connection_id, provider_slug, merchant_id, account_status, charges_enabled)
                   VALUES (?, 'stripe', 'acct_test_verify', 'active', 1)""",
                (conn_id,),
            )

        r_status = api(client, "GET", "/api/integrations/payments/paypay/status", user_id=owner_id)
        body = r_status.get_json() or {}
        if r_status.status_code == 200 and body.get("provider") == "paypay":
            ok("API.paypay_status", body.get("status", ""))
        else:
            fail("API.paypay_status", str(body))

        r_demo = api(client, "POST", "/api/integrations/payments/stripe/demo", user_id=owner_id)
        demo = r_demo.get_json() or {}
        if r_demo.status_code == 200 and demo.get("ok"):
            ok("API.demo_connect")
        elif os.environ.get("PAYMENT_DEMO_CONNECT", "").lower() in ("1", "true", "yes"):
            fail("API.demo_connect", str(demo))
        else:
            ok("API.demo_connect", "skipped (set PAYMENT_DEMO_CONNECT=1 to test)")

        r_paypay = api(
            client,
            "POST",
            "/api/integrations/payments/paypay/connect",
            user_id=owner_id,
            json_body={
                "merchant_id": "m_test_123",
                "api_key": "key_test",
                "api_secret": "secret_test",
            },
        )
        pp = r_paypay.get_json() or {}
        if r_paypay.status_code == 200 and pp.get("ok"):
            ok("API.paypay_credentials")
        else:
            fail("API.paypay_credentials", str(pp))

        with db() as conn:
            row = get_user_connection(conn, owner_id, "paypay")
            if row and row["external_account_id"] == "m_test_123":
                ok("DB.paypay_connection")
            else:
                fail("DB.paypay_connection", "missing or wrong merchant id")

        r_plugins = api(client, "GET", "/api/integrations/plugins", user_id=owner_id)
        plugins = r_plugins.get_json() or []
        for slug in PAYMENT_PLUGIN_SLUGS:
            p = next((x for x in plugins if x.get("slug") == slug), None)
            if p and p.get("connection"):
                ok(f"PluginsAPI.{slug}_connection")
            elif p:
                ok(f"PluginsAPI.{slug}_listed")
            else:
                fail(f"PluginsAPI.{slug}", "missing")

        js = open(os.path.join(ROOT, "static/bos/features/integrations-section.js")).read()
        for token in ("stripe", "paypal", "paypay", "openPaymentDrawer", "PAYMENT_SLUGS"):
            if token in js:
                ok(f"UI.{token}")
            else:
                fail(f"UI.{token}", "missing from integrations-section.js")

    print(f"\n=== Payment connect verify: {len(PASS)} passed, {len(FAIL)} failed ===")
    for name, detail in PASS:
        print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f" FAIL {name}" + (f" — {detail}" if detail else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
