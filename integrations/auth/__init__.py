"""Auth provider abstraction — external authentication, internal UserProfile."""

from __future__ import annotations

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
    """Placeholder for session/password auth — profile keyed by user id."""

    slug = "local"

    def verify_token(self, token: str) -> dict[str, Any]:
        raise NotImplementedError("Local auth uses session login, not bearer tokens")

    def is_configured(self) -> bool:
        return True


def get_auth_provider(name: str | None = None) -> AuthProvider:
    return LocalAuthProvider()
