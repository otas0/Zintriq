"""Zintriq SaaS subscriptions via Stripe Checkout + Flask + existing accounts.

Uses ZINTRIQ_STRIPE_* keys only. Merchant Connect STRIPE_SECRET_KEY is never used here.
Live purchase stays off until BILLING_ENABLED and price IDs are set.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

_log = logging.getLogger("app.billing")

PLANS = ("personal", "team")
HOSTING_GRACE_DAYS = 30
CLOUD_DATA_GRACE_DAYS = 90
_STRIPE_API = "https://api.stripe.com/v1/checkout/sessions"
_STRIPE_PORTAL_API = "https://api.stripe.com/v1/billing_portal/sessions"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def billing_enabled() -> bool:
    return _env_flag("BILLING_ENABLED", False)


def _secret() -> str:
    return (os.environ.get("ZINTRIQ_STRIPE_SECRET_KEY") or "").strip()


def _webhook_secret() -> str:
    return (os.environ.get("ZINTRIQ_STRIPE_WEBHOOK_SECRET") or "").strip()


def _price_id(plan: str) -> str:
    key = "ZINTRIQ_STRIPE_PRICE_PERSONAL" if plan == "personal" else "ZINTRIQ_STRIPE_PRICE_TEAM"
    return (os.environ.get(key) or "").strip()


def _valid_price_id(raw: str) -> bool:
    if not raw.startswith("price_") or len(raw) < 8:
        return False
    return all(ch.isalnum() or ch == "_" for ch in raw)


def _secret_allowed(secret: str) -> bool:
    if secret.startswith("sk_test_"):
        return True
    if secret.startswith("sk_live_") and _env_flag("ZINTRIQ_STRIPE_LIVE", False):
        return True
    return False


def billing_checkout_ready() -> bool:
    return bool(
        billing_enabled()
        and _secret_allowed(_secret())
        and _valid_price_id(_price_id("personal"))
    )


def billing_team_ready() -> bool:
    return bool(billing_checkout_ready() and _valid_price_id(_price_id("team")))


def billing_portal_ready() -> bool:
    return bool(billing_enabled() and _secret_allowed(_secret()))


def _plan_from_price_id(price_id: str) -> str:
    pid = (price_id or "").strip()
    if pid and pid == _price_id("team"):
        return "team"
    if pid and pid == _price_id("personal"):
        return "personal"
    return ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_utc(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_column(conn, table: str, column: str, decl: str) -> None:
    cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS zintriq_subscriptions (
            user_id INTEGER PRIMARY KEY,
            plan TEXT NOT NULL,
            status TEXT NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            stripe_session_id TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_column(conn, "zintriq_subscriptions", "hosting_until", "TEXT")
    _ensure_column(conn, "zintriq_subscriptions", "cloud_data_until", "TEXT")
    from billing_seats import ensure_seat_schema

    ensure_seat_schema(conn)


def verify_stripe_signature(payload: bytes, header: str, secret: str, *, tolerance: int = 300) -> bool:
    if not secret or not header or not payload:
        return False
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        if "=" not in item:
            continue
        k, v = item.strip().split("=", 1)
        parts.setdefault(k, []).append(v)
    try:
        timestamp = int((parts.get("t") or [""])[0])
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp) > tolerance:
        return False
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    for digest in parts.get("v1") or []:
        if hmac.compare_digest(expected, digest):
            return True
    return False


def _upsert_subscription(
    conn,
    *,
    user_id: int,
    plan: str,
    status: str,
    customer_id: str = "",
    subscription_id: str = "",
    session_id: str = "",
) -> None:
    ensure_schema(conn)
    existing = conn.execute(
        """
        SELECT status, hosting_until, cloud_data_until
        FROM zintriq_subscriptions WHERE user_id=?
        """,
        (int(user_id),),
    ).fetchone()
    prev_status = str(existing["status"] if existing else "").strip().lower()
    new_status = str(status or "").strip().lower()
    prev_active = prev_status in {"active", "trialing"}
    new_active = new_status in {"active", "trialing"}
    hosting_until = str(existing["hosting_until"] or "") if existing else ""
    cloud_data_until = str(existing["cloud_data_until"] or "") if existing else ""
    if prev_active and not new_active:
        host_deadline = _iso_utc(_utc_now() + timedelta(days=HOSTING_GRACE_DAYS))
        data_deadline = _iso_utc(_utc_now() + timedelta(days=CLOUD_DATA_GRACE_DAYS))
        prev_host = _parse_iso_utc(hosting_until)
        prev_data = _parse_iso_utc(cloud_data_until)
        new_host = _parse_iso_utc(host_deadline)
        new_data = _parse_iso_utc(data_deadline)
        if prev_host is None or (new_host and prev_host < new_host):
            hosting_until = host_deadline
        if prev_data is None or (new_data and prev_data < new_data):
            cloud_data_until = data_deadline
    if new_active:
        hosting_until = ""
    hosting_until = hosting_until or None
    cloud_data_until = cloud_data_until or None
    if existing:
        conn.execute(
            """
            UPDATE zintriq_subscriptions SET
                plan=?, status=?,
                stripe_customer_id=CASE WHEN ? != '' THEN ? ELSE stripe_customer_id END,
                stripe_subscription_id=CASE WHEN ? != '' THEN ? ELSE stripe_subscription_id END,
                stripe_session_id=CASE WHEN ? != '' THEN ? ELSE stripe_session_id END,
                hosting_until=?,
                cloud_data_until=?,
                updated_at=datetime('now')
            WHERE user_id=?
            """,
            (
                plan,
                status,
                customer_id or "",
                customer_id or "",
                subscription_id or "",
                subscription_id or "",
                session_id or "",
                session_id or "",
                hosting_until,
                cloud_data_until,
                int(user_id),
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO zintriq_subscriptions (
            user_id, plan, status, stripe_customer_id, stripe_subscription_id, stripe_session_id,
            hosting_until, cloud_data_until, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            int(user_id),
            plan,
            status,
            customer_id or "",
            subscription_id or "",
            session_id or "",
            hosting_until,
            cloud_data_until,
        ),
    )


def _create_checkout_session(
    *,
    user_id: int,
    plan: str,
    email: str,
    success_url: str,
    cancel_url: str,
    customer_id: str = "",
) -> dict:
    price = _price_id(plan)
    if not price:
        raise RuntimeError("missing_price")
    fields = {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user_id),
        "line_items[0][price]": price,
        "line_items[0][quantity]": "1",
        "metadata[user_id]": str(user_id),
        "metadata[plan]": plan,
        "subscription_data[metadata][user_id]": str(user_id),
        "subscription_data[metadata][plan]": plan,
    }
    if customer_id.startswith("cus_"):
        fields["customer"] = customer_id
    elif email and "@" in email:
        fields["customer_email"] = email
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        _STRIPE_API,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_secret()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _create_portal_session(*, customer_id: str, return_url: str) -> dict:
    fields = {
        "customer": customer_id,
        "return_url": return_url,
    }
    config = (os.environ.get("ZINTRIQ_STRIPE_PORTAL_CONFIGURATION") or "").strip()
    if config.startswith("bpc_"):
        fields["configuration"] = config
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        _STRIPE_PORTAL_API,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_secret()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def subscription_for_user(conn, user_id: int) -> dict | None:
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT plan, status, stripe_customer_id, stripe_subscription_id,
               hosting_until, cloud_data_until
        FROM zintriq_subscriptions WHERE user_id=?
        """,
        (int(user_id),),
    ).fetchone()
    if not row:
        return None
    return {
        "plan": row["plan"],
        "status": row["status"],
        "stripe_customer_id": row["stripe_customer_id"] or "",
        "stripe_subscription_id": row["stripe_subscription_id"] or "",
        "hosting_until": row["hosting_until"] or "",
        "cloud_data_until": row["cloud_data_until"] or "",
    }


