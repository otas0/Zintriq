"""Zintriq Object Standards — universal behavior for every business object.

Human-readable spec: docs/bos/OBJECT_STANDARDS.md
Frontend mirror: static/bos/platform/object-standards.js
Domain ownership: bos/domain.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet


IDENTITY_FIELDS = ("id", "name", "description", "icon", "cover_image")
METADATA_FIELDS = ("created_at", "updated_at", "created_by", "updated_by")
OWNERSHIP_FIELDS = ("owner_type", "owner_id")
STATUS_MINIMUM = ("draft", "active", "archived")

FOUNDATION_LAYERS = (
    "identity", "metadata", "ownership", "relationships",
    "activity", "notes", "attachments", "tags", "permissions", "status", "audit",
)

STANDARD_PERMISSIONS = frozenset({
    "view", "create", "edit", "archive", "delete", "export", "assign",
})

STANDARD_BATCH_ACTIONS = (
    "select", "select_all", "archive", "delete", "export", "add_tags", "remove_tags",
)

STANDARD_CONTEXT_MENU = (
    ("open", "Open"),
    ("rename", "Rename"),
    ("duplicate", "Duplicate"),
    ("archive", "Archive"),
    ("delete", "Delete"),
)

OPTIONAL_CONTEXT_MENU = (
    ("export", "Export"),
    ("share", "Share"),
    ("move", "Move"),
    ("assign", "Assign"),
)

STANDARD_FILTERS = ("status", "tags", "created_date", "updated_date")
STANDARD_SEARCH_FIELDS = ("name", "id", "description", "tags")

STANDARD_DRAWER_TABS = (
    ("overview", "Overview"),
    ("properties", "Properties"),
    ("related", "Related"),
    ("activity", "Activity"),
    ("attachments", "Attachments"),
    ("notes", "Notes"),
)

ACTIVITY_EVENT_TYPES = frozenset({
    "created", "updated", "renamed", "status_changed",
    "tagged", "attached", "noted", "archived", "restored", "deleted",
})

API_OPERATIONS = (
    ("create", "POST", "{base}"),
    ("read", "GET", "{base}/{id}"),
    ("update", "PATCH", "{base}/{id}"),
    ("archive", "POST", "{base}/{id}/archive"),
    ("delete", "DELETE", "{base}/{id}"),
    ("restore", "POST", "{base}/{id}/restore"),
    ("list", "GET", "{base}"),
    ("search", "GET", "{base}?q="),
    ("export", "GET", "{base}/export"),
    ("batch", "POST", "{base}/batch"),
    ("notes", "POST", "{base}/{id}/notes"),
    ("timeline", "GET", "{base}/{id}/timeline"),
)

VALIDATION_CHECKLIST = (
    "Uses universal object foundation",
    "Globally unique ID",
    "Lifecycle management (draft/active/archived minimum)",
    "Tags support",
    "Notes support",
    "Attachments support",
    "Activity timeline",
    "Audit history",
    "Search",
    "Filters",
    "Batch operations",
    "Standard context menu",
    "Drawer detail experience",
    "Shared UI components only",
    "Platform events emitted",
    "Standard permission model",
    "Global search integration",
    "Notification framework integration",
    "No duplicate domain objects",
)


@dataclass(frozen=True)
class ObjectStandard:
    type: str
    foundation_layers: FrozenSet[str]
    statuses: tuple[str, ...]
    searchable_fields: tuple[str, ...]
    drawer_tabs: tuple[tuple[str, str], ...] = STANDARD_DRAWER_TABS
    batch_actions: tuple[str, ...] = STANDARD_BATCH_ACTIONS
    api_base: str | None = None
    conformance: dict[str, bool] = field(default_factory=dict)


def _default_conformance(**overrides: bool) -> dict[str, bool]:
    base = {item: False for item in VALIDATION_CHECKLIST}
    base.update(overrides)
    return base


OBJECT_STANDARDS: dict[str, ObjectStandard] = {
    "customer": ObjectStandard(
        type="customer",
        foundation_layers=frozenset(FOUNDATION_LAYERS),
        statuses=("active", "inactive", "blocked", "archived"),
        searchable_fields=("full_name", "email", "phone", "customer_code", "company", "tags"),
        api_base="/api/customers",
        conformance=_default_conformance(
            **{
                "Uses universal object foundation": True,
                "Globally unique ID": True,
                "Lifecycle management (draft/active/archived minimum)": True,
                "Tags support": True,
                "Notes support": True,
                "Activity timeline": True,
                "Audit history": True,
                "Search": True,
                "Filters": True,
                "Batch operations": True,
                "Drawer detail experience": True,
                "Shared UI components only": True,
            }
        ),
    ),
    "feedback": ObjectStandard(
        type="feedback",
        foundation_layers=frozenset({"identity", "metadata", "ownership", "relationships", "activity", "tags", "status", "audit"}),
        statuses=("new", "read", "replied", "archived", "hidden", "flagged"),
        searchable_fields=("comment", "customer_name", "rating", "feedback_type", "tags"),
        api_base="/api/feedback/records",
        conformance=_default_conformance(
            **{
                "Uses universal object foundation": True,
                "Globally unique ID": True,
                "Lifecycle management (draft/active/archived minimum)": True,
                "Tags support": True,
                "Activity timeline": True,
                "Search": True,
                "Filters": True,
                "Shared UI components only": True,
                "Attachments support": True,
            }
        ),
    ),
    "workspace": ObjectStandard(
        type="workspace",
        foundation_layers=frozenset({"identity", "metadata", "ownership", "relationships", "activity", "tags", "status", "audit"}),
        statuses=("active", "archived", "suspended"),
        searchable_fields=("name", "slug", "tags"),
        conformance=_default_conformance(
            **{
                "Uses universal object foundation": True,
                "Globally unique ID": True,
                "Lifecycle management (draft/active/archived minimum)": True,
                "Tags support": True,
                "Drawer detail experience": True,
                "Shared UI components only": True,
            }
        ),
    ),
    "product": ObjectStandard(
        type="product",
        foundation_layers=frozenset(FOUNDATION_LAYERS),
        statuses=("draft", "active", "archived"),
        searchable_fields=("name", "sku", "description", "tags"),
        conformance=_default_conformance(
            **{
                "Uses universal object foundation": True,
                "Drawer detail experience": True,
                "Tags support": True,
                "Notes support": True,
                "Attachments support": True,
                "Activity timeline": True,
                "Batch operations": True,
            }
        ),
    ),
    "store": ObjectStandard(
        type="store",
        foundation_layers=frozenset({"identity", "metadata", "ownership", "relationships", "status", "audit"}),
        statuses=("draft", "active", "archived"),
        searchable_fields=("name", "slug", "description"),
        conformance=_default_conformance(**{"Uses universal object foundation": True, "Globally unique ID": True}),
    ),
    "event": ObjectStandard(
        type="event",
        foundation_layers=frozenset({"identity", "metadata", "ownership", "relationships", "activity", "status", "audit"}),
        statuses=("draft", "published", "completed", "archived"),
        searchable_fields=("name", "description"),
        conformance=_default_conformance(**{"Uses universal object foundation": True, "Activity timeline": True}),
    ),
    "task": ObjectStandard(
        type="task",
        foundation_layers=frozenset(FOUNDATION_LAYERS),
        statuses=("open", "in_progress", "done", "archived"),
        searchable_fields=("title", "description", "tags"),
        conformance=_default_conformance(
            **{
                "Uses universal object foundation": True,
                "Tags support": True,
                "Notes support": True,
                "Attachments support": True,
                "Activity timeline": True,
                "Batch operations": True,
                "Drawer detail experience": True,
            }
        ),
    ),
}

NON_NEGOTIABLE_RULES = (
    "Every business object follows the same interaction model.",
    "Every business object inherits the same core behaviors.",
    "Shared functionality must never be reimplemented per module.",
    "Archive is the default lifecycle action — not Delete.",
    "Relationships use references — never duplicated data.",
    "Every future module must comply before development begins.",
)


def get_object_standard(type_key: str) -> ObjectStandard | None:
    return OBJECT_STANDARDS.get(type_key)


def api_path(type_key: str, operation: str, object_id: str | int | None = None) -> str | None:
    std = get_object_standard(type_key)
    if not std or not std.api_base:
        return None
    base = std.api_base.rstrip("/")
    if operation == "list":
        return base
    if operation in ("read", "update", "delete", "archive", "restore") and object_id is not None:
        suffix = {"read": "", "update": "", "delete": "", "archive": "/archive", "restore": "/restore"}[operation]
        return f"{base}/{object_id}{suffix}"
    if operation == "export":
        return f"{base}/export"
    if operation == "batch":
        return f"{base}/batch"
    if operation == "timeline" and object_id is not None:
        return f"{base}/{object_id}/timeline"
    return None


def checklist_score(type_key: str) -> tuple[int, int]:
    std = get_object_standard(type_key)
    if not std:
        return 0, len(VALIDATION_CHECKLIST)
    passed = sum(1 for v in std.conformance.values() if v)
    return passed, len(VALIDATION_CHECKLIST)
