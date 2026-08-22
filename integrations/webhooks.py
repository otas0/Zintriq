"""Webhook handlers — external provider events → Zintriq state."""

from __future__ import annotations

import json
from datetime import datetime

from integrations.payment import get_payment_provider
from integrations.payment.service import PaymentService


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def log_webhook(conn, *, provider: str, event_type: str, workspace_id: int | None, status: str, summary: str = "") -> None:
    conn.execute(
        """INSERT INTO integration_webhook_events
           (provider, event_type, workspace_id, payload_summary, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (provider, event_type, workspace_id, summary[:500], status, _now()),
    )


def handle_payment_webhook(conn, provider_slug: str, payload: bytes, signature: str | None) -> dict:
    provider = get_payment_provider(provider_slug)
    if not provider.is_configured():
        log_webhook(conn, provider=provider_slug, event_type="unknown", workspace_id=None, status="ignored")
        return {"ok": True, "handled": False, "reason": "provider_not_configured"}
    event = provider.parse_webhook(payload, signature)
    if not event:
        try:
            raw = json.loads(payload.decode())
            etype = raw.get("type", "unknown")
        except json.JSONDecodeError:
            etype = "invalid_payload"
        log_webhook(conn, provider=provider_slug, event_type=etype, workspace_id=None, status="unhandled")
        return {"ok": True, "handled": False}
    sub = PaymentService.apply_webhook_event(conn, event)
    log_webhook(
        conn,
        provider=provider_slug,
        event_type=event.get("event_type", "payment"),
        workspace_id=event.get("workspace_id"),
        status="applied" if sub else "no_workspace",
        summary=f"status={event.get('status')}",
    )
    return {"ok": True, "handled": bool(sub), "subscription": sub}
