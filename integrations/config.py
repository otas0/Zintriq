"""Zintriq — Integration layer configuration (environment-driven)."""

from __future__ import annotations

import os


def auth_provider_name() -> str:
    return (os.environ.get("AUTH_PROVIDER") or "local").strip().lower()


def payment_provider_name() -> str:
    return (os.environ.get("PAYMENT_PROVIDER") or "none").strip().lower()


def email_provider_name() -> str:
    return (os.environ.get("EMAIL_PROVIDER") or "none").strip().lower()


def calendar_provider_name() -> str:
    # Local / CalDAV only — Google Calendar is not offered.
    return (os.environ.get("CALENDAR_PROVIDER") or "none").strip().lower()


def auth_configured() -> bool:
    provider = auth_provider_name()
    if provider == "auth0":
        return bool(
            os.environ.get("AUTH0_DOMAIN")
            and os.environ.get("AUTH0_CLIENT_ID")
            and os.environ.get("AUTH0_CLIENT_SECRET")
            and os.environ.get("AUTH0_CALLBACK_URL")
        )
    if provider in ("clerk", "supabase"):
        return bool(os.environ.get("AUTH_PROVIDER_KEY") or os.environ.get(f"{provider.upper()}_CLIENT_ID"))
    return provider == "local"


def payment_configured() -> bool:
    provider = payment_provider_name()
    if provider in ("none", ""):
        return False
    if provider == "stripe":
        return bool(os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("PAYMENT_PROVIDER_KEY"))
    return bool(os.environ.get("PAYMENT_PROVIDER_KEY"))


def email_configured() -> bool:
    provider = email_provider_name()
    if provider in ("none", ""):
        return False
    return bool(os.environ.get("EMAIL_PROVIDER_KEY") or os.environ.get("SMTP_HOST"))


def integration_status() -> dict:
    """Public integration readiness — never exposes secrets."""
    return {
        "auth": {
            "provider": auth_provider_name(),
            "configured": auth_configured(),
        },
        "payment": {
            "provider": payment_provider_name(),
            "configured": payment_configured(),
        },
        "email": {
            "provider": email_provider_name(),
            "configured": email_configured(),
        },
        "calendar": {
            "provider": calendar_provider_name(),
            "configured": calendar_provider_name() in ("caldav", "local")
            and bool(os.environ.get("CALENDAR_PROVIDER_KEY") or os.environ.get("CALDAV_URL")),
        },
    }
