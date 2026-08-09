"""Auth service — resolves external provider, maintains UserProfile."""

from __future__ import annotations

from integrations.auth import get_auth_provider
from integrations.user_profile import get_user_profile, upsert_user_profile


class AuthService:
    @staticmethod
    def provider():
        return get_auth_provider()

    @staticmethod
    def verify_id_token(token: str) -> dict:
        provider = get_auth_provider()
        if not provider.is_configured() and provider.slug != "local":
            raise RuntimeError(f"Auth provider {provider.slug} is not configured")
        return provider.verify_token(token)

    @staticmethod
    def link_user(conn, user_id: int, claims: dict) -> dict:
        upsert_user_profile(
            conn,
            user_id,
            auth_provider=claims.get("auth_provider") or get_auth_provider().slug,
            auth_provider_id=claims.get("auth_provider_id"),
            email=claims["email"],
            full_name=claims.get("full_name"),
        )
        return get_user_profile(conn, user_id)

    @staticmethod
    def profile(conn, user_id: int) -> dict | None:
        return get_user_profile(conn, user_id)
