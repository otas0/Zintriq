"""Store checkout — cart quote, payment sessions, order fulfillment."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import jsonify, redirect, render_template, request, session

from bos.integration_crypto import decrypt_token
from integration_platform import get_user_connection
from integration_catalog import get_payment_plugin
from observability.trace import trace
from payment_checkout_adapters import create_hosted_checkout, verify_hosted_payment
from payment_connect_plugin import (
    PAYMENT_PLUGIN_SLUGS,
    _get_payment_connection,
    merchant_payment_fields,
    merchant_paypal_credentials,
    paypal_capture_checkout_order,
    paypal_create_checkout_order,
)
from storefront_platform import deals_map_for_items

_log = logging.getLogger("app.checkout")

CHECKOUT_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkout_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT UNIQUE NOT NULL,
    store_id INTEGER NOT NULL,
    workspace_id INTEGER,
    owner_id INTEGER NOT NULL,
    customer_user_id INTEGER,
    visitor_key TEXT DEFAULT '',
    line_items TEXT NOT NULL DEFAULT '[]',
    subtotal REAL NOT NULL DEFAULT 0,
    platform_fee REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    provider TEXT,
    provider_session_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    customer_email TEXT DEFAULT '',
    customer_name TEXT DEFAULT '',
    order_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    paid_at TEXT,
    FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_checkout_store ON checkout_sessions(store_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkout_public ON checkout_sessions(public_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _public_id() -> str:
    return secrets.token_urlsafe(12)


def platform_fee_rate() -> float:
    """Platform take rate as a decimal. Default 0 — no checkout fees charged to merchants/customers."""
    max_bps = int(os.environ.get("PLATFORM_TAKE_RATE_MAX_BPS", "0") or "0")
    bps = int(os.environ.get("PLATFORM_TAKE_RATE_BPS", "0") or "0")
    bps = min(max(0, bps), max(0, max_bps))
    return bps / 10000.0


def platform_fee_cap() -> float | None:
    """Optional max platform fee per checkout (USD). None = no cap."""
    raw = os.environ.get("PLATFORM_FEE_CAP_USD", "").strip()
    if not raw or raw.lower() in ("0", "none", "off", "false"):
        return None
    try:
        cap = float(raw)
    except (TypeError, ValueError):
        _log.debug("platform_fee_cap_parse_failed", exc_info=True, extra={"op": "platform_fee_cap"})
        return None
    return cap if cap > 0 else None


def compute_platform_fee(subtotal: float) -> float:
    """Fee = subtotal × rate; optionally capped via PLATFORM_FEE_CAP_USD."""
    subtotal = max(0.0, float(subtotal))
    fee = round(subtotal * platform_fee_rate(), 2)
    cap = platform_fee_cap()
    if cap is not None:
        fee = min(fee, cap)
    return round(fee, 2)


def init_checkout_tables(conn) -> None:
    conn.executescript(CHECKOUT_SCHEMA)


def _payment_user_ids_for_store(conn, store) -> list[int]:
    """User IDs whose payment connections apply to this store."""
    ids: list[int] = []
    owner_id = store["owner_id"] if "owner_id" in store.keys() else None
    if owner_id:
        ids.append(int(owner_id))
    workspace_id = store["workspace_id"] if "workspace_id" in store.keys() else None
    if workspace_id:
        org_owner = conn.execute(
            """SELECT o.owner_id FROM workspaces w
               JOIN organizations o ON o.id = w.organization_id
               WHERE w.id=?""",
            (workspace_id,),
        ).fetchone()
        if org_owner and org_owner["owner_id"]:
            oid = int(org_owner["owner_id"])
            if oid not in ids:
                ids.append(oid)
        members = conn.execute(
            """SELECT user_id FROM workspace_members
               WHERE workspace_id=? AND status='active' AND role IN ('owner', 'administrator', 'admin')""",
            (workspace_id,),
        ).fetchall()
        for m in members:
            uid = int(m["user_id"])
            if uid not in ids:
                ids.append(uid)
    return ids


def _user_payment_providers(conn, user_id: int) -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    for slug in PAYMENT_PLUGIN_SLUGS:
        row = get_user_connection(conn, user_id, slug)
        if not row or row["status"] in ("disconnected",):
            continue
        pay = _get_payment_connection(conn, row["id"])
        meta: dict = {}
        if pay:
            try:
                meta = json.loads(pay["metadata_json"] or "{}")
            except json.JSONDecodeError:
                meta = {}
        connect_mode = meta.get("connect_mode") or "oauth"
        if connect_mode == "demo":
            continue
        spec = get_payment_plugin(slug)
        checkout_ready = True
        ready = bool(
            pay
            and (
                pay["charges_enabled"]
                or pay["account_status"] in ("active", "connected", "pending")
            )
        ) or row["status"] in ("connected", "active")
        if not ready:
            continue
        providers.append({
            "slug": slug,
            "name": (spec or {}).get("name") or slug.replace("_", " ").title(),
            "connect_mode": connect_mode,
            "livemode": bool(pay["livemode"]) if pay else False,
            "demo": False,
            "checkout_ready": checkout_ready,
        })
    return providers


def list_store_payment_providers(conn, store) -> list[dict[str, Any]]:
    """Real payment providers available for checkout (demo connections excluded)."""
    seen: set[str] = set()
    providers: list[dict[str, Any]] = []
    store_row = store if isinstance(store, dict) else dict(store)
    for user_id in _payment_user_ids_for_store(conn, store_row):
        for p in _user_payment_providers(conn, user_id):
            if p.get("connect_mode") == "demo":
                continue
            if p["slug"] not in seen and p.get("checkout_ready"):
                seen.add(p["slug"])
                providers.append(p)
    return providers


def store_checkout_enabled(conn, store) -> bool:
    return bool(list_store_payment_providers(conn, store))


def store_has_cartable_items(conn, store_id: int) -> bool:
    row = conn.execute(
        """SELECT 1 FROM items
           WHERE store_id=? AND status='published' AND allow_cart=1 LIMIT 1""",
        (store_id,),
    ).fetchone()
    return row is not None


def _line_item_price(item_row, deal: dict | None) -> float:
    if deal:
        return float(deal["sale_price"])
    return round(float(item_row["price"]), 2)


def quote_cart(conn, store_id: int, raw_items: list[dict]) -> dict[str, Any]:
    if not raw_items:
        raise ValueError("Cart is empty")
    deals_map = deals_map_for_items(conn, store_id)
    lines: list[dict[str, Any]] = []
    subtotal = 0.0

    for entry in raw_items:
        item_id = int(entry.get("item_id") or entry.get("id") or 0)
        qty = int(entry.get("qty") or entry.get("quantity") or 1)
        if item_id <= 0 or qty <= 0:
            raise ValueError("Invalid cart item")
        row = conn.execute(
            """SELECT id, name, price, image_url, inventory, status, unit, allow_cart
               FROM items WHERE id=? AND store_id=?""",
            (item_id, store_id),
        ).fetchone()
        if not row or row["status"] != "published":
            raise ValueError(f"Item {item_id} is not available")
        allow_cart = int(row["allow_cart"] or 0) if "allow_cart" in row.keys() else 0
        if not allow_cart:
            raise ValueError(f"{row['name']} is not available for online checkout")
        if row["inventory"] is not None and int(row["inventory"]) < qty:
            raise ValueError(f"{row['name']} is out of stock")
        deal = deals_map.get(item_id)
        unit_price = _line_item_price(row, deal)
        line_total = round(unit_price * qty, 2)
        subtotal += line_total
        lines.append({
            "item_id": item_id,
            "name": row["name"],
            "qty": qty,
            "unit_price": unit_price,
            "line_total": line_total,
            "image_url": row["image_url"],
            "unit": row["unit"],
            "deal_label": deal["label"] if deal else None,
        })

    subtotal = round(subtotal, 2)
    rate = platform_fee_rate()
    fee = compute_platform_fee(subtotal)
    total = round(subtotal + fee, 2)
    return {
        "line_items": lines,
        "subtotal": subtotal,
        "platform_fee": fee,
        "platform_fee_rate": rate,
        "platform_fee_cap": platform_fee_cap(),
        "total": total,
        "currency": "USD",
    }


def _merchant_stripe_secret(conn, app, owner_id: int) -> tuple[str, str, dict]:
    row = get_user_connection(conn, owner_id, "stripe")
    if not row:
        raise RuntimeError("Stripe is not connected for this store")
    pay = _get_payment_connection(conn, row["id"])
    meta = json.loads(pay["metadata_json"] or "{}") if pay else {}
    sk = app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY", "")
    mode = meta.get("connect_mode") or "oauth"
    if mode == "demo":
        return "", mode, meta
    if mode == "api_credentials":
        secret = decrypt_token(row["access_token_enc"], sk)
        return secret, mode, meta
    cfg_secret = (os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("PAYMENT_PROVIDER_KEY") or "").strip()
    if not cfg_secret:
        raise RuntimeError("Stripe platform key not configured")
    return cfg_secret, mode, meta


def _stripe_checkout_session(
    secret_key: str,
    *,
    line_items: list[dict],
    platform_fee: float,
    success_url: str,
    cancel_url: str,
    metadata: dict,
    stripe_account: str | None = None,
) -> dict:
    data: dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[checkout_public_id]": metadata.get("checkout_public_id", ""),
        "metadata[store_id]": str(metadata.get("store_id", "")),
    }
    idx = 0
    for line in line_items:
        data[f"line_items[{idx}][price_data][currency]"] = "usd"
        data[f"line_items[{idx}][price_data][product_data][name]"] = line["name"][:120]
        data[f"line_items[{idx}][price_data][unit_amount]"] = str(int(round(line["unit_price"] * 100)))
        data[f"line_items[{idx}][quantity]"] = str(line["qty"])
        idx += 1
    fee_cents = int(round(platform_fee * 100))
    headers = {"Authorization": f"Bearer {secret_key}"}
    if stripe_account and fee_cents > 0:
        data["payment_intent_data[application_fee_amount]"] = str(fee_cents)
        headers["Stripe-Account"] = stripe_account
    elif not stripe_account and fee_cents > 0:
        data[f"line_items[{idx}][price_data][currency]"] = "usd"
        data[f"line_items[{idx}][price_data][product_data][name]"] = "Service fee"
        data[f"line_items[{idx}][price_data][unit_amount]"] = str(fee_cents)
        data[f"line_items[{idx}][quantity]"] = "1"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=body,
        method="POST",
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with trace("payment.stripe.create_session", provider="stripe", op="create_session"):
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())


def _resolve_workspace_id(conn, store_id: int, workspace_id: int | None) -> int:
    if workspace_id:
        return int(workspace_id)
    row = conn.execute("SELECT workspace_id, owner_id FROM stores WHERE id=?", (store_id,)).fetchone()
    if row and row["workspace_id"]:
        return int(row["workspace_id"])
    if row and row["owner_id"]:
        ws = conn.execute(
            """SELECT workspace_id FROM workspace_members
               WHERE user_id=? AND status='active' ORDER BY workspace_id LIMIT 1""",
            (row["owner_id"],),
        ).fetchone()
        if ws:
            return int(ws["workspace_id"])
    raise RuntimeError("Store has no workspace — assign workspace_id before checkout")


def fulfill_checkout(conn, session_row, *, visitor_key: str = "") -> int:
    """Mark paid, create order, decrement inventory."""
    line_items = json.loads(session_row["line_items"] or "[]")
    ws_id = _resolve_workspace_id(
        conn,
        int(session_row["store_id"]),
        session_row["workspace_id"] if session_row["workspace_id"] else None,
    )
    oid = conn.execute(
        """INSERT INTO orders (workspace_id, store_id, customer_id, reference, amount, status, line_items, notes, updated_at)
           VALUES (?, ?, NULL, ?, ?, 'completed', ?, ?, ?)""",
        (
            ws_id,
            session_row["store_id"],
            session_row["public_id"],
            session_row["total"],
            session_row["line_items"],
            f"Paid via {session_row['provider']}",
            _now(),
        ),
    ).lastrowid
    for line in line_items:
        item_id = line.get("item_id")
        qty = int(line.get("qty") or 1)
        if not item_id:
            continue
        conn.execute(
            """UPDATE items SET inventory = inventory - ?, updated_at = ?
               WHERE id=? AND store_id=? AND inventory IS NOT NULL""",
            (qty, _now(), item_id, session_row["store_id"]),
        )
    conn.execute(
        """UPDATE checkout_sessions
           SET status='paid', paid_at=?, order_id=?, visitor_key=COALESCE(NULLIF(?, ''), visitor_key)
           WHERE id=?""",
        (_now(), oid, visitor_key, session_row["id"]),
    )
    try:
        from storefront_platform import record_store_event
        record_store_event(
            conn,
            session_row["store_id"],
            "checkout_paid",
            metadata={"checkout_id": session_row["public_id"], "total": session_row["total"]},
        )
    except Exception:
        logging.getLogger("app.checkout").debug("record_store_event_failed", exc_info=True, extra={"op": "checkout_paid"})
    return int(oid)


def register_checkout_platform(app) -> None:
    from app import current_user, db

    def _base_url() -> str:
        return (os.environ.get("PUBLIC_BASE_URL") or "http://127.0.0.1:5001").rstrip("/")

    @app.post("/api/store/<slug>/checkout/quote")
    def api_checkout_quote(slug: str):
        from app import public_store_or_404

        store = public_store_or_404(slug)
        data = request.get_json(silent=True) or {}
        items = data.get("items") or data.get("line_items") or []
        with db() as conn:
            init_checkout_tables(conn)
            if not store_checkout_enabled(conn, store):
                return jsonify({"error": "This store has not enabled online checkout yet"}), 403
            try:
                quote = quote_cart(conn, store["id"], items)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            providers = list_store_payment_providers(conn, store)
        return jsonify({**quote, "providers": providers, "checkout_enabled": True})

    @app.post("/api/store/<slug>/checkout")
    def api_checkout_create(slug: str):
        from app import public_store_or_404

        store = public_store_or_404(slug)
        data = request.get_json(silent=True) or {}
        items = data.get("items") or []
        provider = (data.get("provider") or "").strip().lower()
        customer_name = (data.get("customer_name") or "").strip()
        customer_email = (data.get("customer_email") or "").strip()

        with db() as conn:
            init_checkout_tables(conn)
            providers = list_store_payment_providers(conn, store)
            if not providers:
                return jsonify({"error": "Checkout is not available for this store"}), 403
            allowed = {p["slug"] for p in providers}
            if provider not in allowed:
                provider = providers[0]["slug"]

            try:
                quote = quote_cart(conn, store["id"], items)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            user = current_user()
            customer_user_id = int(user["id"]) if user else None
            public_id = _public_id()
            cur = conn.execute(
                """INSERT INTO checkout_sessions
                   (public_id, store_id, workspace_id, owner_id, customer_user_id,
                    line_items, subtotal, platform_fee, total, currency, provider, status,
                    customer_email, customer_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    public_id,
                    store["id"],
                    store["workspace_id"] if "workspace_id" in store.keys() else None,
                    store["owner_id"],
                    customer_user_id,
                    json.dumps(quote["line_items"]),
                    quote["subtotal"],
                    quote["platform_fee"],
                    quote["total"],
                    quote["currency"],
                    provider,
                    customer_email,
                    customer_name,
                ),
            )
            session_id = cur.lastrowid
            session_row = conn.execute("SELECT * FROM checkout_sessions WHERE id=?", (session_id,)).fetchone()

            provider_info = next(p for p in providers if p["slug"] == provider)
            if provider_info.get("demo") or provider_info.get("connect_mode") == "demo":
                conn.execute("UPDATE checkout_sessions SET status='failed' WHERE id=?", (session_id,))
                return jsonify({"error": "Reconnect this payment method with your real API keys"}), 400
            base = _base_url()

            if provider == "stripe":
                try:
                    secret, mode, meta = _merchant_stripe_secret(conn, app, int(store["owner_id"]))
                    if not secret:
                        return jsonify({"error": "Connect Stripe with your secret key in Settings to accept payments"}), 400
                    stripe_account = None
                    conn_row = get_user_connection(conn, int(store["owner_id"]), "stripe")
                    if mode == "oauth" and conn_row and conn_row["external_account_id"]:
                        stripe_account = conn_row["external_account_id"]
                    stripe_session = _stripe_checkout_session(
                        secret,
                        line_items=quote["line_items"],
                        platform_fee=quote["platform_fee"] if stripe_account or mode == "api_credentials" else 0,
                        success_url=f"{base}/store/{slug}/checkout/{public_id}/success?session_id={{CHECKOUT_SESSION_ID}}",
                        cancel_url=f"{base}/store/{slug}/checkout?cancelled=1",
                        metadata={"checkout_public_id": public_id, "store_id": store["id"]},
                        stripe_account=stripe_account,
                    )
                    conn.execute(
                        "UPDATE checkout_sessions SET provider_session_id=? WHERE id=?",
                        (stripe_session.get("id", ""), session_id),
                    )
                    return jsonify({
                        "checkout_id": public_id,
                        "provider": "stripe",
                        "checkout_url": stripe_session.get("url"),
                    })
                except (urllib.error.HTTPError, RuntimeError) as exc:
                    detail = exc.read().decode()[:200] if isinstance(exc, urllib.error.HTTPError) and exc.fp else str(exc)
                    conn.execute("UPDATE checkout_sessions SET status='failed' WHERE id=?", (session_id,))
                    rid = uuid.uuid4().hex[:12]
                    app.logger.error("payment_provider_error provider=stripe reference=%s detail=%s", rid, detail, exc_info=True)
                    return jsonify({"error": "Payment could not be processed.", "reference": rid}), 502

            if provider == "paypal":
                try:
                    client_id, client_secret, mode, _ = merchant_paypal_credentials(
                        conn, app, int(store["owner_id"])
                    )
                    order = paypal_create_checkout_order(
                        client_id,
                        client_secret,
                        mode,
                        amount=quote["total"],
                        currency=quote["currency"],
                        return_url=f"{base}/store/{slug}/checkout/{public_id}/success?provider=paypal",
                        cancel_url=f"{base}/store/{slug}/checkout?cancelled=1",
                        reference_id=public_id,
                        brand_name=store["name"] if "name" in store.keys() else "Store",
                    )
                    order_id = order.get("id", "")
                    approve_url = next(
                        (l.get("href") for l in order.get("links", []) if l.get("rel") == "approve"),
                        None,
                    )
                    if not approve_url:
                        raise RuntimeError("PayPal did not return an approval URL")
                    conn.execute(
                        "UPDATE checkout_sessions SET provider_session_id=? WHERE id=?",
                        (order_id, session_id),
                    )
                    return jsonify({
                        "checkout_id": public_id,
                        "provider": "paypal",
                        "checkout_url": approve_url,
                    })
                except (urllib.error.HTTPError, RuntimeError) as exc:
                    detail = exc.read().decode()[:200] if isinstance(exc, urllib.error.HTTPError) and exc.fp else str(exc)
                    conn.execute("UPDATE checkout_sessions SET status='failed' WHERE id=?", (session_id,))
                    rid = uuid.uuid4().hex[:12]
                    app.logger.error("payment_provider_error provider=paypal reference=%s detail=%s", rid, detail, exc_info=True)
                    return jsonify({"error": "Payment could not be processed.", "reference": rid}), 502

            try:
                fields = merchant_payment_fields(conn, app, int(store["owner_id"]), provider)
                hosted = create_hosted_checkout(
                    provider,
                    fields,
                    amount=quote["total"],
                    currency=quote["currency"],
                    description=", ".join(f"{l['qty']}× {l['name']}" for l in quote["line_items"])[:120],
                    reference=public_id,
                    return_url=f"{base}/store/{slug}/checkout/{public_id}/success?provider={provider}",
                    cancel_url=f"{base}/store/{slug}/checkout?cancelled=1",
                    brand_name=store["name"] if "name" in store.keys() else "Store",
                    customer_email=customer_email,
                    pay_url=f"{base}/store/{slug}/checkout/{public_id}/pay",
                )
                conn.execute(
                    "UPDATE checkout_sessions SET provider_session_id=? WHERE id=?",
                    (hosted.get("session_id", ""), session_id),
                )
                return jsonify({
                    "checkout_id": public_id,
                    "provider": provider,
                    "checkout_url": hosted["checkout_url"],
                })
            except (urllib.error.HTTPError, RuntimeError) as exc:
                detail = exc.read().decode()[:200] if isinstance(exc, urllib.error.HTTPError) and exc.fp else str(exc)
                conn.execute("UPDATE checkout_sessions SET status='failed' WHERE id=?", (session_id,))
                rid = uuid.uuid4().hex[:12]
                app.logger.error("payment_provider_error provider=%s reference=%s detail=%s", provider_info.get('name', provider), rid, detail, exc_info=True)
                return jsonify({"error": "Payment could not be processed.", "reference": rid}), 502

    @app.get("/store/<slug>/checkout")
    def store_checkout_page(slug: str):
        from app import public_store_or_404, storefront_render_context

        store = public_store_or_404(slug)
        with db() as conn:
            init_checkout_tables(conn)
            providers = list_store_payment_providers(conn, store)
            if not providers:
                from flask import flash, redirect, url_for
                flash("This store has not set up online payments yet.", "error")
                return redirect(url_for("storefront", slug=slug))
        ctx = storefront_render_context(store, preview_mode=False)
        ctx["checkout_providers"] = providers
        ctx["platform_fee_rate"] = platform_fee_rate()
        return render_template("customer/checkout.html", **ctx)

    @app.get("/store/<slug>/checkout/<public_id>/pay")
    def store_checkout_pay(slug: str, public_id: str):
        from app import public_store_or_404

        store = public_store_or_404(slug)
        with db() as conn:
            init_checkout_tables(conn)
            row = conn.execute(
                "SELECT * FROM checkout_sessions WHERE public_id=? AND store_id=?",
                (public_id, store["id"]),
            ).fetchone()
            if not row:
                from flask import abort
                abort(404)
            if row["status"] == "paid":
                from flask import redirect, url_for
                return redirect(url_for("store_checkout_success", slug=slug, public_id=public_id))
            line_items = json.loads(row["line_items"] or "[]")
            providers = list_store_payment_providers(conn, store)
            braintree_token = ""
            if row["provider"] == "braintree":
                try:
                    fields = merchant_payment_fields(conn, app, int(store["owner_id"]), "braintree")
                    from payment_checkout_adapters import _braintree_client_token
                    braintree_token = _braintree_client_token(fields)
                except Exception:
                    _log.debug("braintree_client_token_failed", exc_info=True, extra={"op": "store_checkout_pay"})
                    braintree_token = ""
        return render_template(
            "customer/checkout_pay.html",
            store=store,
            checkout=dict(row),
            line_items=line_items,
            providers=providers,
            braintree_token=braintree_token,
        )

    @app.post("/store/<slug>/checkout/<public_id>/braintree")
    def store_checkout_braintree(slug: str, public_id: str):
        from app import public_store_or_404
        from guest_platform import ensure_visitor_key
        from payment_checkout_adapters import _basic, _http_json

        store = public_store_or_404(slug)
        data = request.get_json(silent=True) or {}
        nonce = (data.get("nonce") or data.get("payment_method_nonce") or "").strip()
        if not nonce:
            return jsonify({"error": "Payment method is missing"}), 400
        with db() as conn:
            init_checkout_tables(conn)
            row = conn.execute(
                "SELECT * FROM checkout_sessions WHERE public_id=? AND store_id=?",
                (public_id, store["id"]),
            ).fetchone()
            if not row:
                return jsonify({"error": "Checkout not found"}), 404
            if row["status"] == "paid":
                return jsonify({"ok": True, "success_url": f"/store/{slug}/checkout/{public_id}/success"})
            if row["provider"] != "braintree":
                return jsonify({"error": "Not a Braintree checkout"}), 400
            fields = merchant_payment_fields(conn, app, int(store["owner_id"]), "braintree")
            public = fields.get("public_key") or ""
            private = fields.get("private_key") or fields.get("secret_key") or ""
            host = "https://payments.braintree-api.com" if fields.get("livemode") else "https://payments.sandbox.braintree-api.com"
            try:
                result = _http_json(
                    f"{host}/graphql",
                    payload={
                        "query": (
                            "mutation Charge($input: ChargePaymentMethodInput!) { "
                            "chargePaymentMethod(input: $input) { transaction { id status } } }"
                        ),
                        "variables": {
                            "input": {
                                "paymentMethodId": nonce,
                                "transaction": {"amount": f"{float(row['total']):.2f}"},
                            }
                        },
                    },
                    headers={
                        "Authorization": _basic(public, private),
                        "Braintree-Version": "2019-01-01",
                    },
                )
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
                rid = uuid.uuid4().hex[:12]
                app.logger.error("braintree_network_error provider=braintree reference=%s error=%s", rid, type(exc).__name__, exc_info=True)
                return jsonify({"error": "Payment could not be processed.", "reference": rid}), 502
            status = (
                ((result.get("data") or {}).get("chargePaymentMethod") or {})
                .get("transaction", {})
                .get("status")
                or ""
            )
            if status.lower() not in ("settled", "submitted_for_settlement", "settling", "authorized"):
                rid = uuid.uuid4().hex[:12]
                app.logger.error("payment_provider_error provider=braintree reference=%s detail=%s", rid, str(result.get("errors") or f"status={status or 'failed'}")[:200])
                return jsonify({"error": "Payment could not be processed.", "reference": rid}), 402
            fulfill_checkout(conn, row, visitor_key=ensure_visitor_key(session))
        return jsonify({"ok": True, "success_url": f"/store/{slug}/checkout/{public_id}/success"})

    @app.post("/store/<slug>/checkout/<public_id>/complete")
    def store_checkout_complete(slug: str, public_id: str):
        from app import public_store_or_404

        store = public_store_or_404(slug)
        with db() as conn:
            init_checkout_tables(conn)
            row = conn.execute(
                "SELECT * FROM checkout_sessions WHERE public_id=? AND store_id=?",
                (public_id, store["id"]),
            ).fetchone()
            if not row:
                return jsonify({"error": "Checkout not found"}), 404
            if row["status"] == "paid":
                return jsonify({"ok": True, "success_url": f"/store/{slug}/checkout/{public_id}/success"})
            return jsonify({
                "error": "This order must be paid on the payment provider page. Demo confirm is disabled.",
            }), 400

    @app.get("/store/<slug>/checkout/<public_id>/success")
    def store_checkout_success(slug: str, public_id: str):
        from app import public_store_or_404

        store = public_store_or_404(slug)
        stripe_session_id = request.args.get("session_id")
        paypal_token = request.args.get("token")
        rid = None
        with db() as conn:
            init_checkout_tables(conn)
            row = conn.execute(
                "SELECT * FROM checkout_sessions WHERE public_id=? AND store_id=?",
                (public_id, store["id"]),
            ).fetchone()
            if not row:
                from flask import abort
                abort(404)
            payment_verified = row["status"] == "paid"
            fulfillment_ok = row["status"] == "paid"
            if row["status"] != "paid" and stripe_session_id and row["provider"] == "stripe":
                try:
                    secret, _, _ = _merchant_stripe_secret(conn, app, int(store["owner_id"]))
                    req = urllib.request.Request(
                        f"https://api.stripe.com/v1/checkout/sessions/{stripe_session_id}",
                        method="GET",
                        headers={"Authorization": f"Bearer {secret}"},
                    )
                    with trace("payment.stripe.verify_session", provider="stripe", op="verify_session", checkout_id=public_id):
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            stripe_sess = json.loads(resp.read().decode())
                    if stripe_sess.get("payment_status") == "paid":
                        payment_verified = True
                    else:
                        payment_verified = False
                except Exception:
                    rid = uuid.uuid4().hex[:12]
                    app.logger.error("checkout_verify_failed provider=stripe checkout_id=%s reference=%s recover=true", public_id, rid, exc_info=True)
                    payment_verified = False
                if payment_verified:
                    try:
                        from guest_platform import ensure_visitor_key
                        fulfill_checkout(conn, row, visitor_key=ensure_visitor_key(session))
                        row = conn.execute(
                            "SELECT * FROM checkout_sessions WHERE id=?", (row["id"],)
                        ).fetchone()
                        fulfillment_ok = True
                    except Exception:
                        if rid is None:
                            rid = uuid.uuid4().hex[:12]
                        app.logger.error("checkout_fulfill_failed provider=stripe checkout_id=%s reference=%s recover=true", public_id, rid, exc_info=True)
                        fulfillment_ok = False
            if row["status"] != "paid" and row["provider"] == "paypal":
                order_id = paypal_token or row["provider_session_id"] or ""
                if order_id:
                    try:
                        client_id, client_secret, mode, _ = merchant_paypal_credentials(
                            conn, app, int(store["owner_id"])
                        )
                        capture = paypal_capture_checkout_order(
                            client_id, client_secret, mode, order_id
                        )
                        status = capture.get("status") or ""
                        if status in ("COMPLETED", "PARTIALLY_COMPLETED"):
                            payment_verified = True
                        else:
                            payment_verified = False
                    except Exception:
                        rid = uuid.uuid4().hex[:12]
                        app.logger.error("checkout_verify_failed provider=paypal checkout_id=%s reference=%s recover=true", public_id, rid, exc_info=True)
                        payment_verified = False
                    if payment_verified:
                        try:
                            from guest_platform import ensure_visitor_key
                            fulfill_checkout(conn, row, visitor_key=ensure_visitor_key(session))
                            row = conn.execute(
                                "SELECT * FROM checkout_sessions WHERE id=?", (row["id"],)
                            ).fetchone()
                            fulfillment_ok = True
                        except Exception:
                            if rid is None:
                                rid = uuid.uuid4().hex[:12]
                            app.logger.error("checkout_fulfill_failed provider=paypal checkout_id=%s reference=%s recover=true", public_id, rid, exc_info=True)
                            fulfillment_ok = False
            if row["status"] != "paid" and row["provider"] not in ("stripe", "paypal", "demo"):
                try:
                    fields = merchant_payment_fields(conn, app, int(store["owner_id"]), row["provider"])
                    query = {k: request.args.get(k, "") for k in request.args}
                    if verify_hosted_payment(
                        row["provider"],
                        fields,
                        session_id=row["provider_session_id"] or "",
                        query=query,
                    ):
                        payment_verified = True
                    else:
                        payment_verified = False
                except Exception:
                    rid = uuid.uuid4().hex[:12]
                    app.logger.error("checkout_verify_failed provider=%s checkout_id=%s reference=%s recover=true", row["provider"], public_id, rid, exc_info=True)
                    payment_verified = False
                if payment_verified:
                    try:
                        from guest_platform import ensure_visitor_key
                        fulfill_checkout(conn, row, visitor_key=ensure_visitor_key(session))
                        row = conn.execute(
                            "SELECT * FROM checkout_sessions WHERE id=?", (row["id"],)
                        ).fetchone()
                        fulfillment_ok = True
                    except Exception:
                        if rid is None:
                            rid = uuid.uuid4().hex[:12]
                        app.logger.error("checkout_fulfill_failed provider=%s checkout_id=%s reference=%s recover=true", row["provider"], public_id, rid, exc_info=True)
                        fulfillment_ok = False
            line_items = json.loads(row["line_items"] or "[]")
        if not payment_verified or not fulfillment_ok:
            if rid is None:
                rid = uuid.uuid4().hex[:12]
            app.logger.error("checkout_success_error checkout_id=%s reference=%s payment_verified=%s fulfillment_ok=%s recover=true", public_id, rid, payment_verified, fulfillment_ok)
            return render_template("customer/checkout_error.html", store=store, reference=rid), 500
        return render_template(
            "customer/checkout_success.html",
            store=store,
            checkout=dict(row),
            line_items=line_items,
        )

    app.init_checkout_tables = init_checkout_tables
