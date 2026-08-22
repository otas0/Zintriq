"""Reputation Connect — business-owner OAuth account linking for review platforms."""

from __future__ import annotations

import base64
import json
import os
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import abort, jsonify, redirect, request, session, url_for

from bos.integration_crypto import encrypt_token
from integration_catalog import get_reputation_plugin, reputation_plugin_slugs
from feedback_reputation_plugins import REPUTATION_PLUGIN_SLUGS
from integration_platform import get_plugin_by_slug, get_user_connection, log_integration_event

OAUTH_CONFIG = {
    "yelp": {
        "auth_url": "https://biz.yelp.com/oauth2/authorize",
        "token_url": "https://api.yelp.com/oauth2/token",
        "scope": "business",
        "client_id_env": "YELP_CLIENT_ID",
        "client_secret_env": "YELP_CLIENT_SECRET",
        "redirect_env": "YELP_OAUTH_REDIRECT_URI",
    },
    "tripadvisor": {
        "auth_url": "https://api.tripadvisor.com/oauth2/authorize",
        "token_url": "https://api.tripadvisor.com/oauth2/token",
        "scope": "reviews_read",
        "client_id_env": "TRIPADVISOR_CLIENT_ID",
        "client_secret_env": "TRIPADVISOR_CLIENT_SECRET",
        "redirect_env": "TRIPADVISOR_OAUTH_REDIRECT_URI",
    },
    "tablelog": {
        "auth_url": "https://api.tabelog.com/oauth/authorize",
        "token_url": "https://api.tabelog.com/oauth/token",
        "scope": "reviews",
        "client_id_env": "TABLELOG_CLIENT_ID",
        "client_secret_env": "TABLELOG_CLIENT_SECRET",
        "redirect_env": "TABLELOG_OAUTH_REDIRECT_URI",
    },
    "opentable": {
        "auth_url": "https://oauth.opentable.com/authorize",
        "token_url": "https://oauth.opentable.com/token",
        "scope": "reviews_read",
        "client_id_env": "OPENTABLE_CLIENT_ID",
        "client_secret_env": "OPENTABLE_CLIENT_SECRET",
        "redirect_env": "OPENTABLE_OAUTH_REDIRECT_URI",
    },
    "google_reviews": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/business.manage",
        "client_id_env": "GOOGLE_REVIEWS_CLIENT_ID",
        "client_secret_env": "GOOGLE_REVIEWS_CLIENT_SECRET",
        "redirect_env": "GOOGLE_REVIEWS_OAUTH_REDIRECT_URI",
        "extra_auth_params": {"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
        "token_in_body": True,
        "profile": "google_business",
    },
    "google_customer_reviews": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/content",
        "client_id_env": "GOOGLE_MERCHANT_CLIENT_ID",
        "client_secret_env": "GOOGLE_MERCHANT_CLIENT_SECRET",
        "redirect_env": "GOOGLE_MERCHANT_OAUTH_REDIRECT_URI",
        "extra_auth_params": {"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
        "token_in_body": True,
        "profile": "google_merchant",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _secret_key(app) -> str:
    return app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY", "")


def _demo_connect_allowed(app) -> bool:
    """Demo connect permanently disabled — real credentials only."""
    return False


def _redirect_uri(app, provider: str, env_key: str) -> str:
    explicit = os.environ.get(env_key, "").strip()
    if explicit:
        return explicit
    try:
        return url_for("reputation_oauth_callback", provider=provider, _external=True)
    except RuntimeError:
        base = (os.environ.get("PUBLIC_BASE_URL") or "http://127.0.0.1:5001").rstrip("/")
        return f"{base}/api/integrations/reputation/{provider}/oauth/callback"


def _provider_config(app, slug: str) -> dict | None:
    slug = slug.lower()
    spec = OAUTH_CONFIG.get(slug)
    if not spec:
        return None
    client_id = os.environ.get(spec["client_id_env"], "").strip()
    client_secret = os.environ.get(spec["client_secret_env"], "").strip()
    if not client_id or not client_secret:
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_url": spec["auth_url"],
        "token_url": spec["token_url"],
        "scope": spec["scope"],
        "redirect_uri": _redirect_uri(app, slug, spec["redirect_env"]),
        "extra_auth_params": spec.get("extra_auth_params") or {},
        "token_in_body": bool(spec.get("token_in_body")),
        "profile": spec.get("profile") or "",
    }


def provider_configured(app, slug: str) -> bool:
    return _provider_config(app, slug) is not None


def _http_get_json(url: str, access_token: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def _google_profile(access: str, kind: str) -> tuple[str, str, str]:
    if kind == "google_merchant":
        data = _http_get_json("https://shoppingcontent.googleapis.com/content/v2.1/accounts/authinfo", access)
        ids = data.get("accountIdentifiers") or []
        first = ids[0] if ids else {}
        mid = str(first.get("merchantId") or first.get("aggregatorId") or "")
        return mid, "", "Google Merchant Center"
    data = _http_get_json("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", access)
    accounts = data.get("accounts") or []
    first = accounts[0] if accounts else {}
    name = first.get("accountName") or first.get("name") or "Google Business Profile"
    account_id = first.get("name") or first.get("accountName") or ""
    return account_id, first.get("email") or "", name


def _http_post_form(url: str, data: dict, *, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode({k: v for k, v in data.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def _store_oauth_connection(
    conn,
    app,
    *,
    user_id: int,
    slug: str,
    access: str,
    refresh: str,
    expires_at: str | None,
    external_id: str,
    email: str,
    business_name: str,
    connect_mode: str,
) -> int:
    plugin = get_plugin_by_slug(conn, slug)
    if not plugin:
        raise RuntimeError(f"{slug} plugin not registered")
    sk = _secret_key(app)
    existing = conn.execute(
        "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
        (user_id, plugin["id"]),
    ).fetchone()
    meta = json.dumps({"connect_mode": connect_mode, "business_name": business_name})
    if existing:
        conn_id = int(existing["id"])
        conn.execute(
            """UPDATE user_integration_connections
               SET external_account_id=?, external_account_email=?,
                   access_token_enc=?, refresh_token_enc=?, expires_at=?,
                   status='connected', updated_at=? WHERE id=?""",
            (
                external_id,
                email,
                encrypt_token(access, sk),
                encrypt_token(refresh, sk) if refresh else "",
                expires_at,
                _now(),
                conn_id,
            ),
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
        conn_id = int(cur.lastrowid)
    log_integration_event(conn, conn_id, "reputation.oauth.connected", "success", meta)
    return conn_id


def reputation_status_payload(conn, app, user_id: int, slug: str) -> dict:
    row = get_user_connection(conn, user_id, slug)
    if not row:
        return {
            "connected": False,
            "status": "not_connected",
            "demo_available": False,
            "oauth_available": provider_configured(app, slug),
        }
    logs = conn.execute(
        """SELECT event_type, status, error_message, created_at
           FROM integration_event_logs WHERE connection_id=?
           ORDER BY created_at DESC LIMIT 12""",
        (row["id"],),
    ).fetchall()
    return {
        "connected": row["status"] in ("connected", "active", "installed"),
        "status": row["status"] or "connected",
        "external_account_id": row["external_account_id"],
        "external_account_email": row["external_account_email"],
        "demo_available": False,
        "oauth_available": provider_configured(app, slug),
        "recent_logs": [dict(l) for l in logs],
    }


def register_reputation_connect_plugin(app) -> None:
    from app import current_user, db, login_required

    def uid():
        user = current_user()
        if not user:
            abort(401)
        return int(user["id"])

    @app.get("/api/integrations/reputation/<provider>/oauth/start")
    @login_required
    def reputation_oauth_start(provider):
        provider = provider.lower()
        if provider not in REPUTATION_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown review platform"}), 404
        user_id = uid()
        cfg = _provider_config(app, provider)
        state = secrets.token_urlsafe(32)
        session[f"rep_oauth_state_{provider}"] = state
        session[f"rep_oauth_user_{provider}"] = user_id
        if not cfg:
            return jsonify({
                "error": f"{provider.title()} OAuth is not configured on this server. Use credential connect with a real API key where supported, or configure OAuth env vars.",
                "demo_available": False,
            }), 503
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": cfg["scope"],
            "state": state,
            **(cfg.get("extra_auth_params") or {}),
        }
        auth_url = f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"
        return jsonify({"auth_url": auth_url, "provider": provider})

    @app.get("/api/integrations/reputation/<provider>/oauth/callback")
    def reputation_oauth_callback(provider):
        provider = provider.lower()
        if provider not in REPUTATION_PLUGIN_SLUGS:
            return redirect("/app/settings?integration_error=unknown_provider")
        state = request.args.get("state", "")
        if state != session.get(f"rep_oauth_state_{provider}"):
            return redirect("/app/settings?integration_error=invalid_state")
        user_id = session.get(f"rep_oauth_user_{provider}")
        if not user_id or not current_user() or int(current_user()["id"]) != int(user_id):
            return redirect(url_for("login", next=request.url))
        code = request.args.get("code")
        if not code:
            return redirect("/app/settings?integration_error=no_code")
        try:
            if code == "__demo__":
                return redirect("/app/settings?integration_error=demo_disabled")
            cfg = _provider_config(app, provider)
            if not cfg:
                return redirect("/app/settings?integration_error=not_configured")
            token_body = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
            }
            headers = {}
            if cfg.get("token_in_body"):
                token_body["client_id"] = cfg["client_id"]
                token_body["client_secret"] = cfg["client_secret"]
            else:
                basic = base64.b64encode(
                    f"{cfg['client_id']}:{cfg['client_secret']}".encode()
                ).decode()
                headers["Authorization"] = f"Basic {basic}"
            token_data = _http_post_form(cfg["token_url"], token_body, headers=headers or None)
            access = token_data.get("access_token", "")
            refresh = token_data.get("refresh_token", "")
            expires_in = int(token_data.get("expires_in", 3600))
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).replace(microsecond=0).isoformat()
            external_id = token_data.get("business_id") or token_data.get("account_id") or ""
            email = token_data.get("email") or ""
            business_name = token_data.get("business_name") or provider.title()
            if cfg.get("profile") and access:
                try:
                    external_id, email, business_name = _google_profile(access, cfg["profile"])
                except Exception:
                    pass
            with db() as conn:
                _store_oauth_connection(
                    conn,
                    app,
                    user_id=int(user_id),
                    slug=provider,
                    access=access,
                    refresh=refresh,
                    expires_at=expires_at,
                    external_id=external_id,
                    email=email,
                    business_name=business_name,
                    connect_mode="oauth",
                )
        except Exception:
            return redirect(f"/app/settings?integration={provider}&integration_error=token_exchange_failed")
        session.pop(f"rep_oauth_state_{provider}", None)
        session.pop(f"rep_oauth_user_{provider}", None)
        return redirect(f"/app/settings?integration={provider}&step=connected")

    @app.post("/api/integrations/reputation/<provider>/connect")
    @login_required
    def reputation_credential_connect(provider):
        """Connect review platform only after live provider verification."""
        from payment_connect_plugin import _rollback_request_db
        from integration_credential_verify import CredentialVerifyError, verify_reputation_credentials

        provider = provider.lower()
        if provider not in REPUTATION_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown review platform"}), 404
        spec = get_reputation_plugin(provider)
        if not spec:
            return jsonify({"error": "Unknown review platform"}), 404
        if spec.get("oauth_required") and provider == "google_reviews":
            return jsonify({
                "error": "Google Reviews must be connected with Google Business Profile OAuth — a listing ID is not accepted.",
            }), 400
        data = request.get_json(silent=True) or {}
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
            return jsonify({"error": f"Required: {', '.join(missing)}"}), 400

        try:
            verified = verify_reputation_credentials(provider, fields)
        except CredentialVerifyError as exc:
            _rollback_request_db()
            return jsonify({"error": str(exc)}), 400

        business_id = (
            str(verified.get("external_id") or "").strip()
            or fields.get("business_id")
            or fields.get("business_unit_id")
            or fields.get("hotel_id")
            or fields.get("venue_id")
            or fields.get("page_id")
            or fields.get("store_id")
            or fields.get("property_id")
            or fields.get("merchant_identifier")
            or fields.get("tsid")
            or fields.get("merchant_id")
            or next(iter(fields.values()), provider)
        )
        api_key = (
            fields.get("api_key")
            or fields.get("access_token")
            or fields.get("client_secret")
            or ""
        )
        user_id = uid()
        try:
            with db() as conn:
                plugin = get_plugin_by_slug(conn, provider)
                if not plugin:
                    raise RuntimeError("Plugin not registered")
                existing = conn.execute(
                    "SELECT id FROM user_integration_connections WHERE user_id=? AND plugin_id=?",
                    (user_id, plugin["id"]),
                ).fetchone()
                sk = _secret_key(app)
                meta = json.dumps({
                    **fields,
                    "connect_mode": "api_credentials",
                    "verified": True,
                    "business_name": verified.get("business_name") or "",
                })
                if existing:
                    conn_id = int(existing["id"])
                    conn.execute(
                        """UPDATE user_integration_connections
                           SET external_account_id=?, access_token_enc=?, refresh_token_enc='',
                               status='connected', updated_at=? WHERE id=?""",
                        (
                            business_id[:128],
                            encrypt_token(api_key or business_id, sk),
                            _now(),
                            conn_id,
                        ),
                    )
                else:
                    cur = conn.execute(
                        """INSERT INTO user_integration_connections
                           (user_id, plugin_id, external_account_id, access_token_enc, status)
                           VALUES (?, ?, ?, ?, 'connected')""",
                        (user_id, plugin["id"], business_id[:128], encrypt_token(api_key or business_id, sk)),
                    )
                    conn_id = int(cur.lastrowid)
                log_integration_event(conn, conn_id, "reputation.credentials.connected", "success", meta)
        except Exception as exc:
            _rollback_request_db()
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "provider": provider, "connected": True})

    @app.get("/api/integrations/reputation/<provider>/status")
    @login_required
    def reputation_connect_status(provider):
        provider = provider.lower()
        if provider not in REPUTATION_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown review platform"}), 404
        with db() as conn:
            payload = reputation_status_payload(conn, app, uid(), provider)
        return jsonify(payload)

    @app.post("/api/integrations/reputation/<provider>/disconnect")
    @login_required
    def reputation_connect_disconnect(provider):
        provider = provider.lower()
        if provider not in REPUTATION_PLUGIN_SLUGS:
            return jsonify({"error": "Unknown review platform"}), 404
        with db() as conn:
            connection = get_user_connection(conn, uid(), provider)
            if not connection:
                return jsonify({"ok": True})
            conn.execute(
                """UPDATE user_integration_connections
                   SET status='disconnected', access_token_enc='', refresh_token_enc='',
                       updated_at=? WHERE id=?""",
                (_now(), connection["id"]),
            )
            log_integration_event(conn, connection["id"], "reputation.oauth.disconnected", "success")
        return jsonify({"ok": True})

    @app.get("/api/integrations/reputation/config")
    @login_required
    def reputation_connect_config():
        return jsonify({
            "demo_available": False,
            "providers": {
                slug: {
                    "oauth_available": provider_configured(app, slug),
                    "demo_available": False,
                    "connect_modes": (
                        (["oauth"] if slug in OAUTH_CONFIG and provider_configured(app, slug) else [])
                        + (["credentials"] if (get_reputation_plugin(slug) or {}).get("credential_fields") else [])
                    ),
                }
                for slug in REPUTATION_PLUGIN_SLUGS
            },
        })
