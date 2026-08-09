"""Business OS Data Architecture — platform-wide data principles registry.

Human-readable spec: docs/bos/DATA_ARCHITECTURE.md
Frontend mirror: static/bos/platform/data-architecture.js

This is NOT database DDL. It defines how data is owned, referenced, synced, and consumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

# ── Core principles ──────────────────────────────────────────────────────────

DATA_PRINCIPLES = (
    "single_source_of_truth",
    "reference_not_duplicate",
    "one_owner_per_object",
    "event_propagation",
    "immutable_history",
    "derived_not_authoritative",
    "disposable_search_index",
    "cache_not_source",
    "archive_over_delete",
    "workspace_root",
)

NON_NEGOTIABLE_RULES = (
    "One object = one source of truth",
    "Relationships use references, never duplicated records",
    "Events propagate changes",
    "Derived data is never authoritative",
    "Archived data remains recoverable",
    "Every platform follows the same ownership model",
)

# Layers that hold data by role
DATA_LAYERS = (
    "authoritative",   # business object tables — current state
    "reference",       # FK relationships between objects
    "immutable",       # domain_events, audit append-only
    "projection",      # activity timelines written by subscribers
    "derived",         # analytics, aggregates, search indexes
    "cache",           # client/session caches — disposable
)

# Default lifecycle — archive before hard delete
DEFAULT_LIFECYCLE = ("draft", "active", "archived", "deleted")

SOFT_DELETE_DEFAULT = "archived"


@dataclass(frozen=True)
class DataOwnership:
    """Who owns authoritative data for an object type."""

    object_type: str
    owner_type: str
    owner_field: str
    table: str | None = None
    maturity: str = "implemented"


@dataclass(frozen=True)
class ReferenceRule:
    """A directed reference between object types."""

    from_type: str
    field: str
    to_type: str
    required: bool = False


@dataclass(frozen=True)
class DerivedStore:
    """A non-authoritative data store rebuilt from sources."""

    id: str
    label: str
    sources: tuple[str, ...]
    rebuild: str
    maturity: str = "implemented"


@dataclass(frozen=True)
class PrincipleConformance:
    principle: str
    implemented: bool
    notes: str = ""


# Workspace-scoped authoritative objects
OWNERSHIP_REGISTRY: dict[str, DataOwnership] = {
    "workspace": DataOwnership("workspace", "organization", "organization_id", "workspaces"),
    "store": DataOwnership("store", "workspace", "workspace_id", "stores"),
    "customer": DataOwnership("customer", "workspace", "workspace_id", "customer_profiles", "implemented"),
    "feedback": DataOwnership("feedback", "store", "store_id", "feedback_records"),
    "feedback_template": DataOwnership("feedback_template", "store", "store_id", "feedback_templates"),
    "event": DataOwnership("event", "store", "store_id", "events"),
    "user": DataOwnership("user", "none", "", "users"),
    "organization": DataOwnership("organization", "user", "owner_id", "organizations", "partial"),
}

REFERENCE_REGISTRY: tuple[ReferenceRule, ...] = (
    ReferenceRule("feedback", "customer_id", "customer"),
    ReferenceRule("feedback", "store_id", "store", required=True),
    ReferenceRule("feedback", "template_id", "feedback_template"),
    ReferenceRule("store", "workspace_id", "workspace", required=True),
    ReferenceRule("customer", "workspace_id", "workspace"),
    ReferenceRule("customer", "primary_store_id", "store"),
    ReferenceRule("event_attendee", "customer_id", "customer"),
    ReferenceRule("event", "store_id", "store", required=True),
    ReferenceRule("check_in_log", "customer_id", "customer"),
)

DERIVED_STORES: tuple[DerivedStore, ...] = (
    DerivedStore("domain_events", "Domain Event Log", ("all_objects",), "Append-only; never delete"),
    DerivedStore("event_analytics", "Analytics Counters", ("domain_events",), "Re-aggregate from events"),
    DerivedStore("workspace_search", "Workspace Search Index", ("customer", "store", "feedback"), "Live SQL query — no persistent index"),
    DerivedStore("customer_activities", "Customer Timeline Projection", ("domain_events",), "Rebuild from domain_events filter"),
    DerivedStore("event_notifications", "Notification Feed", ("domain_events",), "Derived from events + rules"),
    DerivedStore("bos_local_store", "BOS Mock Client Store", ("seed.js",), "Not authoritative — migrate to API", "partial"),
)

IMMUTABLE_STORES: FrozenSet[str] = frozenset({
    "domain_events",
    "feedback_activity",
    "workflow_executions",
    "pass_scan_log",
    "check_in_log",
})

SYNC_MECHANISM = "event_bus"  # platforms never direct-sync

CONFORMANCE: tuple[PrincipleConformance, ...] = (
    PrincipleConformance("single_source_of_truth", True, "customer_profiles, stores authoritative"),
    PrincipleConformance("reference_not_duplicate", True, "customer_id on feedback; anonymous fields exception"),
    PrincipleConformance("one_owner_per_object", True, "workspace_id scope"),
    PrincipleConformance("event_propagation", True, "bos/events.py emit + subscribers"),
    PrincipleConformance("immutable_history", True, "domain_events append-only"),
    PrincipleConformance("derived_not_authoritative", True, "event_analytics, search API"),
    PrincipleConformance("disposable_search_index", True, "No separate search DB"),
    PrincipleConformance("cache_not_source", True, "Business OS modules use REST APIs; store.js is UI prefs only"),
    PrincipleConformance("archive_over_delete", True, "status=archived default"),
    PrincipleConformance("workspace_root", True, "All operational data under workspace"),
)


def ownership_for(object_type: str) -> DataOwnership | None:
    return OWNERSHIP_REGISTRY.get(object_type)


def references_from(object_type: str) -> list[ReferenceRule]:
    return [r for r in REFERENCE_REGISTRY if r.from_type == object_type]


def conformance_gaps() -> list[str]:
    return [c.principle for c in CONFORMANCE if not c.implemented]


def is_immutable_store(store_id: str) -> bool:
    return store_id in IMMUTABLE_STORES