def subscription_cloud_active(conn, user_id: int) -> bool:
    """True when the account may use paid cloud Publish & sync."""
    row = subscription_for_user(conn, user_id)
    if not row:
        return False
    return str(row.get("status") or "").strip().lower() in {"active", "trialing"}


def subscription_hosting_active(conn, user_id: int) -> bool:
    """Paid plan or within the 30-day published-work grace window."""
    if not billing_enabled():
        return True
    if subscription_cloud_active(conn, user_id):
        return True
    row = subscription_for_user(conn, user_id)
    if not row:
        return False
    until = _parse_iso_utc(str(row.get("hosting_until") or ""))
    return bool(until and until >= _utc_now())


def subscription_cloud_data_active(conn, user_id: int) -> bool:
    """Draft/share blobs still readable for restore within 90 days after lapse."""
    if not billing_enabled():
        return True
    if subscription_cloud_active(conn, user_id):
        return True
    row = subscription_for_user(conn, user_id)
    if not row:
        return False
    until = _parse_iso_utc(str(row.get("cloud_data_until") or ""))
    return bool(until and until >= _utc_now())


def _int_user_id(raw) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _lookup_user_id(conn, obj: dict) -> int:
    meta = obj.get("metadata") or {}
    uid = _int_user_id(meta.get("user_id") or obj.get("client_reference_id"))
    if uid:
        return uid
    sub = obj.get("id") or obj.get("subscription") or ""
    if isinstance(sub, dict):
        sub = sub.get("id") or ""
    customer = obj.get("customer") or ""
    if isinstance(customer, dict):
        customer = customer.get("id") or ""
    ensure_schema(conn)
    if sub:
        row = conn.execute(
            "SELECT user_id FROM zintriq_subscriptions WHERE stripe_subscription_id=?",
            (str(sub),),
        ).fetchone()
        if row:
            return int(row["user_id"])
    if customer:
        row = conn.execute(
            "SELECT user_id FROM zintriq_subscriptions WHERE stripe_customer_id=?",
            (str(customer),),
        ).fetchone()
        if row:
            return int(row["user_id"])
    return 0


