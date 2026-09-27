"""Payment Connect — merchant OAuth / credential connections for Stripe, PayPal, PayPay."""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import abort, jsonify, redirect, request, session, url_for

from bos.integration_crypto import decrypt_token, encrypt_token
from integration_platform import (
    get_plugin_by_slug,
    get_user_connection,
    log_integration_event,
)

from integration_catalog import get_payment_plugin, payment_plugin_slugs

_log = logging.getLogger("app.payment")

PAYMENT_PLUGIN_SLUGS = payment_plugin_slugs()

STRIPE_CONNECT_AUTH = "https://connect.stripe.com/oauth/authorize"
STRIPE_CONNECT_TOKEN = "https://connect.stripe.com/oauth/token"
STRIPE_API = "https://api.stripe.com/v1"

PAYPAL_AUTH_LIVE = "https://www.paypal.com/signin/authorize"
PAYPAL_AUTH_SANDBOX = "https://www.sandbox.paypal.com/signin/authorize"
PAYPAL_API_LIVE = "https://api-m.paypal.com"
PAYPAL_API_SANDBOX = "https://api-m.sandbox.paypal.com"
PAYPAL_SCOPES = "openid profile email https://uri.paypal.com/services/payments/realtimepayment"

PAYPAY_API_PROD = "https://api.paypay.ne.jp"
PAYPAY_API_STG = "https://stg-api.paypay.ne.jp"
PAYPAY_AUTH_PROD = "https://paypay.ne.jp/portal/oauth/authorize"
PAYPAY_AUTH_STG = "https://stg.paypay.ne.jp/portal/oauth/authorize"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _secret_key(app) -> str:
    return app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY", "")


