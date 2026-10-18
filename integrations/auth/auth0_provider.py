"""Auth0 (Okta) OIDC provider — Universal Login + JWT validation."""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from integrations.auth import AuthProvider


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


class Auth0AuthProvider(AuthProvider):
    slug = "auth0"

    def __init__(self) -> None:
        self.domain = _env("AUTH0_DOMAIN").rstrip("/")
        self.client_id = _env("AUTH0_CLIENT_ID")
        self.client_secret = _env("AUTH0_CLIENT_SECRET")
        self.audience = _env("AUTH0_AUDIENCE")
        self.callback_url = _env("AUTH0_CALLBACK_URL")
        self.logout_return_to = _env("AUTH0_LOGOUT_RETURN_TO") or _env("PUBLIC_BASE_URL") or "/"

    def is_configured(self) -> bool:
        return bool(self.domain and self.client_id and self.client_secret and self.callback_url)

    @property
    def issuer(self) -> str:
        d = self.domain
        if not d.startswith("http"):
            d = f"https://{d}"
        return d.rstrip("/") + "/"

    def authorize_url(self, *, state: str, screen_hint: str | None = None) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.callback_url,
            "scope": "openid profile email",
            "state": state,
        }
        if self.audience:
            params["audience"] = self.audience
        if screen_hint:
            params["screen_hint"] = screen_hint
        return f"{self.issuer}authorize?{urllib.parse.urlencode(params)}"

    def logout_url(self) -> str:
        params = {
            "client_id": self.client_id,
            "returnTo": self.logout_return_to,
        }
        return f"{self.issuer}v2/logout?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        token_url = f"{self.issuer}oauth/token"
        body = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.callback_url,
            }
        ).encode()
        req = urllib.request.Request(
            token_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())

    def exchange_code_pkce(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Native/desktop Authorization Code + PKCE (no client_secret)."""
        token_url = f"{self.issuer}oauth/token"
        cid = (client_id or _env("AUTH0_NATIVE_CLIENT_ID") or self.client_id).strip()
        payload = {
            "grant_type": "authorization_code",
            "client_id": cid,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
        }
        body = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(
            token_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:240]
            raise ValueError(f"Auth0 PKCE exchange failed ({exc.code}): {detail}") from exc

    def userinfo(self, access_token: str) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.issuer}userinfo",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())

    def verify_token(self, token: str) -> dict[str, Any]:
        """Validate Auth0 access/id token via userinfo (network) or decode id_token claims lightly.

        Production hardening: prefer JWKS verification (PyJWT). Here we call /userinfo with the
        access token when available; for id_token-only flows callers should pass access_token.
        """
        try:
            info = self.userinfo(token)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Auth0 token rejected: {exc.code}") from exc
        return self.normalized_claims(
            {
                "sub": info.get("sub"),
                "email": info.get("email"),
                "email_verified": info.get("email_verified", False),
                "name": info.get("name") or info.get("nickname") or "",
            }
        )

    def claims_from_token_response(self, token_data: dict[str, Any]) -> dict[str, Any]:
        access = token_data.get("access_token") or ""
        if access:
            return self.verify_token(access)
        # Fallback: decode id_token payload without verify (dev only) — still require sub+email
        id_token = token_data.get("id_token") or ""
        if not id_token or id_token.count(".") != 2:
            raise ValueError("Auth0 response missing usable tokens")
        import base64

        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        allowed = {c for c in (self.client_id, _env("AUTH0_NATIVE_CLIENT_ID")) if c}
        aud = data.get("aud")
        aud_ok = (isinstance(aud, str) and aud in allowed) or (
            isinstance(aud, list) and any(a in allowed for a in aud)
        )
        if allowed and not aud_ok:
            raise ValueError("Auth0 id_token audience mismatch")
        return self.normalized_claims(data)


def new_oauth_state() -> str:
    return secrets.token_urlsafe(24)