def _status_from_stripe(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"active", "trialing"}:
        return "active"
    if value in {"past_due", "unpaid", "incomplete"}:
        return "past_due"
    if value in {"canceled", "cancelled", "incomplete_expired"}:
        return "cancelled"
    return value or "active"


def _apply_checkout_completed(conn, obj: dict) -> None:
    user_id = _lookup_user_id(conn, obj)
    if not user_id:
        return
    meta = obj.get("metadata") or {}
    plan = (meta.get("plan") or "personal").strip().lower()
    if plan not in PLANS:
        plan = "personal"
    sub = obj.get("subscription")
    if isinstance(sub, dict):
        sub_id = sub.get("id") or ""
    else:
        sub_id = sub or ""
    customer = obj.get("customer") or ""
    if isinstance(customer, dict):
        customer = customer.get("id") or ""
    _upsert_subscription(
        conn,
        user_id=user_id,
        plan=plan,
        status="active",
        customer_id=str(customer),
        subscription_id=str(sub_id),
        session_id=str(obj.get("id") or ""),
    )


def _plan_from_subscription_obj(obj: dict) -> str:
    items = obj.get("items") or {}
    data = items.get("data") if isinstance(items, dict) else items
    price_id = ""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        price = data[0].get("price")
        if isinstance(price, dict):
            price_id = str(price.get("id") or "")
        elif isinstance(price, str):
            price_id = price
    mapped = _plan_from_price_id(price_id)
    if mapped:
        return mapped
    plan = ((obj.get("metadata") or {}).get("plan") or "").strip().lower()
    if plan in PLANS:
        return plan
    return "personal"


def _apply_subscription_object(conn, obj: dict, *, status: str = "") -> None:
    user_id = _lookup_user_id(conn, obj)
    if not user_id:
        return
    plan = _plan_from_subscription_obj(obj)
    mapped = status or _status_from_stripe(str(obj.get("status") or ""))
    customer = obj.get("customer") or ""
    if isinstance(customer, dict):
        customer = customer.get("id") or ""
    _upsert_subscription(
        conn,
        user_id=user_id,
        plan=plan,
        status=mapped,
        customer_id=str(customer),
        subscription_id=str(obj.get("id") or ""),
    )


