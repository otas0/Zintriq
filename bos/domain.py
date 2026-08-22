"""Zintriq domain model — canonical registry for ownership, relationships, and lifecycle.

Human-readable spec: docs/bos/DOMAIN_MODEL.md
Frontend mirror: static/bos/platform/domain-model.js

This module defines the business domain. It is NOT database DDL and NOT UI schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet


LIFECYCLE_DEFAULT = ("created", "active", "updated", "archived", "restored", "deleted")

SHARED_BEHAVIORS = frozenset({
    "activity", "notes", "attachments", "tags", "search", "filters",
    "archive", "restore", "permissions", "audit",
})

PERMISSION_ACTIONS = frozenset({
    "create", "read", "update", "archive", "delete", "export",
    "assign", "reply", "publish",
})


@dataclass(frozen=True)
class DomainObject:
    """One business object type in the domain."""

    type: str
    label: str
    collection: str | None
    owner_type: str
    owner_field: str | None
    references: tuple[str, ...]
    platform: str
    lifecycle: tuple[str, ...] = LIFECYCLE_DEFAULT
    behaviors: FrozenSet[str] = field(default_factory=lambda: SHARED_BEHAVIORS)
    owns_data: bool = True
    maturity: str = "planned"  # implemented | partial | planned
    table: str | None = None


@dataclass(frozen=True)
class PlatformDef:
    """A platform operates on domain objects; it does not replace them."""

    id: str
    label: str
    operates_on: tuple[str, ...]
    read_only: bool = False


ROOT_TYPES = frozenset({"user", "organization", "workspace"})

DOMAIN_OBJECTS: dict[str, DomainObject] = {
    "user": DomainObject(
        type="user", label="User", collection=None,
        owner_type="none", owner_field=None, references=(),
        platform="auth", owns_data=True, maturity="implemented", table="users",
        behaviors=frozenset({"permissions", "audit"}),
    ),
    "organization": DomainObject(
        type="organization", label="Organization", collection="organizations",
        owner_type="user", owner_field="ownerId", references=("user",),
        platform="organizations", maturity="partial", table="organizations",
    ),
    "workspace": DomainObject(
        type="workspace", label="Workspace", collection="workspaces",
        owner_type="organization", owner_field="organizationId", references=("organization",),
        platform="workspaces", maturity="implemented", table="workspaces",
        lifecycle=("active", "archived", "suspended"),
    ),
    "store": DomainObject(
        type="store", label="Store", collection=None,
        owner_type="workspace", owner_field="workspaceId", references=("workspace",),
        platform="qr_workspace", maturity="implemented", table="stores",
        lifecycle=("draft", "active", "archived"),
    ),
    "customer": DomainObject(
        type="customer", label="Customer", collection="customers",
        owner_type="workspace", owner_field="workspaceId", references=("workspace", "store"),
        platform="customers", maturity="implemented", table="customer_profiles",
        lifecycle=("active", "inactive", "blocked", "archived"),
        behaviors=frozenset(SHARED_BEHAVIORS | {"export", "timeline", "files"}),
    ),
    "product": DomainObject(
        type="product", label="Product", collection="catalog",
        owner_type="workspace", owner_field="workspaceId", references=("workspace",),
        platform="catalog", maturity="partial", table="items",
        lifecycle=("draft", "active", "archived"),
    ),
    "service": DomainObject(
        type="service", label="Service", collection=None,
        owner_type="workspace", owner_field="workspaceId", references=("workspace",),
        platform="catalog", maturity="planned",
    ),
    "employee": DomainObject(
        type="employee", label="Employee", collection="team",
        owner_type="workspace", owner_field="workspaceId", references=("workspace", "user"),
        platform="team", maturity="partial",
        lifecycle=("invited", "active", "inactive", "archived"),
    ),
    "qr": DomainObject(
        type="qr", label="QR", collection=None,
        owner_type="store", owner_field="storeId", references=("store",),
        platform="qr", owns_data=False, maturity="implemented", table="qr_codes",
        lifecycle=("draft", "active", "archived"),
        behaviors=frozenset({"publish", "archive", "search"}),
    ),
    "feedback_template": DomainObject(
        type="feedback_template", label="Feedback Template", collection=None,
        owner_type="store", owner_field="storeId", references=("workspace", "store"),
        platform="feedback", maturity="implemented", table="feedback_templates",
        lifecycle=("draft", "published", "archived"),
    ),
    "feedback": DomainObject(
        type="feedback", label="Feedback", collection=None,
        owner_type="store", owner_field="storeId",
        references=("workspace", "store", "feedback_template", "customer", "qr"),
        platform="feedback", maturity="implemented", table="feedback_records",
        lifecycle=("new", "read", "replied", "archived", "hidden", "flagged"),
        behaviors=frozenset(SHARED_BEHAVIORS | {"reply", "export"}),
    ),
    "event": DomainObject(
        type="event", label="Event", collection=None,
        owner_type="store", owner_field="storeId",
        references=("workspace", "store", "customer", "employee", "qr"),
        platform="qr", maturity="implemented", table="events",
        lifecycle=("draft", "published", "completed", "archived"),
    ),
    "appointment": DomainObject(
        type="appointment", label="Appointment", collection=None,
        owner_type="store", owner_field="storeId",
        references=("customer", "employee", "service", "store", "workspace"),
        platform="booking", maturity="planned",
        lifecycle=("scheduled", "confirmed", "completed", "cancelled", "archived"),
    ),
    "order": DomainObject(
        type="order", label="Order", collection="transactions",
        owner_type="workspace", owner_field="workspaceId",
        references=("customer", "product", "service", "store", "employee", "workspace"),
        platform="transactions", maturity="planned",
        lifecycle=("pending", "completed", "refunded", "archived"),
    ),
    "membership": DomainObject(
        type="membership", label="Membership", collection=None,
        owner_type="workspace", owner_field="workspaceId", references=("customer", "workspace"),
        platform="membership", maturity="planned",
    ),
    "inventory": DomainObject(
        type="inventory", label="Inventory", collection=None,
        owner_type="store", owner_field="storeId", references=("product", "store", "workspace"),
        platform="inventory", maturity="planned", owns_data=True,
    ),
    "document": DomainObject(
        type="document", label="Document", collection="documents",
        owner_type="workspace", owner_field="workspaceId",
        references=("workspace", "customer", "employee", "product", "order", "event"),
        platform="documents", maturity="partial", table="customer_files",
    ),
    "notification": DomainObject(
        type="notification", label="Notification", collection=None,
        owner_type="user", owner_field="userId", references=(),
        platform="notifications", owns_data=False, maturity="partial",
        lifecycle=("unread", "read", "dismissed"),
        behaviors=frozenset({"read", "search"}),
    ),
    "task": DomainObject(
        type="task", label="Task", collection="operations",
        owner_type="workspace", owner_field="workspaceId", references=("workspace",),
        platform="operations", maturity="partial",
        lifecycle=("open", "in_progress", "done", "archived"),
        behaviors=frozenset(SHARED_BEHAVIORS | {"assign"}),
    ),
    "automation": DomainObject(
        type="automation", label="Automation", collection=None,
        owner_type="workspace", owner_field="workspaceId", references=("workspace",),
        platform="automation", maturity="planned",
        lifecycle=("draft", "active", "paused", "archived"),
    ),
    "analytics": DomainObject(
        type="analytics", label="Analytics", collection=None,
        owner_type="none", owner_field=None, references=(),
        platform="analytics", owns_data=False, maturity="partial",
        behaviors=frozenset({"read", "export"}),
    ),
    "settings": DomainObject(
        type="settings", label="Settings", collection=None,
        owner_type="workspace", owner_field="workspaceId", references=("workspace", "store"),
        platform="settings", maturity="partial",
        behaviors=frozenset({"read", "update"}),
    ),
}

PLATFORMS: dict[str, PlatformDef] = {
    "auth": PlatformDef("auth", "Authentication", ("user",)),
    "organizations": PlatformDef("organizations", "Organization", ("organization",)),
    "workspaces": PlatformDef("workspaces", "Workspaces", ("workspace",)),
    "experiences": PlatformDef("experiences", "Experiences", ("experience", "settings")),
    "qr": PlatformDef("qr", "QR Platform", ("qr", "event", "product", "store")),
    "customers": PlatformDef("customers", "Customer Platform", ("customer",)),
    "feedback": PlatformDef("feedback", "Feedback Platform", ("feedback_template", "feedback", "settings")),
    "catalog": PlatformDef("catalog", "Catalog", ("product", "service")),
    "team": PlatformDef("team", "Team", ("employee",)),
    "documents": PlatformDef("documents", "Documents", ("document",)),
    "operations": PlatformDef("operations", "Operations", ("task",)),
    "transactions": PlatformDef("transactions", "Transactions", ("order",)),
    "notifications": PlatformDef("notifications", "Notifications", ("notification",)),
    "analytics": PlatformDef("analytics", "Analytics", ("analytics",), read_only=True),
    "booking": PlatformDef("booking", "Booking", ("appointment",), read_only=False),
    "membership": PlatformDef("membership", "Membership", ("membership",)),
    "inventory": PlatformDef("inventory", "Inventory", ("inventory",)),
    "automation": PlatformDef("automation", "Automation Engine", ("automation",)),
    "settings": PlatformDef("settings", "Settings", ("settings",)),
}

# QR gateway may point to these target types (QR never owns them)
QR_TARGET_TYPES = frozenset({
    "product", "feedback_template", "event", "store", "check_in", "business_card",
})

NON_NEGOTIABLE_RULES = (
    "One object = one responsibility.",
    "Every object has exactly one owner.",
    "Relationships use references — never duplicated data.",
    "Platforms operate on objects; they do not own business domain data.",
    "Shared behaviors must remain consistent across all objects.",
    "New modules must update docs/bos/DOMAIN_MODEL.md and both code registries.",
)


def get_domain_object(type_key: str) -> DomainObject | None:
    return DOMAIN_OBJECTS.get(type_key)


def is_root_type(type_key: str) -> bool:
    return type_key in ROOT_TYPES


def platform_for_type(type_key: str) -> str | None:
    obj = get_domain_object(type_key)
    return obj.platform if obj else None


def owns_data(type_key: str) -> bool:
    obj = get_domain_object(type_key)
    return obj.owns_data if obj else False


def validate_reference(source_type: str, target_type: str) -> bool:
    """Return True if source_type may reference target_type per domain spec."""
    source = get_domain_object(source_type)
    if not source:
        return False
    return target_type in source.references or target_type == "workspace"


def objects_for_platform(platform_id: str) -> list[DomainObject]:
    return [o for o in DOMAIN_OBJECTS.values() if o.platform == platform_id]


def implemented_objects() -> list[DomainObject]:
    return [o for o in DOMAIN_OBJECTS.values() if o.maturity == "implemented"]
