"""Zintriq Platform Specification — universal platform standards registry.

Human-readable spec: docs/bos/PLATFORM_SPECIFICATION.md
Frontend mirror: static/bos/platform/platform-spec.js
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

# Standard sections every platform may implement
PLATFORM_SECTIONS = (
    "overview",
    "object_list",
    "detail",
    "activity",
    "analytics",
    "settings",
    "integrations",
)

# Minimum sections for a "complete" platform
REQUIRED_SECTIONS = frozenset({"overview", "object_list", "detail", "settings"})

# Minimum batch actions for collection platforms
REQUIRED_BATCH_ACTIONS = frozenset({"select", "select_all", "archive", "delete", "export", "add_tags"})

# Foundation services platforms consume — never reimplement
FOUNDATION_SERVICES = frozenset({
    "events", "notifications", "search", "permissions", "files", "settings_framework",
})

# Core services platforms depend on
CORE_SERVICES = frozenset({
    "shell", "navigation", "workspace", "auth", "authorization",
})


@dataclass(frozen=True)
class PlatformSection:
    id: str
    label: str
    required: bool = False


@dataclass(frozen=True)
class PlatformConformance:
    shell_integrated: bool = False
    emits_events: bool = False
    uses_shared_components: bool = False
    drawer_detail: bool = False
    batch_operations: bool = False
    global_search_registered: bool = False
    no_direct_notifications: bool = False
    api_backed: bool = False
    settings_section: bool = False
    activity_section: bool = False


@dataclass(frozen=True)
class PlatformSpec:
    id: str
    label: str
    operates_on: tuple[str, ...]
    sections: tuple[PlatformSection, ...]
    backend: tuple[str, ...] = ()
    frontend: tuple[str, ...] = ()
    maturity: str = "planned"  # implemented | partial | planned
    conformance: PlatformConformance = field(default_factory=PlatformConformance)
    notes: str = ""


STANDARD_SECTIONS: tuple[PlatformSection, ...] = (
    PlatformSection("overview", "Overview", required=True),
    PlatformSection("object_list", "Object List", required=True),
    PlatformSection("detail", "Detail", required=True),
    PlatformSection("activity", "Activity"),
    PlatformSection("analytics", "Analytics"),
    PlatformSection("settings", "Settings", required=True),
    PlatformSection("integrations", "Integrations"),
)


PLATFORM_REGISTRY: dict[str, PlatformSpec] = {
    "workspaces": PlatformSpec(
        id="workspaces", label="Workspace Platform",
        operates_on=("workspace", "store"),
        sections=(
            PlatformSection("overview", "Overview", required=True),
            PlatformSection("object_list", "Stores"),
            PlatformSection("detail", "Members"),
            PlatformSection("activity", "Activity"),
            PlatformSection("settings", "Settings", required=True),
        ),
        backend=("workspace_platform.py",),
        frontend=("static/bos/features/workspaces-page.js",),
        maturity="implemented",
        conformance=PlatformConformance(
            shell_integrated=True, emits_events=True, uses_shared_components=True,
            drawer_detail=False, api_backed=True, settings_section=True, activity_section=True,
            no_direct_notifications=True,
        ),
    ),
    "customers": PlatformSpec(
        id="customers", label="Customer Platform",
        operates_on=("customer",),
        sections=(
            PlatformSection("overview", "Overview", required=True),
            PlatformSection("object_list", "Customers", required=True),
            PlatformSection("detail", "Detail", required=True),
            PlatformSection("activity", "Activity"),
            PlatformSection("settings", "Settings", required=True),
        ),
        backend=("customer_platform.py",),
        frontend=("static/bos/features/customers-page.js",),
        maturity="implemented",
        conformance=PlatformConformance(
            shell_integrated=True, emits_events=True, uses_shared_components=True,
            drawer_detail=True, batch_operations=True, global_search_registered=True,
            api_backed=True, settings_section=True, activity_section=True,
            no_direct_notifications=True,
        ),
    ),
    "feedback": PlatformSpec(
        id="feedback", label="Feedback Platform",
        operates_on=("feedback", "feedback_template"),
        sections=(
            PlatformSection("overview", "Overview", required=True),
            PlatformSection("object_list", "Templates"),
            PlatformSection("object_list", "Inbox", required=True),
            PlatformSection("analytics", "Analytics"),
            PlatformSection("settings", "Settings", required=True),
        ),
        backend=("feedback_platform.py",),
        frontend=("static/bos/features/feedback-page.js",),
        maturity="implemented",
        conformance=PlatformConformance(
            shell_integrated=True, emits_events=True, uses_shared_components=True,
            drawer_detail=True, api_backed=True, settings_section=True,
            no_direct_notifications=True, activity_section=False,
        ),
        notes="QR is publish channel only; Reviews is first feedback type.",
    ),
    "qr": PlatformSpec(
        id="qr", label="QR Platform",
        operates_on=("store", "qr", "product", "event", "business_card", "check_in"),
        sections=(
            PlatformSection("object_list", "Stores", required=True),
            PlatformSection("detail", "QR Assets"),
            PlatformSection("settings", "Store Settings"),
        ),
        backend=("app.py",),
        frontend=("templates/owner/", "static/owner.js"),
        maturity="implemented",
        conformance=PlatformConformance(
            shell_integrated=True, emits_events=False, uses_shared_components=False,
            drawer_detail=False, api_backed=True,
        ),
        notes="Owner UI outside BOS shell; migrating toward shell integration.",
    ),
    "catalog": PlatformSpec(
        id="catalog", label="Product Platform",
        operates_on=("product", "catalog"),
        sections=STANDARD_SECTIONS,
        frontend=("static/bos/features/module-page.js",),
        maturity="partial",
        conformance=PlatformConformance(
            shell_integrated=True, uses_shared_components=True, drawer_detail=True,
            batch_operations=True, emits_events=False, api_backed=False,
        ),
        notes="Mock data via store.js; API backend planned.",
    ),
    "transactions": PlatformSpec(
        id="transactions", label="Order Platform",
        operates_on=("order", "transaction"),
        sections=STANDARD_SECTIONS,
        frontend=("static/bos/features/module-page.js",),
        maturity="partial",
        conformance=PlatformConformance(
            shell_integrated=True, uses_shared_components=True, drawer_detail=True,
            batch_operations=True, emits_events=False, api_backed=False,
        ),
    ),
    "team": PlatformSpec(
        id="team", label="Team Platform",
        operates_on=("employee", "team"),
        sections=STANDARD_SECTIONS,
        frontend=("static/bos/features/module-page.js",),
        maturity="partial",
        conformance=PlatformConformance(
            shell_integrated=True, uses_shared_components=True, drawer_detail=True,
            batch_operations=True, emits_events=False, api_backed=False,
        ),
    ),
    "documents": PlatformSpec(
        id="documents", label="Documents Platform",
        operates_on=("document",),
        sections=STANDARD_SECTIONS,
        frontend=("static/bos/features/module-page.js",),
        maturity="partial",
        conformance=PlatformConformance(
            shell_integrated=True, uses_shared_components=True, drawer_detail=True,
            batch_operations=True, emits_events=False, api_backed=False,
        ),
    ),
    "inventory": PlatformSpec(
        id="inventory", label="Inventory Platform",
        operates_on=("inventory", "product"),
        sections=STANDARD_SECTIONS,
        maturity="planned",
    ),
    "analytics": PlatformSpec(
        id="analytics", label="Analytics Platform",
        operates_on=(),
        sections=(
            PlatformSection("overview", "Overview", required=True),
            PlatformSection("analytics", "Analytics", required=True),
        ),
        backend=("event_platform.py", "feedback_platform.py"),
        maturity="partial",
        conformance=PlatformConformance(
            shell_integrated=True, emits_events=False, api_backed=True,
        ),
        notes="Event consumer only — never modifies platform objects.",
    ),
}


def platform_spec(platform_id: str) -> PlatformSpec | None:
    return PLATFORM_REGISTRY.get(platform_id)


def is_platform_complete(platform_id: str) -> bool:
    spec = PLATFORM_REGISTRY.get(platform_id)
    if not spec or spec.maturity != "implemented":
        return False
    section_ids = {s.id for s in spec.sections}
    if not REQUIRED_SECTIONS.issubset(section_ids):
        return False
    c = spec.conformance
    return (
        c.shell_integrated
        and c.emits_events
        and c.uses_shared_components
        and c.api_backed
        and c.no_direct_notifications
        and c.settings_section
    )


def conformance_gaps(platform_id: str) -> list[str]:
    spec = PLATFORM_REGISTRY.get(platform_id)
    if not spec:
        return ["Platform not registered"]
    gaps: list[str] = []
    c = spec.conformance
    checks = {
        "shell_integrated": "Integrate with Application Shell",
        "emits_events": "Emit domain events via Event Bus",
        "uses_shared_components": "Use shared component library",
        "drawer_detail": "Use drawer-first detail view",
        "batch_operations": "Support batch operations",
        "global_search_registered": "Register objects in Global Search",
        "no_direct_notifications": "Stop direct notification creation",
        "api_backed": "Backend API (not mock store only)",
        "settings_section": "Provide Settings section",
        "activity_section": "Provide Activity section",
    }
    for attr, label in checks.items():
        if not getattr(c, attr, False):
            gaps.append(label)
    section_ids = {s.id for s in spec.sections}
    for req in REQUIRED_SECTIONS:
        if req not in section_ids:
            gaps.append(f"Missing required section: {req}")
    return gaps
