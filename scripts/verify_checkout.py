#!/usr/bin/env python3
"""Verify store checkout (cart quote + demo payment)."""

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
        sess["csrf_token"] = "verify-checkout-csrf"


def api(client, method, path, *, json_body=None):
    headers = {"X-CSRF-Token": "verify-checkout-csrf", "Content-Type": "application/json"}
    if method == "GET":
        return client.get(path, headers=headers)
    return client.post(path, headers=headers, json=json_body or {})


def run() -> int:
    os.environ.setdefault("SECRET_KEY", "bos-local-dev-secret-key-do-not-use-in-production")
    os.environ.setdefault("PAYMENT_DEMO_CONNECT", "1")

    from app import app, db
    from checkout_platform import compute_platform_fee, init_checkout_tables, platform_fee_rate, quote_cart
    from integration_platform import init_integration_tables, get_plugin_by_slug
    from payment_connect_plugin import init_payment_connection_tables
    from storefront_platform import migrate_storefront_catalog_columns

    client = app.test_client()

    with app.app_context():
        with db() as conn:
            migrate_storefront_catalog_columns(conn)
            init_integration_tables(conn)
            init_payment_connection_tables(conn)
            init_checkout_tables(conn)

            owner_id = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, 'x')",
                (f"checkout_{os.getpid()}@test.local",),
            ).lastrowid
            from team_platform import init_team_tables
            from workspace_platform import init_workspace_tables
            init_workspace_tables(conn)
            init_team_tables(conn)
            conn.execute(
                "INSERT INTO organizations (name, slug, owner_id) VALUES (?, ?, ?)",
                ("Checkout Org", f"co-{os.getpid()}", owner_id),
            )
            org_id = conn.execute("SELECT id FROM organizations WHERE slug=?", (f"co-{os.getpid()}",)).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspaces (organization_id, name, slug) VALUES (?, 'WS', ?)",
                (org_id, f"ws-{os.getpid()}"),
            )
            ws_id = conn.execute("SELECT id FROM workspaces WHERE slug=?", (f"ws-{os.getpid()}",)).fetchone()["id"]
            conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role, status) VALUES (?, ?, 'owner', 'active')",
                (ws_id, owner_id),
            )
            slug = f"checkout-store-{os.getpid()}"
            conn.execute(
                """INSERT INTO stores (slug, name, owner_id, workspace_id, status)
                   VALUES (?, 'Checkout Test', ?, ?, 'active')""",
                (slug, owner_id, ws_id),
            )
            store_id = conn.execute("SELECT id FROM stores WHERE slug=?", (slug,)).fetchone()["id"]
            item_id = conn.execute(
                "INSERT INTO items (store_id, name, price, status, allow_cart) VALUES (?, 'Test Item', 10.0, 'published', 1)",
                (store_id,),
            ).lastrowid
            plugin = get_plugin_by_slug(conn, "stripe")
            conn_id = conn.execute(
                """INSERT INTO user_integration_connections (user_id, plugin_id, status, external_account_id)
                   VALUES (?, ?, 'active', 'acct_demo')""",
                (owner_id, plugin["id"]),
            ).lastrowid
            conn.execute(
                """INSERT INTO payment_connections
                   (connection_id, provider_slug, merchant_id, account_status, charges_enabled, metadata_json)
                   VALUES (?, 'stripe', 'acct_demo', 'active', 1, '{"connect_mode":"demo"}')""",
                (conn_id,),
            )

            quote = quote_cart(conn, store_id, [{"item_id": item_id, "qty": 2}])
            if abs(quote["total"] - quote["subtotal"]) < 0.01 and quote["platform_fee"] == 0:
                ok("Quote.totals", f"subtotal={quote['subtotal']} total={quote['total']} fee=0")
            else:
                fail("Quote.totals", str(quote))

            if platform_fee_rate() == 0:
                ok("Quote.rate_zero", f"rate={platform_fee_rate()}")
            else:
                fail("Quote.rate_zero", str(platform_fee_rate()))

            expensive_id = conn.execute(
                "INSERT INTO items (store_id, name, price, status, allow_cart) VALUES (?, 'Big Item', 1000.0, 'published', 1)",
                (store_id,),
            ).lastrowid
            big_quote = quote_cart(conn, store_id, [{"item_id": expensive_id, "qty": 1}])
            if abs(big_quote["platform_fee"] - 0.0) < 0.01 and abs(big_quote["total"] - big_quote["subtotal"]) < 0.01:
                ok("Quote.no_fee", f"fee={big_quote['platform_fee']} total={big_quote['total']}")
            else:
                fail("Quote.no_fee", str(big_quote))

            small_fee = compute_platform_fee(100.0)
            if abs(small_fee - 0.0) < 0.01:
                ok("Quote.fee_zero", f"fee={small_fee}")
            else:
                fail("Quote.fee_zero", str(small_fee))

        with client.session_transaction() as sess:
            sess["csrf_token"] = "verify-checkout-csrf"

        rules = {r.rule for r in app.url_map.iter_rules()}
        for route in (
            "/api/store/<slug>/checkout/quote",
            "/api/store/<slug>/checkout",
            "/store/<slug>/checkout",
        ):
            if route in rules:
                ok(f"Route.{route}")
            else:
                fail(f"Route.{route}")

        r_quote = api(client, "POST", f"/api/store/{slug}/checkout/quote", json_body={"items": [{"item_id": item_id, "qty": 1}]})
        if r_quote.status_code == 200 and r_quote.get_json().get("line_items"):
            ok("API.quote")
        else:
            fail("API.quote", str(r_quote.get_json()))

        r_checkout = api(
            client,
            "POST",
            f"/api/store/{slug}/checkout",
            json_body={"items": [{"item_id": item_id, "qty": 1}], "provider": "stripe"},
        )
        body = r_checkout.get_json() or {}
        if r_checkout.status_code == 200 and body.get("complete_url"):
            ok("API.checkout_demo")
            checkout_id = body["checkout_id"]
        else:
            fail("API.checkout_demo", str(body))
            checkout_id = None

        if checkout_id:
            r_complete = api(client, "POST", f"/store/{slug}/checkout/{checkout_id}/complete")
            comp = r_complete.get_json() or {}
            if r_complete.status_code == 200 and comp.get("ok"):
                ok("API.complete")
            else:
                fail("API.complete", str(comp))

            with db() as conn:
                row = conn.execute(
                    "SELECT status FROM checkout_sessions WHERE public_id=?", (checkout_id,)
                ).fetchone()
                if row and row["status"] == "paid":
                    ok("DB.paid_session")
                else:
                    fail("DB.paid_session", str(dict(row) if row else None))
                order = conn.execute(
                    "SELECT id FROM orders WHERE reference=?", (checkout_id,)
                ).fetchone()
                if order:
                    ok("DB.order_created")
                else:
                    fail("DB.order_created", "missing")

    print(f"\n=== Checkout verify: {len(PASS)} passed, {len(FAIL)} failed ===")
    for name, detail in PASS:
        print(f"  OK  {name}" + (f" — {detail}" if detail else ""))
    for name, detail in FAIL:
        print(f" FAIL {name}" + (f" — {detail}" if detail else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
