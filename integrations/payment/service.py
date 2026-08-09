"""PaymentService — provider-agnostic billing preparation."""

from __future__ import annotations

from integrations.payment import get_payment_provider
from integrations.subscription import (
    ensure_workspace_subscription,
    get_workspace_subscription,
    update_subscription_from_provider,
)


class PaymentService:
    @staticmethod
    def provider():
        return get_payment_provider()

    @staticmethod
    def subscription(conn, workspace_id: int) -> dict:
        return ensure_workspace_subscription(conn, workspace_id)

    @staticmethod
    def create_customer(conn, workspace_id: int, *, email: str, name: str = "") -> dict:
        provider = get_payment_provider()
        if not provider.is_configured():
            raise RuntimeError("Payment provider is not configured")
        result = provider.create_customer(workspace_id=workspace_id, email=email, name=name)
        sub = update_subscription_from_provider(
            conn,
            workspace_id,
            provider=provider.slug,
            provider_customer_id=result.get("provider_customer_id"),
        )
        return {"subscription": sub, "provider": provider.slug}

    @staticmethod
    def apply_webhook_event(conn, event: dict) -> dict | None:
        ws_id = event.get("workspace_id")
        if not ws_id:
            return None
        return update_subscription_from_provider(
            conn,
            int(ws_id),
            provider=event.get("provider") or get_payment_provider().slug,
            provider_customer_id=event.get("provider_customer_id"),
            provider_subscription_id=event.get("provider_subscription_id"),
            plan=event.get("plan"),
            status=event.get("status"),
            current_period_end=str(event["current_period_end"]) if event.get("current_period_end") else None,
        )

    @staticmethod
    def is_active(conn, workspace_id: int) -> bool:
        sub = get_workspace_subscription(conn, workspace_id)
        if not sub:
            return True  # free tier default
        return sub["status"] in ("active", "trialing") or sub["plan"] == "free"
