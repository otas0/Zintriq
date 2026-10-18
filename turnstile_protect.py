"""Cloudflare Turnstile — bot protection for auth forms (not Google reCAPTCHA)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

_log = logging.getLogger("app.auth")

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_site_key() -> str:
    return (os.environ.get("TURNSTILE_SITE_KEY") or "").strip()


def turnstile_secret_key() -> str:
    return (os.environ.get("TURNSTILE_SECRET_KEY") or "").strip()


def turnstile_configured() -> bool:
    return bool(turnstile_site_key() and turnstile_secret_key())


def turnstile_required() -> bool:
    """Enforce when keys are set, or when TURNSTILE_REQUIRED=1 in production."""
    if turnstile_configured():
        return True
    return (os.environ.get("TURNSTILE_REQUIRED") or "").strip().lower() in ("1", "true", "yes")


FAIL_MESSAGE = "Please complete the security check and try again."


def extract_turnstile_token() -> str:
    from flask import request

    payload = request.get_json(silent=True) or {}
    return (
        request.form.get("cf-turnstile-response")
        or payload.get("cf-turnstile-response")
        or request.headers.get("CF-Turnstile-Response")
        or ""
    ).strip()


def client_ip() -> str | None:
    from flask import request

    return (request.headers.get("CF-Connecting-IP") or request.remote_addr or "").strip() or None


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    secret = turnstile_secret_key()
    if not secret:
        # Misconfigured require → fail closed; unconfigured → allow (local dev)
        return not turnstile_required()
    token = (token or "").strip()
    if not token:
        return False
    body = {"secret": secret, "response": token}
    if remote_ip:
        body["remoteip"] = remote_ip
    data = urllib.parse.urlencode(body).encode()
    req = urllib.request.Request(
        VERIFY_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
        return bool(payload.get("success"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        _log.warning("turnstile_verify_failed error=%s", str(exc)[:120])
        return False


def request_passes_turnstile() -> bool:
    """True when Turnstile is off (local) or the submitted token verifies."""
    if not turnstile_configured() and not turnstile_required():
        return True
    return verify_turnstile(extract_turnstile_token(), client_ip())
