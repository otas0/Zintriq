"""Payment provider abstraction — no card storage, external billing only."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any

from observability.trace import trace

_log = logging.getLogger("app.payment")


class PaymentProvider(ABC):
    slug: str = "none"

    @abstractmethod
    def is_configured(self) -> bool:
        pass

    @abstractmethod
    def create_customer(self, *, workspace_id: int, email: str, name: str = "") -> dict[str, Any]:
        """Create external customer; returns {provider_customer_id, ...}."""

    @abstractmethod
    def create_checkout_session(
        self, *, workspace_id: int, plan: str, success_url: str, cancel_url: str,
    ) -> dict[str, Any]:
        """Return {checkout_url, session_id} for external payment page."""

    def parse_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any] | None:
        """Parse verified webhook into normalized event or None."""
        return None


class NullPaymentProvider(PaymentProvider):
    slug = "none"

    def is_configured(self) -> bool:
        return False

    def create_customer(self, *, workspace_id: int, email: str, name: str = "") -> dict[str, Any]:
        raise RuntimeError("Payment provider is not configured")

    def create_checkout_session(
        self, *, workspace_id: int, plan: str, success_url: str, cancel_url: str,
    ) -> dict[str, Any]:
        raise RuntimeError("Payment provider is not configured")


class StripePaymentProvider(PaymentProvider):
    slug = "stripe"

    def is_configured(self) -> bool:
        import os
        return bool(os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("PAYMENT_PROVIDER_KEY"))

    def _secret(self) -> str:
        import os
        key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("PAYMENT_PROVIDER_KEY") or ""
        if not key:
            raise RuntimeError("Stripe is not configured")
        return key

    def create_customer(self, *, workspace_id: int, email: str, name: str = "") -> dict[str, Any]:
        import json
        import urllib.error
        import urllib.request
        body = {"email": email, "name": name or None, "metadata": {"workspace_id": str(workspace_id)}}
        req = urllib.request.Request(
            "https://api.stripe.com/v1/customers",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self._secret()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with trace("payment.stripe.create_customer", provider="stripe", op="create_customer"):
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode() if exc.fp else str(exc)
            raise RuntimeError(f"Stripe customer creation failed: {detail}") from exc
        return {"provider_customer_id": data["id"], "raw": data}

    def create_checkout_session(
        self, *, workspace_id: int, plan: str, success_url: str, cancel_url: str,
    ) -> dict[str, Any]:
        raise RuntimeError("Stripe checkout requires price IDs — configure STRIPE_PRICE_* env vars")

    def parse_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any] | None:
        import json
        import os
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        if not secret:
            return None
        try:
            event = json.loads(payload.decode())
        except json.JSONDecodeError:
            _log.debug("stripe_webhook_json_parse_failed", exc_info=True, extra={"op": "parse_webhook"})
            return None
        etype = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}
        workspace_id = None
        meta = obj.get("metadata") or {}
        if meta.get("workspace_id"):
            try:
                workspace_id = int(meta["workspace_id"])
            except (TypeError, ValueError):
                _log.debug("webhook_workspace_id_parse_failed", exc_info=True, extra={"op": "parse_webhook"})
                pass
        if etype == "customer.subscription.updated" or etype == "customer.subscription.created":
            status_map = {"active": "active", "past_due": "past_due", "canceled": "cancelled", "trialing": "trialing"}
            return {
                "event_type": etype,
                "workspace_id": workspace_id,
                "provider": "stripe",
                "provider_customer_id": obj.get("customer"),
                "provider_subscription_id": obj.get("id"),
                "status": status_map.get(obj.get("status"), "inactive"),
                "plan": (obj.get("items") or {}).get("data", [{}])[0].get("price", {}).get("nickname") or "pro",
                "current_period_end": obj.get("current_period_end"),
            }
        if etype == "customer.subscription.deleted":
            return {
                "event_type": etype,
                "workspace_id": workspace_id,
                "provider": "stripe",
                "provider_subscription_id": obj.get("id"),
                "status": "cancelled",
            }
        return None


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    from integrations.config import payment_provider_name
    slug = (name or payment_provider_name()).lower()
    if slug == "stripe":
        return StripePaymentProvider()
    return NullPaymentProvider()
