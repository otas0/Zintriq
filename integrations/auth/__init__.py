"""Auth provider abstraction — external authentication, internal UserProfile."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


class AuthProvider(ABC):
    slug: str = "base"

    @abstractmethod
    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify provider token; return normalized claims."""

    @abstractmethod
    def is_configured(self) -> bool:
        pass

    def normalized_claims(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "auth_provider": self.slug,
            "auth_provider_id": raw.get("uid") or raw.get("sub") or raw.get("id"),
            "email": (raw.get("email") or "").strip().lower(),
            "email_verified": bool(raw.get("email_verified", True)),
            "full_name": raw.get("name") or raw.get("full_name") or "",
        }


class LocalAuthProvider(AuthProvider):
    """Session/password auth — profile keyed by user id."""

    slug = "local"

    def verify_token(self, token: str) -> dict[str, Any]:
        raise NotImplementedError("Local auth uses session login, not bearer tokens")

    def is_configured(self) -> bool:
        return True


def auth_provider_name() -> str:
    return (os.environ.get("AUTH_PROVIDER") or "local").strip().lower()


def get_auth_provider(name: str | None = None) -> AuthProvider:
    chosen = (name or auth_provider_name()).strip().lower()
    if chosen == "auth0":
        from integrations.auth.auth0_provider import Auth0AuthProvider

        return Auth0AuthProvider()
    return LocalAuthProvider()


def auth0_enabled() -> bool:
    if auth_provider_name() != "auth0":
        return False
    return get_auth_provider("auth0").is_configured()