def register_billing(app) -> None:
    from app import current_user, db, login_required

    @app.context_processor
    def inject_billing_ready():
        return {
            "billing_checkout_ready": billing_checkout_ready(),
            "billing_team_ready": billing_team_ready(),
            "billing_portal_ready": billing_portal_ready(),
            "billing_enabled": billing_enabled(),
        }

    @app.get("/billing/status")
    @login_required
    def billing_status():
        """Narrow entitlement read for the portal and desktop Publish gate."""
        user = current_user()
        with db() as conn:
            ensure_schema(conn)
            uid = int(user["id"])
            row = subscription_for_user(conn, uid)
            active = subscription_cloud_active(conn, uid)
            hosting = subscription_hosting_active(conn, uid)
        return jsonify(
            {
                "billing_enabled": billing_enabled(),
                "checkout_ready": billing_checkout_ready(),
                "cloud_active": active,
                "cloud_data_until": (row or {}).get("cloud_data_until") or "",
                "hosting_active": hosting,
                "hosting_until": (row or {}).get("hosting_until") or "",
                "plan": (row or {}).get("plan") or "",
                "status": (row or {}).get("status") or "",
                # Local make + export never require a subscription.
                "local_export": True,
                "publish": active,
                "sync": active,
            }
        )

    @app.post("/billing/checkout")
    @login_required
    def billing_checkout():
        if not billing_enabled():
            abort(404)
        if not billing_checkout_ready():
            flash("Subscriptions are not open yet.", "info")
            return redirect(url_for("marketing_contact"))
        plan = (request.form.get("plan") or "").strip().lower()
        if plan not in PLANS:
            abort(400)
        if plan == "team" and not billing_team_ready():
            flash("Team billing is not configured yet.", "info")
            return redirect(url_for("marketing_contact"))
        user = current_user()
        existing = None
        with db() as conn:
            existing = subscription_for_user(conn, int(user["id"]))
        customer_id = (existing or {}).get("stripe_customer_id") or ""
        base = (os.environ.get("PUBLIC_BASE_URL") or request.url_root or "").rstrip("/")
        success = base + "/checkout/done?session_id={CHECKOUT_SESSION_ID}"
        cancel = base + "/checkout/cancel"
        try:
            session = _create_checkout_session(
                user_id=int(user["id"]),
                plan=plan,
                email=(user.get("email") or ""),
                success_url=success,
                cancel_url=cancel,
                customer_id=customer_id,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode() if exc.fp else str(exc)
            _log.warning("stripe_checkout_http_error detail=%s", detail[:400])
            flash("Checkout could not start. Try again or contact us.", "error")
            return redirect(url_for("marketing_pricing"))
        except Exception:
            _log.exception("stripe_checkout_failed")
            flash("Checkout could not start. Try again or contact us.", "error")
            return redirect(url_for("marketing_pricing"))
        url = session.get("url") or ""
        if not url.startswith("https://"):
            abort(502)
        return redirect(url, code=303)

    @app.post("/billing/portal")
    @login_required
    def billing_portal():
        if not billing_portal_ready():
            abort(404)
        user = current_user()
        with db() as conn:
            row = subscription_for_user(conn, int(user["id"]))
        customer_id = (row or {}).get("stripe_customer_id") or ""
        if not str(customer_id).startswith("cus_"):
            flash("No Stripe customer is linked to this account yet.", "info")
            return redirect(url_for("account"))
        base = (os.environ.get("PUBLIC_BASE_URL") or request.url_root or "").rstrip("/")
        return_url = base + "/account"
        try:
            portal = _create_portal_session(customer_id=str(customer_id), return_url=return_url)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode() if exc.fp else str(exc)
            _log.warning("stripe_portal_http_error detail=%s", detail[:400])
            flash("Billing portal could not start. Try again or contact us.", "error")
            return redirect(url_for("account"))
        except Exception:
            _log.exception("stripe_portal_failed")
            flash("Billing portal could not start. Try again or contact us.", "error")
            return redirect(url_for("account"))
        url = portal.get("url") or ""
        if not url.startswith("https://"):
            abort(502)
        return redirect(url, code=303)

    @app.get("/checkout/done")
    def billing_done():
        return render_template("marketing/checkout_done.html", state="done")

    @app.get("/checkout/cancel")
    def billing_cancel():
        return render_template("marketing/checkout_done.html", state="cancel")

    @app.get("/billing/seats")
    @login_required
    def billing_seats():
        user = current_user()
        from billing_seats import members_of, seat_limit_for_plan, seats_used

        with db() as conn:
            ensure_schema(conn)
            row = subscription_for_user(conn, int(user["id"]))
            plan = "personal"
            if row and row.get("status") == "active":
                plan = row.get("plan") or "personal"
            members = members_of(conn, int(user["id"]))
            used = seats_used(conn, int(user["id"]))
        return jsonify(
            {
                "plan": plan,
                "seats_used": used,
                "seat_limit": seat_limit_for_plan(plan),
                "members": members,
            }
        )

    @app.post("/billing/seats")
    @login_required
    def billing_seats_invite():
        user = current_user()
        body = request.get_json(silent=True) or request.form
        email = str((body.get("email") if hasattr(body, "get") else "") or "").strip().lower()
        from billing_seats import invite_member, seat_limit_for_plan

        if not email or "@" not in email:
            return jsonify({"error": "email required"}), 400
        with db() as conn:
            ensure_schema(conn)
            row = subscription_for_user(conn, int(user["id"]))
            plan = "personal"
            if row and row.get("status") == "active":
                plan = row.get("plan") or "personal"
            member = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not member:
                return jsonify({"error": "unknown account"}), 404
            try:
                invite_member(conn, int(user["id"]), int(member["id"]), plan=plan)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "email": email, "seat_limit": seat_limit_for_plan(plan)}), 201

    @app.post("/webhooks/stripe-billing")
    def billing_webhook():
        secret = _webhook_secret()
        payload = request.get_data(cache=False)
        header = request.headers.get("Stripe-Signature") or ""
        if not secret or not verify_stripe_signature(payload, header, secret):
            abort(400)
        try:
            event = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            abort(400)
        etype = event.get("type") or ""
        obj = (event.get("data") or {}).get("object") or {}
        with db() as conn:
            ensure_schema(conn)
            if etype == "checkout.session.completed":
                _apply_checkout_completed(conn, obj)
            elif etype == "customer.subscription.updated":
                _apply_subscription_object(conn, obj)
            elif etype in ("customer.subscription.deleted", "customer.subscription.canceled"):
                _apply_subscription_object(conn, obj, status="cancelled")
            conn.commit()
        return {"ok": True}
