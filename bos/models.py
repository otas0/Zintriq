"""Zintriq domain models — MVP platform scope."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BosModule:
    id: str
    label: str
    icon: str
    endpoint: str
    description: str = ""


# Zintriq module registry — MVP navigation
BOS_MODULES: tuple[BosModule, ...] = (
    BosModule("store", "Stores", "▣", "bos.store", "Live store hub at /manage — products, QR, settings"),
    BosModule("team", "Team", "◈", "bos.team", "Invite members and manage access"),
    BosModule("settings", "Settings", "⚙", "bos.settings", "Workspace configuration"),
    # Legacy module ids — redirect into Store
    BosModule("qr", "Experiences", "⬡", "bos.qr_experiences", "Legacy — use Store"),
    BosModule("responses", "Responses", "✎", "bos.responses", "Legacy — use Store"),
    # Legacy / deferred modules (URL-only, not in primary nav)
    BosModule("customers", "Responses", "✎", "bos.responses", "Legacy alias"),
    BosModule("interactions", "Responses", "✎", "bos.responses", "Legacy alias"),
    BosModule("feedback", "Responses", "✎", "bos.responses", "Legacy alias"),
    BosModule("operations", "Operations", "◎", "bos.operations", "Deferred — bookings & check-ins"),
    BosModule("checkin", "Check-in", "✓", "bos.check_in", "Live check-in under Manage"),
    BosModule("booking", "Booking", "◷", "bos.booking", "Deferred"),
    BosModule("calendar", "Calendar", "📅", "bos.calendar", "Deferred"),
)


def module_for_id(module_id: str) -> BosModule | None:
    return next((m for m in BOS_MODULES if m.id == module_id), None)


def row_to_dict(row: Any) -> dict:
    return dict(row) if row is not None else {}