def _http_post_form(url: str, data: dict, *, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode({k: v for k, v in data.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def _http_get_json(url: str, access_token: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def _http_post_json(url: str, payload: dict, *, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def init_payment_connection_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS payment_connections (
            connection_id INTEGER NOT NULL UNIQUE,
            provider_slug TEXT NOT NULL,
            merchant_id TEXT DEFAULT '',
            account_status TEXT NOT NULL DEFAULT 'pending',
            charges_enabled INTEGER NOT NULL DEFAULT 0,
            payouts_enabled INTEGER NOT NULL DEFAULT 0,
            livemode INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(connection_id) REFERENCES user_integration_connections(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_payment_conn_provider ON payment_connections(provider_slug);
        """
    )
    conn.execute(
        """UPDATE payment_connections
           SET livemode=1, updated_at=?
           WHERE livemode=0
             AND COALESCE(metadata_json, '') NOT LIKE '%"connect_mode": "demo"%'""",
        (_now(),),
    )


def _as_dict(row) -> dict:
    return dict(row) if row else {}


def _oauth_redirect_uri(app, provider: str, env_key: str) -> str:
    explicit = os.environ.get(env_key, "").strip()
    if explicit:
        return explicit
    try:
        return url_for("payment_connect_oauth_callback", provider=provider, _external=True)
    except RuntimeError:
        base = (os.environ.get("PUBLIC_BASE_URL") or "http://127.0.0.1:5001").rstrip("/")
        return f"{base}/api/integrations/payments/{provider}/oauth/callback"


def _provider_config(app, slug: str) -> dict | None:
    slug = slug.lower()
    if slug == "stripe":
        client_id = (
            os.environ.get("STRIPE_CONNECT_CLIENT_ID")
            or os.environ.get("STRIPE_CLIENT_ID")
            or ""
        ).strip()
        secret = (os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("PAYMENT_PROVIDER_KEY") or "").strip()
        redirect_uri = _oauth_redirect_uri(app, "stripe", "STRIPE_CONNECT_REDIRECT_URI")
        if not client_id or not secret:
            return None
        return {
            "slug": "stripe",
            "client_id": client_id,
            "client_secret": secret,
            "redirect_uri": redirect_uri,
            "auth_url": STRIPE_CONNECT_AUTH,
            "token_url": STRIPE_CONNECT_TOKEN,
            "scope": "read_write",
        }
    if slug == "paypal":
        client_id = (os.environ.get("PAYPAL_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("PAYPAL_CLIENT_SECRET") or "").strip()
        mode = (os.environ.get("PAYPAL_MODE") or "live").strip().lower()
        api_base = PAYPAL_API_LIVE if mode == "live" else PAYPAL_API_SANDBOX
        auth_url = PAYPAL_AUTH_LIVE if mode == "live" else PAYPAL_AUTH_SANDBOX
        redirect_uri = _oauth_redirect_uri(app, "paypal", "PAYPAL_OAUTH_REDIRECT_URI")
        if not client_id or not client_secret:
            return None
        return {
            "slug": "paypal",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "auth_url": auth_url,
            "token_url": f"{api_base}/v1/oauth2/token",
            "userinfo_url": f"{api_base}/v1/identity/oauth2/userinfo?schema=paypalv1.1",
            "scope": PAYPAL_SCOPES,
            "mode": mode,
        }
    if slug == "paypay":
        client_id = (os.environ.get("PAYPAY_CLIENT_ID") or os.environ.get("PAYPAY_API_KEY") or "").strip()
        client_secret = (os.environ.get("PAYPAY_CLIENT_SECRET") or os.environ.get("PAYPAY_API_SECRET") or "").strip()
        mode = (os.environ.get("PAYPAY_MODE") or "production").strip().lower()
        api_base = PAYPAY_API_PROD if mode == "production" else PAYPAY_API_STG
        auth_url = PAYPAY_AUTH_PROD if mode == "production" else PAYPAY_AUTH_STG
        redirect_uri = _oauth_redirect_uri(app, "paypay", "PAYPAY_OAUTH_REDIRECT_URI")
        if not client_id or not client_secret:
            return None
        return {
            "slug": "paypay",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "auth_url": auth_url,
            "token_url": f"{api_base}/v2/oauth/token",
            "scope": "direct_debit_read write",
            "mode": mode,
        }
    return None


def provider_configured(app, slug: str) -> bool:
    return _provider_config(app, slug) is not None


def _store_tokens(conn, connection_id: int, access: str, refresh: str, expires_at: str | None, app) -> None:
    sk = _secret_key(app)
    conn.execute(
        """UPDATE user_integration_connections
           SET access_token_enc=?, refresh_token_enc=?, expires_at=?, status='connected', updated_at=?
           WHERE id=?""",
        (
            encrypt_token(access, sk),
            encrypt_token(refresh, sk) if refresh else "",
            expires_at,
            _now(),
            connection_id,
        ),
    )


def _upsert_payment_connection(
    conn,
    connection_id: int,
    provider_slug: str,
    *,
    merchant_id: str = "",
    account_status: str = "pending",
    charges_enabled: bool = False,
    payouts_enabled: bool = False,
    livemode: bool = False,
    metadata: dict | None = None,
) -> None:
    meta_json = json.dumps(metadata or {})
    conn.execute(
        """INSERT INTO payment_connections
           (connection_id, provider_slug, merchant_id, account_status,
            charges_enabled, payouts_enabled, livemode, metadata_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(connection_id) DO UPDATE SET
             merchant_id=excluded.merchant_id,
             account_status=excluded.account_status,
             charges_enabled=excluded.charges_enabled,
             payouts_enabled=excluded.payouts_enabled,
             livemode=excluded.livemode,
             metadata_json=excluded.metadata_json,
             updated_at=excluded.updated_at""",
        (
            connection_id,
            provider_slug,
            merchant_id,
            account_status,
            1 if charges_enabled else 0,
            1 if payouts_enabled else 0,
            1 if livemode else 0,
            meta_json,
            _now(),
        ),
    )


def _get_payment_connection(conn, connection_id: int):
    return conn.execute(
        "SELECT * FROM payment_connections WHERE connection_id=?",
        (connection_id,),
    ).fetchone()


def merchant_payment_fields(conn, app, owner_id: int, slug: str) -> dict:
    """Decrypted merchant credentials + metadata for a connected payment plugin."""
    row = get_user_connection(conn, owner_id, slug)
    if not row:
        raise RuntimeError(f"{slug} is not connected for this store")
    if row["status"] in ("disconnected",):
        raise RuntimeError(f"{slug} is disconnected — reconnect in Settings")
    pay = _get_payment_connection(conn, row["id"])
    meta: dict = {}
    if pay:
        try:
            meta = json.loads(pay["metadata_json"] or "{}")
        except json.JSONDecodeError:
            meta = {}
    if meta.get("connect_mode") == "demo":
        raise RuntimeError("Demo connections cannot take real payments — reconnect with your API keys")
    sk = _secret_key(app)
    try:
        access = decrypt_token(row["access_token_enc"], sk) if row["access_token_enc"] else ""
    except Exception:
        _log.debug("payment_access_token_decrypt_failed", exc_info=True, extra={"op": "payment_connect_fields"})
        access = ""
    try:
        refresh = decrypt_token(row["refresh_token_enc"], sk) if row["refresh_token_enc"] else ""
    except Exception:
        _log.debug("payment_refresh_token_decrypt_failed", exc_info=True, extra={"op": "payment_connect_fields"})
        refresh = ""
    fields = {k: v for k, v in meta.items() if k not in ("connect_mode", "checkout_ready", "note")}
    if access and "secret_key" not in fields and "api_key" not in fields and "access_token" not in fields:
        fields.setdefault("secret_key", access)
        fields.setdefault("access_token", access)
        fields.setdefault("api_key", access)
    if refresh:
        fields.setdefault("client_secret", refresh)
        fields.setdefault("api_secret", refresh)
        fields.setdefault("public_key", refresh)
    if pay:
        fields["livemode"] = bool(pay["livemode"])
        if pay["merchant_id"] and "merchant_id" not in fields:
            fields["merchant_id"] = pay["merchant_id"]
    return fields


def _load_access_token(conn, connection_row, app, provider_slug: str) -> str:
    sk = _secret_key(app)
    try:
        access = decrypt_token(connection_row["access_token_enc"], sk)
    except Exception as exc:
        conn.execute(
            "UPDATE user_integration_connections SET status='error', updated_at=? WHERE id=?",
            (_now(), connection_row["id"]),
        )
        raise RuntimeError(f"{provider_slug} token invalid — reconnect in Settings") from exc
    expires = connection_row["expires_at"]
    if expires and expires <= _now() and connection_row["refresh_token_enc"]:
        cfg = _provider_config(app, provider_slug)
        if not cfg:
            raise RuntimeError(f"{provider_slug} OAuth not configured")
        refresh = decrypt_token(connection_row["refresh_token_enc"], sk)
        if provider_slug == "stripe":
            token_data = _http_post_form(
                cfg["token_url"],
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_secret": cfg["client_secret"],
                },
            )
        elif provider_slug == "paypal":
            basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
            token_data = _http_post_form(
                cfg["token_url"],
                {"grant_type": "refresh_token", "refresh_token": refresh},
                headers={"Authorization": f"Basic {basic}"},
            )
        else:
            token_data = _http_post_form(
                cfg["token_url"],
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                },
            )
        access = token_data.get("access_token", "")
        new_refresh = token_data.get("refresh_token") or refresh
        expires_in = int(token_data.get("expires_in", 3600))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).replace(microsecond=0).isoformat()
        _store_tokens(conn, connection_row["id"], access, new_refresh, expires_at, app)
    return access


def _demo_connect_allowed(app) -> bool:
    """Demo connect permanently disabled — real credentials only."""
    return False


def _connection_metadata(conn, connection_id: int) -> dict:
    pay = _get_payment_connection(conn, connection_id)
    if not pay:
        return {}
    try:
        return json.loads(pay["metadata_json"] or "{}")
    except json.JSONDecodeError:
        _log.debug("connection_metadata_json_parse_failed", exc_info=True, extra={"op": "_connection_metadata"})
        return {}


def _verify_stripe_secret(secret_key: str) -> dict:
    req = urllib.request.Request(
        f"{STRIPE_API}/account",
        method="GET",
        headers={"Authorization": f"Bearer {secret_key}"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


def _verify_paypal_credentials(client_id: str, client_secret: str, mode: str) -> dict:
    api_base = PAYPAL_API_LIVE if mode == "live" else PAYPAL_API_SANDBOX
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return _http_post_form(
        f"{api_base}/v1/oauth2/token",
        {"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )


def _ensure_plugin_connection(conn, user_id: int, plugin_slug: str) -> tuple[int, bool]:
    plugin = get_plugin_by_slug(conn, plugin_slug)
    if not plugin:
        raise RuntimeError(f"{plugin_slug} plugin not available")
    existing = conn.execute(
        "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
        (user_id, plugin["id"]),
    ).fetchone()
    if existing:
        return int(existing["id"]), False
    # Never mark connected until credentials pass live verify.
    conn_id = conn.execute(
        """INSERT INTO user_integration_connections (user_id, plugin_id, status)
           VALUES (?, ?, 'pending')""",
        (user_id, plugin["id"]),
    ).lastrowid
    return int(conn_id), True


def _rollback_request_db() -> None:
    """Undo partial writes when the view catches an error (teardown would otherwise commit)."""
    try:
        from flask import g, has_app_context
        if not has_app_context():
            return
        conn = g.get("_sqlite_conn")
        if conn is not None:
            conn.rollback()
    except Exception:
        logging.getLogger("app.payment").debug("rollback_helper_failed", exc_info=True)


def _purge_fake_integration_connections(conn) -> int:
    """Remove demo / unverified / pending-orphan connections left by older builds."""
    rows = conn.execute(
        """SELECT uic.id, uic.status, uic.external_account_id, uic.external_account_email,
                  uic.access_token_enc, pc.metadata_json
           FROM user_integration_connections uic
           LEFT JOIN payment_connections pc ON pc.connection_id = uic.id"""
    ).fetchall()
    removed = 0
    for row in rows:
        meta_raw = row["metadata_json"] or ""
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except json.JSONDecodeError:
            meta = {}
        status = (row["status"] or "").lower()
        is_demo = meta.get("connect_mode") == "demo" or "Sandbox demo" in str(meta.get("note") or "")
        is_unverified = meta.get("connect_mode") == "api_credentials" and not meta.get("verified")
        is_pending = status == "pending"
        looks_demo_id = bool(
            (row["external_account_email"] or "").endswith(".local")
            or str(row["external_account_id"] or "").startswith(("acct_demo", "demo_", "PAYPAL_DEMO"))
            or "_demo_" in str(row["external_account_id"] or "")
        )
        if is_demo or is_unverified or is_pending or looks_demo_id:
            conn.execute("DELETE FROM payment_connections WHERE connection_id=?", (row["id"],))
            conn.execute("DELETE FROM integration_event_logs WHERE connection_id=?", (row["id"],))
            conn.execute("DELETE FROM user_integration_connections WHERE id=?", (row["id"],))
            removed += 1
    return removed


def _refresh_stripe_from_connection(conn, app, connection_row: dict) -> dict:
    connection_id = int(connection_row["id"])
    meta = _connection_metadata(conn, connection_id)
    sk_app = _secret_key(app)

    if meta.get("connect_mode") == "api_credentials":
        secret = decrypt_token(connection_row["access_token_enc"], sk_app)
        data = _verify_stripe_secret(secret)
        account_id = data.get("id") or connection_row.get("external_account_id") or ""
        charges = bool(data.get("charges_enabled"))
        payouts = bool(data.get("payouts_enabled"))
        status = "active" if charges else "pending"
        _upsert_payment_connection(
            conn,
            connection_id,
            "stripe",
            merchant_id=account_id,
            account_status=status,
            charges_enabled=charges,
            payouts_enabled=payouts,
            livemode=secret_key.startswith(("sk_live_", "rk_live_")),
            metadata={**meta, "connect_mode": "api_credentials"},
        )
        conn.execute(
            """UPDATE user_integration_connections
               SET external_account_id=?, external_account_email=?, status=?, updated_at=?
               WHERE id=?""",
            (account_id, data.get("email") or "", "active" if charges else "connected", _now(), connection_id),
        )
        return data

    account_id = connection_row.get("external_account_id") or ""
    if not account_id:
        return {}
    cfg = _provider_config(app, "stripe")
    if not cfg:
        return {}
    req = urllib.request.Request(
        f"{STRIPE_API}/accounts/{account_id}",
        method="GET",
        headers={"Authorization": f"Bearer {cfg['client_secret']}"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode())
    charges = bool(data.get("charges_enabled"))
    payouts = bool(data.get("payouts_enabled"))
    status = "active" if charges else "pending"
    if data.get("requirements", {}).get("disabled_reason"):
        status = "restricted"
    _upsert_payment_connection(
        conn,
        connection_id,
        "stripe",
        merchant_id=account_id,
        account_status=status,
        charges_enabled=charges,
        payouts_enabled=payouts,
        livemode=bool(data.get("livemode")),
        metadata={**meta, "connect_mode": meta.get("connect_mode") or "oauth"},
    )
    conn.execute(
        "UPDATE user_integration_connections SET status=?, updated_at=? WHERE id=?",
        ("active" if charges else "connected", _now(), connection_id),
    )
    return data


def _refresh_stripe_account(conn, app, connection_id: int, account_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM user_integration_connections WHERE id=?", (connection_id,)
    ).fetchone()
    if row:
        return _refresh_stripe_from_connection(conn, app, _as_dict(row))
    return {}


def _refresh_paypal_account(conn, app, connection_row) -> dict:
    row = _as_dict(connection_row)
    meta = _connection_metadata(conn, row["id"])
    sk_app = _secret_key(app)

    if meta.get("connect_mode") == "api_credentials":
        client_id = decrypt_token(row["access_token_enc"], sk_app)
        client_secret = decrypt_token(row["refresh_token_enc"], sk_app)
        mode = meta.get("mode") or (os.environ.get("PAYPAL_MODE") or "live").strip().lower()
        token_data = _verify_paypal_credentials(client_id, client_secret, mode)
        expires_in = int(token_data.get("expires_in", 3600))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).replace(microsecond=0).isoformat()
        _store_tokens(conn, row["id"], client_id, client_secret, expires_at, app)
        _upsert_payment_connection(
            conn,
            row["id"],
            "paypal",
            merchant_id=client_id[:24],
            account_status="active",
            charges_enabled=True,
            payouts_enabled=True,
            livemode=mode == "live",
            metadata={**meta, "connect_mode": "api_credentials", "mode": mode},
        )
        conn.execute(
            """UPDATE user_integration_connections
               SET external_account_id=?, status='active', updated_at=? WHERE id=?""",
            (client_id[:24], _now(), row["id"]),
        )
        return token_data

    cfg = _provider_config(app, "paypal")
    if not cfg:
        return {}
    access = _load_access_token(conn, row, app, "paypal")
    profile = _http_get_json(cfg["userinfo_url"], access)
    payer_id = profile.get("payer_id") or profile.get("user_id") or ""
    email = profile.get("email") or profile.get("emails", [{}])[0].get("value", "")
    verified = profile.get("verified_account", True)
    status = "active" if verified else "pending"
    _upsert_payment_connection(
        conn,
        row["id"],
        "paypal",
        merchant_id=payer_id,
        account_status=status,
        charges_enabled=verified,
        payouts_enabled=verified,
        livemode=cfg.get("mode") == "live",
        metadata={**meta, "connect_mode": "oauth", "verified_account": verified},
    )
    conn.execute(
        """UPDATE user_integration_connections
           SET external_account_id=?, external_account_email=?, status=?, updated_at=?
           WHERE id=?""",
        (payer_id, email, "active" if verified else "connected", _now(), row["id"]),
    )
    return profile


def payment_connection_to_api(payment_row) -> dict | None:
    if not payment_row:
        return None
    meta = {}
    try:
        meta = json.loads(payment_row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        _log.debug("payment_connection_metadata_parse_failed", exc_info=True, extra={"op": "payment_connection_to_api"})
        pass
    return {
        "provider": payment_row["provider_slug"],
        "merchant_id": payment_row["merchant_id"],
        "account_status": payment_row["account_status"],
        "charges_enabled": bool(payment_row["charges_enabled"]),
        "payouts_enabled": bool(payment_row["payouts_enabled"]),
        "livemode": bool(payment_row["livemode"]),
        "metadata": meta,
    }


def build_status_payload(app, conn, user_id: int, provider_slug: str) -> dict:
    configured = provider_configured(app, provider_slug)
    connection = _as_dict(get_user_connection(conn, user_id, provider_slug))
    if not connection:
        return {
            "provider": provider_slug,
            "configured": configured,
            "demo_available": False,
            "connected": False,
            "status": "not_connected",
        }
    payment = _get_payment_connection(conn, connection["id"])
    logs = conn.execute(
        """SELECT event_type, status, error_message, created_at
           FROM integration_event_logs WHERE connection_id=?
           ORDER BY created_at DESC LIMIT 12""",
        (connection["id"],),
    ).fetchall()
    status = connection["status"] or "connected"
    if payment:
        if payment["account_status"] == "active" or payment["charges_enabled"]:
            status = "active"
        elif payment["account_status"] in ("restricted", "error"):
            status = "error"
    payload = {
        "provider": provider_slug,
        "configured": configured,
        "demo_available": False,
        "connected": connection["status"] in ("connected", "active", "installed"),
        "status": status if connection["status"] in ("connected", "active", "installed") else "not_connected",
        "external_account_id": connection.get("external_account_id"),
        "external_account_email": connection.get("external_account_email"),
        "payment": payment_connection_to_api(payment),
        "recent_logs": [dict(row) for row in logs],
    }
    return payload


def _infer_livemode(fields: dict) -> bool:
    """Owner connections are live. Only treat clearly-test keys as sandbox."""
    mode = str(fields.get("mode") or "").strip().lower()
    if mode in ("sandbox", "test", "demo"):
        return False
    if mode in ("live", "production"):
        return True
    blob = " ".join(str(v) for v in fields.values() if isinstance(v, str)).lower()
    test_markers = (
        "sk_test_", "rk_test_", "pk_test_", "sk_sbox_",
        "test_sk_", "test_ck_", "test_gsk_",
    )
    return not any(marker in blob for marker in test_markers)


def _connect_generic_payment_credentials(
    conn,
    app,
    *,
    conn_id: int,
    provider: str,
    data: dict,
    preverified: dict | None = None,
) -> None:
    from integration_credential_verify import CredentialVerifyError, verify_payment_credentials

    spec = get_payment_plugin(provider)
    if not spec:
        raise ValueError(f"Unknown payment provider: {provider}")
    fields: dict[str, str] = {}
    missing: list[str] = []
    for field in spec.get("credential_fields", []):
        key = field["key"]
        val = (data.get(key) or "").strip()
        if field.get("required") and not val:
            missing.append(field.get("label") or key)
        if val:
            fields[key] = val
    if missing:
        raise ValueError(f"Required: {', '.join(missing)}")

    if preverified is not None:
        verified = preverified
        fields = preverified.get("fields") or fields
    else:
        try:
            verified = verify_payment_credentials(provider, fields)
        except CredentialVerifyError as exc:
            raise ValueError(str(exc)) from exc

    primary = (
        fields.get("secret_key")
        or fields.get("api_secret")
        or fields.get("client_secret")
        or fields.get("private_key")
        or fields.get("transaction_key")
        or fields.get("access_token")
        or fields.get("server_key")
        or fields.get("api_key")
        or fields.get("xml_password")
        or fields.get("password")
        or fields.get("admin_key")
        or fields.get("key1")
        or ""
    )
    secondary = (
        fields.get("client_id")
        or fields.get("public_key")
        or fields.get("merchant_id")
        or fields.get("publishable_key")
        or fields.get("api_login_id")
        or fields.get("merchant_code")
        or fields.get("username")
        or fields.get("partner_code")
        or fields.get("cid")
        or ""
    )
    if not primary and not secondary:
        primary = json.dumps(fields)

    external_id = (
        str(verified.get("external_id") or "").strip()
        or fields.get("merchant_id")
        or fields.get("location_id")
        or fields.get("merchant_account")
        or fields.get("merchant_code")
        or fields.get("shop_id")
        or fields.get("fps_id")
        or fields.get("partner_code")
        or fields.get("cid")
        or fields.get("store_id")
        or fields.get("promptpay_id")
        or fields.get("app_id")
        or (secondary[:32] if secondary else provider)
    )
    livemode = _infer_livemode(fields)
    meta = {
        **fields,
        "connect_mode": "api_credentials",
        "checkout_ready": spec.get("checkout_ready", False),
        "mode": "live" if livemode else "sandbox",
        "verified": True,
    }
    _store_tokens(conn, conn_id, primary, secondary, None, app)
    conn.execute(
        """UPDATE user_integration_connections
           SET external_account_id=?, status='active', updated_at=? WHERE id=?""",
        (external_id[:64], _now(), conn_id),
    )
    _upsert_payment_connection(
        conn,
        conn_id,
        provider,
        merchant_id=external_id[:64],
        account_status="active",
        charges_enabled=True,
        payouts_enabled=True,
        livemode=livemode,
        metadata=meta,
    )
    log_integration_event(conn, conn_id, "credentials.connected", "success")


def register_payment_connect_plugin(app) -> None:
    from app import current_user, db, login_required

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    @app.get("/api/integrations/payments/<provider>/oauth/start")
    @login_required
    def payment_connect_oauth_start(provider):
        provider = provider.lower()
        if provider not in PAYMENT_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown payment provider"}), 404
        cfg = _provider_config(app, provider)
        if not cfg:
            return jsonify({
                "error": f"{provider.title()} OAuth is not configured on this server. Connect with real API credentials, or set the provider OAuth env vars.",
                "env_hint": _env_hint(provider),
                "demo_available": False,
            }), 503
        user_id = uid()
        state = secrets.token_urlsafe(32)
        session[f"payment_oauth_state_{provider}"] = state
        session[f"payment_oauth_user_{provider}"] = user_id
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
        }
        if provider == "stripe":
            params["stripe_landing"] = "register"
        auth_url = f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"
        return jsonify({"auth_url": auth_url, "provider": provider})

    @app.get("/api/integrations/payments/<provider>/oauth/callback")
    def payment_connect_oauth_callback(provider):
        provider = provider.lower()
        if provider not in PAYMENT_PLUGIN_SLUGS:
            return redirect("/app/settings?integration_error=unknown_provider")
        cfg = _provider_config(app, provider)
        if not cfg:
            return redirect("/app/settings?integration_error=not_configured")
        if request.args.get("error"):
            err = urllib.parse.quote(request.args.get("error_description") or request.args.get("error"))
            return redirect(f"/app/settings?integration={provider}&integration_error={err}")
        state = request.args.get("state", "")
        if state != session.get(f"payment_oauth_state_{provider}"):
            return redirect("/app/settings?integration_error=invalid_state")
        user_id = session.get(f"payment_oauth_user_{provider}")
        if not user_id or not current_user() or int(current_user()["id"]) != int(user_id):
            return redirect(url_for("login", next=request.url))
        code = request.args.get("code")
        if not code:
            return redirect("/app/settings?integration_error=no_code")
        try:
            if provider == "stripe":
                token_data = _http_post_form(
                    cfg["token_url"],
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_secret": cfg["client_secret"],
                    },
                )
            elif provider == "paypal":
                basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
                token_data = _http_post_form(
                    cfg["token_url"],
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": cfg["redirect_uri"],
                    },
                    headers={"Authorization": f"Basic {basic}"},
                )
            else:
                token_data = _http_post_form(
                    cfg["token_url"],
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": cfg["redirect_uri"],
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                    },
                )
        except Exception as exc:
            return redirect(f"/app/settings?integration={provider}&integration_error=token_exchange_failed")
        access = token_data.get("access_token", "")
        refresh = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).replace(microsecond=0).isoformat()
        external_id = ""
        email = ""
        if provider == "stripe":
            external_id = token_data.get("stripe_user_id") or token_data.get("account_id") or ""
        with db() as conn:
            init_payment_connection_tables(conn)
            plugin = get_plugin_by_slug(conn, provider)
            if not plugin:
                return redirect("/app/settings?integration_error=plugin_missing")
            existing = conn.execute(
                "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
                (user_id, plugin["id"]),
            ).fetchone()
            sk = _secret_key(app)
            if existing:
                conn_id = existing["id"]
                _store_tokens(conn, conn_id, access, refresh, expires_at, app)
                conn.execute(
                    """UPDATE user_integration_connections
                       SET external_account_id=COALESCE(NULLIF(?, ''), external_account_id),
                           status='connected', updated_at=? WHERE id=?""",
                    (external_id, _now(), conn_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO user_integration_connections
                       (user_id, plugin_id, external_account_id, external_account_email,
                        access_token_enc, refresh_token_enc, expires_at, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'connected')""",
                    (
                        user_id,
                        plugin["id"],
                        external_id,
                        email,
                        encrypt_token(access, sk),
                        encrypt_token(refresh, sk) if refresh else "",
                        expires_at,
                    ),
                )
                conn_id = cur.lastrowid
            log_integration_event(conn, conn_id, "oauth.connected", "success")
            row = conn.execute(
                "SELECT * FROM user_integration_connections WHERE id=?", (conn_id,)
            ).fetchone()
            try:
                if provider == "stripe" and external_id:
                    acct = _refresh_stripe_account(conn, app, conn_id, external_id)
                    email = acct.get("email") or ""
                    conn.execute(
                        "UPDATE user_integration_connections SET external_account_email=? WHERE id=?",
                        (email, conn_id),
                    )
                elif provider == "paypal":
                    profile = _refresh_paypal_account(conn, app, row)
                    email = profile.get("email") or ""
                elif provider == "paypay":
                    merchant_id = token_data.get("merchant_id") or token_data.get("merchantId") or external_id
                    _upsert_payment_connection(
                        conn,
                        conn_id,
                        "paypay",
                        merchant_id=merchant_id,
                        account_status="connected",
                        charges_enabled=True,
                        livemode=cfg.get("mode") == "production",
                        metadata={"connect_mode": "oauth"},
                    )
                    conn.execute(
                        """UPDATE user_integration_connections
                           SET external_account_id=?, status='active', updated_at=? WHERE id=?""",
                        (merchant_id, _now(), conn_id),
                    )
            except Exception as exc:
                log_integration_event(conn, conn_id, "oauth.profile_sync", "error", str(exc))
        session.pop(f"payment_oauth_state_{provider}", None)
        session.pop(f"payment_oauth_user_{provider}", None)
        return redirect(f"/app/settings?integration={provider}&step=connected")

    @app.get("/api/integrations/payments/<provider>/status")
    @login_required
    def payment_connect_status(provider):
        provider = provider.lower()
        if provider not in PAYMENT_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown provider"}), 404
        user_id = uid()
        with db() as conn:
            init_payment_connection_tables(conn)
            connection = get_user_connection(conn, user_id, provider)
            conn_row = _as_dict(connection)
            if conn_row and provider == "stripe" and (
                conn_row.get("external_account_id") or conn_row.get("access_token_enc")
            ):
                try:
                    _refresh_stripe_from_connection(conn, app, conn_row)
                except Exception:
                    logging.getLogger("app.payment").error("stripe_status_refresh_failed", exc_info=True)  # SUSPECT: swallow may hide bug — see Phase 1.1
                connection = get_user_connection(conn, user_id, provider)
            elif conn_row and provider == "paypal" and conn_row.get("access_token_enc"):
                try:
                    _refresh_paypal_account(conn, app, conn_row)
                except Exception:
                    logging.getLogger("app.payment").error("paypal_status_refresh_failed", exc_info=True)  # SUSPECT: swallow may hide bug — see Phase 1.1
            payload = build_status_payload(app, conn, user_id, provider)
        return jsonify(payload)

    @app.post("/api/integrations/payments/<provider>/refresh")
    @login_required
    def payment_connect_refresh(provider):
        provider = provider.lower()
        if provider not in PAYMENT_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown provider"}), 404
        user_id = uid()
        with db() as conn:
            connection = get_user_connection(conn, user_id, provider)
            conn_row = _as_dict(connection)
            if not conn_row:
                return jsonify({"error": "Not connected"}), 404
            try:
                if provider == "stripe":
                    _refresh_stripe_from_connection(conn, app, conn_row)
                elif provider == "paypal":
                    _refresh_paypal_account(conn, app, conn_row)
                log_integration_event(conn, conn_row["id"], "account.refresh", "success")
            except Exception as exc:
                log_integration_event(conn, conn_row["id"], "account.refresh", "error", str(exc))
                return jsonify({"error": str(exc)}), 502
            payload = build_status_payload(app, conn, user_id, provider)
        return jsonify(payload)

    @app.post("/api/integrations/payments/<provider>/connect")
    @login_required
    def payment_manual_connect(provider):
        """Connect with merchant API credentials after live provider verification."""
        from integration_credential_verify import (
            CredentialVerifyError,
            assert_not_placeholder,
            verify_payment_credentials,
        )

        provider = provider.lower()
        if provider not in PAYMENT_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown provider"}), 404
        data = request.get_json(silent=True) or {}
        user_id = uid()

        try:
            # --- Phase 1: live verify BEFORE any DB write ---
            if provider == "stripe":
                secret_key = (data.get("secret_key") or data.get("api_key") or "").strip()
                publishable_key = (data.get("publishable_key") or "").strip()
                assert_not_placeholder({"secret_key": secret_key, "publishable_key": publishable_key})
                if not secret_key or not secret_key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
                    raise CredentialVerifyError(
                        "Valid Stripe secret key required (sk_test_… or sk_live_…)"
                    )
                account = _verify_stripe_secret(secret_key)
                verified = {
                    "provider": "stripe",
                    "secret_key": secret_key,
                    "publishable_key": publishable_key,
                    "external_id": account.get("id") or "",
                    "email": account.get("email") or "",
                    "charges_enabled": bool(account.get("charges_enabled")),
                    "payouts_enabled": bool(account.get("payouts_enabled")),
                    "livemode": secret_key.startswith(("sk_live_", "rk_live_")),
                    "account": account,
                }
            elif provider == "paypal":
                client_id = (data.get("client_id") or "").strip()
                client_secret = (data.get("client_secret") or "").strip()
                mode = (data.get("mode") or os.environ.get("PAYPAL_MODE") or "live").strip().lower()
                assert_not_placeholder({"client_id": client_id, "client_secret": client_secret})
                if not client_id or not client_secret:
                    raise CredentialVerifyError("client_id and client_secret are required")
                _verify_paypal_credentials(client_id, client_secret, mode)
                verified = {
                    "provider": "paypal",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "mode": mode,
                    "external_id": client_id[:24],
                    "livemode": mode == "live",
                }
            else:
                spec = get_payment_plugin(provider)
                if not spec:
                    raise CredentialVerifyError(f"Unknown payment provider: {provider}")
                fields: dict[str, str] = {}
                missing: list[str] = []
                for field in spec.get("credential_fields", []):
                    key = field["key"]
                    val = (data.get(key) or "").strip()
                    if field.get("required") and not val:
                        missing.append(field.get("label") or key)
                    if val:
                        fields[key] = val
                if missing:
                    raise CredentialVerifyError(f"Required: {', '.join(missing)}")
                result = verify_payment_credentials(provider, fields)
                verified = {"provider": provider, "fields": fields, **result}

            # --- Phase 2: persist only after verify succeeded ---
            with db() as conn:
                init_payment_connection_tables(conn)
                conn_id, _ = _ensure_plugin_connection(conn, user_id, provider)

                if provider == "stripe":
                    _store_tokens(
                        conn, conn_id, verified["secret_key"], verified["publishable_key"], None, app
                    )
                    charges = verified["charges_enabled"]
                    conn.execute(
                        """UPDATE user_integration_connections
                           SET external_account_id=?, external_account_email=?, status=?, updated_at=?
                           WHERE id=?""",
                        (
                            verified["external_id"],
                            verified["email"],
                            "active" if charges else "connected",
                            _now(),
                            conn_id,
                        ),
                    )
                    _upsert_payment_connection(
                        conn,
                        conn_id,
                        "stripe",
                        merchant_id=verified["external_id"],
                        account_status="active" if charges else "pending",
                        charges_enabled=charges,
                        payouts_enabled=verified["payouts_enabled"],
                        livemode=verified["livemode"],
                        metadata={
                            "connect_mode": "api_credentials",
                            "publishable_key": verified["publishable_key"],
                            "verified": True,
                        },
                    )
                elif provider == "paypal":
                    _store_tokens(
                        conn, conn_id, verified["client_id"], verified["client_secret"], None, app
                    )
                    conn.execute(
                        """UPDATE user_integration_connections
                           SET external_account_id=?, status='active', updated_at=? WHERE id=?""",
                        (verified["external_id"], _now(), conn_id),
                    )
                    _upsert_payment_connection(
                        conn,
                        conn_id,
                        "paypal",
                        merchant_id=verified["external_id"],
                        account_status="active",
                        charges_enabled=True,
                        payouts_enabled=True,
                        livemode=verified["livemode"],
                        metadata={
                            "connect_mode": "api_credentials",
                            "mode": verified["mode"],
                            "verified": True,
                        },
                    )
                else:
                    _connect_generic_payment_credentials(
                        conn,
                        app,
                        conn_id=conn_id,
                        provider=provider,
                        data=data,
                        preverified=verified,
                    )

                log_integration_event(conn, conn_id, "credentials.connected", "success")
                payload = build_status_payload(app, conn, user_id, provider)
        except (CredentialVerifyError, urllib.error.HTTPError, ValueError, RuntimeError) as exc:
            _rollback_request_db()
            if isinstance(exc, urllib.error.HTTPError):
                detail = exc.read().decode() if exc.fp else str(exc)
                return jsonify({"error": f"Could not verify credentials: {detail[:200]}"}), 400
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            _rollback_request_db()
            return jsonify({"error": str(exc)}), 400

        return jsonify({"ok": True, **payload})

    @app.post("/api/integrations/payments/paypay/connect")
    @login_required
    def paypay_manual_connect():
        """Legacy alias for PayPay credential connect."""
        return payment_manual_connect("paypay")

    @app.post("/api/integrations/payments/<provider>/disconnect")
    @login_required
    def payment_connect_disconnect(provider):
        provider = provider.lower()
        if provider not in PAYMENT_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown provider"}), 404
        user_id = uid()
        with db() as conn:
            connection = get_user_connection(conn, user_id, provider)
            if not connection:
                return jsonify({"ok": True})
            conn.execute("DELETE FROM payment_connections WHERE connection_id=?", (connection["id"],))
            conn.execute(
                """UPDATE user_integration_connections
                   SET access_token_enc='', refresh_token_enc='', expires_at=NULL,
                       external_account_id='', external_account_email='',
                       status='disconnected', updated_at=?
                   WHERE id=? AND user_id=?""",
                (_now(), connection["id"], user_id),
            )
            log_integration_event(conn, connection["id"], "oauth.disconnected", "success")
        return jsonify({"ok": True})

    @app.get("/api/integrations/payments/config")
    @login_required
    def payment_connect_config():
        """Which payment providers are server-configured (no secrets exposed)."""
        return jsonify({
            "demo_available": False,
            "providers": {
                slug: {
                    "configured": provider_configured(app, slug),
                    "oauth_available": provider_configured(app, slug),
                    "credentials_available": True,
                    "demo_available": False,
                    "connect_modes": _payment_connect_modes(app, slug),
                    "env_hint": _env_hint(slug),
                }
                for slug in PAYMENT_PLUGIN_SLUGS
            },
        })

    app.init_payment_connection_tables = init_payment_connection_tables
    with app.app_context():
        try:
            from app import db as app_db
            with app_db() as conn:
                init_payment_connection_tables(conn)
                n = _purge_fake_integration_connections(conn)
                if n:
                    app.logger.info("payment_integration_purge count=%d", n)
        except Exception as exc:
            _log.warning("payment_integration_purge_skipped error=%s", type(exc).__name__)


def _payment_connect_modes(app, slug: str) -> list[str]:
    modes = ["credentials"]
    if provider_configured(app, slug):
        modes.append("oauth")
    return modes


def merchant_paypal_credentials(conn, app, owner_id: int) -> tuple[str, str, str, dict]:
    """Merchant PayPal REST app credentials (client_id, client_secret, mode, meta)."""
    row = get_user_connection(conn, owner_id, "paypal")
    if not row:
        raise RuntimeError("PayPal is not connected for this store")
    pay = _get_payment_connection(conn, row["id"])
    meta: dict = {}
    if pay:
        try:
            meta = json.loads(pay["metadata_json"] or "{}")
        except json.JSONDecodeError:
            meta = {}
    mode = (meta.get("mode") or os.environ.get("PAYPAL_MODE") or "live").strip().lower()
    connect_mode = meta.get("connect_mode") or "oauth"
    if connect_mode == "demo":
        raise RuntimeError("Demo PayPal cannot accept real payments")
    if connect_mode != "api_credentials":
        raise RuntimeError("PayPal checkout requires your REST app Client ID and Secret in Settings")
    sk = _secret_key(app)
    client_id = decrypt_token(row["access_token_enc"], sk)
    client_secret = decrypt_token(row["refresh_token_enc"], sk)
    if not client_id or not client_secret:
        raise RuntimeError("PayPal credentials missing — reconnect in Settings")
    return client_id, client_secret, mode, meta


def paypal_api_base(mode: str) -> str:
    return PAYPAL_API_LIVE if mode == "live" else PAYPAL_API_SANDBOX


def paypal_access_token(client_id: str, client_secret: str, mode: str) -> str:
    token_data = _verify_paypal_credentials(client_id, client_secret, mode)
    access = token_data.get("access_token", "")
    if not access:
        raise RuntimeError("PayPal authentication failed")
    return access


def paypal_create_checkout_order(
    client_id: str,
    client_secret: str,
    mode: str,
    *,
    amount: float,
    currency: str,
    return_url: str,
    cancel_url: str,
    reference_id: str,
    brand_name: str = "Store",
) -> dict:
    access = paypal_access_token(client_id, client_secret, mode)
    api = paypal_api_base(mode)
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference_id[:127],
                "amount": {
                    "currency_code": currency.upper(),
                    "value": f"{amount:.2f}",
                },
            }
        ],
        "application_context": {
            "return_url": return_url,
            "cancel_url": cancel_url,
            "brand_name": brand_name[:127],
            "user_action": "PAY_NOW",
        },
    }
    return _http_post_json(
        f"{api}/v2/checkout/orders",
        payload,
        headers={"Authorization": f"Bearer {access}"},
    )


def paypal_capture_checkout_order(
    client_id: str,
    client_secret: str,
    mode: str,
    order_id: str,
) -> dict:
    access = paypal_access_token(client_id, client_secret, mode)
    api = paypal_api_base(mode)
    return _http_post_json(
        f"{api}/v2/checkout/orders/{urllib.parse.quote(order_id)}/capture",
        {},
        headers={"Authorization": f"Bearer {access}"},
    )


def _env_hint(provider: str) -> str:
    hints = {
        "stripe": "Paste your Stripe secret key from dashboard.stripe.com/apikeys — no platform setup needed",
        "paypal": "Paste your PayPal REST app Client ID + Secret from developer.paypal.com — no platform setup needed",
        "paypay": "Paste your PayPay merchant API credentials from the PayPay merchant portal",
    }
    return hints.get(provider, "")
