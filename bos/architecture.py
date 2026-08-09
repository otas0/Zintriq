"""Business OS System Architecture — layer registry and dependency map.

Human-readable spec: docs/bos/SYSTEM_ARCHITECTURE.md
Frontend mirror: static/bos/platform/system-architecture.js
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Layer = Literal["foundation", "core", "platform", "shared", "extension"]

ARCHITECTURE_PRINCIPLES = (
    "domain_first",
    "platform_first",
    "object_driven",
    "event_driven",
    "component_driven",
)

DEPENDENCY_ORDER: tuple[Layer, ...] = ("extension", "platform", "core", "foundation")


@dataclass(frozen=True)
class LayerModule:
    id: str
    label: str
    layer: Layer
    paths: tuple[str, ...]
    spec: str | None = None
    maturity: str = "implemented"  # implemented | partial | planned
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateLevel:
    id: str
    label: str
    examples: tuple[str, ...]
    locations: tuple[str, ...]


@dataclass(frozen=True)
class PluginHook:
    id: str
    label: str
    maturity: str = "planned"


# ── Foundation ───────────────────────────────────────────────────────────────

FOUNDATION_MODULES: tuple[LayerModule, ...] = (
    LayerModule("domain", "Domain Models", "foundation", ("bos/domain.py", "static/bos/platform/domain-model.js"), "docs/bos/DOMAIN_MODEL.md"),
    LayerModule("data_architecture", "Data Architecture", "foundation", ("bos/data_architecture.py", "static/bos/platform/data-architecture.js"), "docs/bos/DATA_ARCHITECTURE.md"),
    LayerModule("object_standards", "Object Standards", "foundation", ("bos/object_standards.py", "static/bos/platform/object-standards.js"), "docs/bos/OBJECT_STANDARDS.md"),
    LayerModule("events", "Event Bus", "foundation", ("bos/events.py", "event_platform.py", "static/bos/platform/event-bus.js"), "docs/bos/EVENT_BUS.md"),
    LayerModule("workflows", "Workflow Engine", "foundation", ("bos/workflows.py", "workflow_platform.py", "static/bos/platform/workflow-engine.js"), "docs/bos/WORKFLOW_ENGINE.md", maturity="implemented", depends_on=("events",)),
    LayerModule("permissions", "Permission Engine", "foundation", ("bos/domain.py",), maturity="partial"),
    LayerModule("search", "Global Search", "foundation", ("static/bos/services/global-search.js",), maturity="implemented"),
    LayerModule("notifications", "Notification Framework", "foundation", ("static/bos/platform/notifications.js",), maturity="implemented", depends_on=("events",)),
    LayerModule("files", "File / Attachments", "foundation", ("static/bos/platform/attachments.js", "static/uploads/"), maturity="partial"),
    LayerModule("settings", "Settings Framework", "foundation", ("workspace_platform.py",), maturity="partial"),
)

# ── Core ─────────────────────────────────────────────────────────────────────

CORE_MODULES: tuple[LayerModule, ...] = (
    LayerModule("workspace", "Workspace Platform", "core", ("workspace_platform.py", "static/bos/services/workspace-context.js"), maturity="implemented", depends_on=("domain", "events")),
    LayerModule("shell", "Application Shell", "core", ("static/bos/core/shell.js", "static/bos/core/shell-nav.js", "templates/bos/shell.html"), "docs/bos/APPLICATION_SHELL.md", depends_on=("workspace",)),
    LayerModule("navigation", "Navigation", "core", ("static/bos/core/nav.js", "static/bos/core/workspace-switcher.js"), depends_on=("shell",)),
    LayerModule("auth", "Authentication", "core", ("app.py",), maturity="implemented"),
    LayerModule("authorization", "Authorization", "core", ("workspace_platform.py",), maturity="partial", depends_on=("auth", "permissions")),
    LayerModule("plugins", "Plugin Manager", "core", ("bos/architecture.py",), maturity="planned"),
)

# ── Platforms ────────────────────────────────────────────────────────────────

PLATFORM_MODULES: tuple[LayerModule, ...] = (
    LayerModule("customers", "Customer Platform", "platform", ("customer_platform.py", "static/bos/features/customers-page.js"), "docs/bos/PLATFORM_SPECIFICATION.md", maturity="implemented", depends_on=("shell", "events", "domain")),
    LayerModule("feedback", "Feedback Platform", "platform", ("feedback_platform.py", "static/bos/features/feedback-page.js"), "docs/bos/PLATFORM_SPECIFICATION.md", maturity="implemented", depends_on=("shell", "events", "domain")),
    LayerModule("qr", "QR Platform", "platform", ("app.py",), maturity="implemented", depends_on=("shell", "domain")),
    LayerModule("catalog", "Product Platform", "platform", ("static/bos/features/catalog-page.js", "bos_modules_platform.py"), maturity="stable", depends_on=("shell",)),
    LayerModule("transactions", "Order Platform", "platform", ("static/bos/features/transactions-page.js", "bos_modules_platform.py"), maturity="stable", depends_on=("shell",)),
    LayerModule("team", "Team Platform", "platform", ("team_platform.py", "static/bos/features/team-page.js", "bos/permissions.py"), maturity="implemented", depends_on=("shell", "events", "auth")),
    LayerModule("tasks", "Task Platform", "platform", ("task_platform.py", "static/bos/features/operations-page.js", "static/bos/services/tasks.js"), maturity="implemented", depends_on=("shell", "events", "team")),
    LayerModule("inventory", "Inventory Platform", "platform", (), maturity="planned", depends_on=("shell", "catalog")),
    LayerModule("appointments", "Appointment Platform", "platform", (), maturity="planned", depends_on=("shell", "customers")),
    LayerModule("membership", "Membership Platform", "platform", (), maturity="planned", depends_on=("shell", "customers")),
    LayerModule("analytics", "Analytics Platform", "platform", ("event_platform.py",), maturity="partial", depends_on=("events",)),
)

# ── Shared ───────────────────────────────────────────────────────────────────

SHARED_MODULES: tuple[LayerModule, ...] = (
    LayerModule("design_tokens", "Design Tokens", "shared", ("static/tokens.css", "static/materials.css", "static/system.css")),
    LayerModule("components", "Component Library", "shared", ("static/bos/components/", "static/bos/components.css")),
    LayerModule("shell_styles", "Shell Styles", "shared", ("static/bos/shell.css", "static/bos/polish.css")),
    LayerModule("services", "JS Services", "shared", ("static/bos/services/",)),
    LayerModule("platform_ui", "Platform UI Utilities", "shared", ("static/bos/platform/object-detail.js", "static/bos/platform/commands.js")),
    LayerModule("api_client", "API Client", "shared", ("static/bos/services/api.js",)),
)

# ── Extensions ───────────────────────────────────────────────────────────────

EXTENSION_MODULES: tuple[LayerModule, ...] = (
    LayerModule("integrations", "Integrations", "extension", (), maturity="planned"),
    LayerModule("marketplace", "Marketplace", "extension", (), maturity="planned"),
    LayerModule("ai_copilot", "AI Copilot", "extension", (), maturity="planned"),
)

ALL_MODULES: dict[str, LayerModule] = {
    m.id: m for m in (*FOUNDATION_MODULES, *CORE_MODULES, *PLATFORM_MODULES, *SHARED_MODULES, *EXTENSION_MODULES)
}

# ── State levels ─────────────────────────────────────────────────────────────

STATE_LEVELS: tuple[StateLevel, ...] = (
    StateLevel("global", "Global State", ("current_workspace", "current_user", "theme", "notifications"), ("session", "workspace-context.js", "store.js")),
    StateLevel("platform", "Platform State", ("selected_rows", "filters", "drawer", "module_ui"), ("selection.js", "ui-state.js", "features/*-page.js")),
    StateLevel("local", "Local State", ("form_input", "dialog_open", "hover"), ("component scope",)),
)

# ── Plugin hooks (future) ────────────────────────────────────────────────────

PLUGIN_HOOKS: tuple[PluginHook, ...] = (
    PluginHook("register_page", "Register platform page"),
    PluginHook("register_object", "Register domain object type"),
    PluginHook("register_command", "Register command palette command"),
    PluginHook("register_event", "Subscribe to domain event"),
    PluginHook("register_nav", "Register sidebar nav item"),
    PluginHook("register_settings", "Register settings panel"),
    PluginHook("register_integration", "Register external integration"),
)

# ── API flow ─────────────────────────────────────────────────────────────────

API_LAYERS = (
    "ui",           # feature-page.js, components
    "platform_api", # *_platform.py routes
    "domain",       # bos/domain.py, object rules
    "infrastructure",  # SQLite, filesystem
)

NAV_LEVELS = ("workspace", "platform", "object_list", "object_detail")


def layer_for_module(module_id: str) -> Layer | None:
    mod = ALL_MODULES.get(module_id)
    return mod.layer if mod else None


def allowed_dependency(from_id: str, to_id: str) -> bool:
    """Return True if from_id may depend on to_id (downward only)."""
    a, b = ALL_MODULES.get(from_id), ALL_MODULES.get(to_id)
    if not a or not b:
        return True  # unknown — don't block
    order = {layer: i for i, layer in enumerate(reversed(DEPENDENCY_ORDER))}
    # Higher layer may depend on same or lower layer (e.g. platform → foundation).
    return order.get(a.layer, 0) >= order.get(b.layer, 0)
