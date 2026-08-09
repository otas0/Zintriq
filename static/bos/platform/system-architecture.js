/**
 * Business OS System Architecture — layer registry (JavaScript mirror).
 *
 * Spec: docs/bos/SYSTEM_ARCHITECTURE.md
 * Backend mirror: bos/architecture.py
 */

/** @typedef {'foundation'|'core'|'platform'|'shared'|'extension'} ArchitectureLayer */
/** @typedef {'implemented'|'partial'|'planned'} Maturity */

/**
 * @typedef {Object} LayerModuleDef
 * @property {string} id
 * @property {string} label
 * @property {ArchitectureLayer} layer
 * @property {string[]} paths
 * @property {string|null} [spec]
 * @property {Maturity} maturity
 * @property {string[]} dependsOn
 */

/** @type {readonly string[]} */
export const ARCHITECTURE_PRINCIPLES = [
  "domain_first", "platform_first", "object_driven", "event_driven", "component_driven",
];

/** @type {readonly ArchitectureLayer[]} */
export const DEPENDENCY_ORDER = ["extension", "platform", "core", "foundation"];

/** @type {readonly LayerModuleDef[]} */
export const FOUNDATION_MODULES = [
  { id: "domain", label: "Domain Models", layer: "foundation", paths: ["bos/domain.py", "static/bos/platform/domain-model.js"], spec: "docs/bos/DOMAIN_MODEL.md", maturity: "implemented", dependsOn: [] },
  { id: "object_standards", label: "Object Standards", layer: "foundation", paths: ["bos/object_standards.py", "static/bos/platform/object-standards.js"], spec: "docs/bos/OBJECT_STANDARDS.md", maturity: "implemented", dependsOn: [] },
  { id: "events", label: "Event Bus", layer: "foundation", paths: ["bos/events.py", "event_platform.py", "static/bos/platform/event-bus.js"], spec: "docs/bos/EVENT_BUS.md", maturity: "implemented", dependsOn: [] },
  { id: "permissions", label: "Permission Engine", layer: "foundation", paths: ["bos/domain.py"], maturity: "partial", dependsOn: [] },
  { id: "search", label: "Global Search", layer: "foundation", paths: ["static/bos/services/global-search.js"], maturity: "implemented", dependsOn: [] },
  { id: "notifications", label: "Notification Framework", layer: "foundation", paths: ["static/bos/platform/notifications.js"], maturity: "implemented", dependsOn: ["events"] },
  { id: "files", label: "File / Attachments", layer: "foundation", paths: ["static/bos/platform/attachments.js"], maturity: "partial", dependsOn: [] },
  { id: "settings", label: "Settings Framework", layer: "foundation", paths: ["workspace_platform.py"], maturity: "partial", dependsOn: [] },
];

/** @type {readonly LayerModuleDef[]} */
export const CORE_MODULES = [
  { id: "workspace", label: "Workspace Platform", layer: "core", paths: ["workspace_platform.py", "static/bos/services/workspace-context.js"], maturity: "implemented", dependsOn: ["domain", "events"] },
  { id: "shell", label: "Application Shell", layer: "core", paths: ["static/bos/core/shell.js", "templates/bos/shell.html"], spec: "docs/bos/APPLICATION_SHELL.md", maturity: "implemented", dependsOn: ["workspace"] },
  { id: "navigation", label: "Navigation", layer: "core", paths: ["static/bos/core/nav.js", "static/bos/core/workspace-switcher.js"], maturity: "implemented", dependsOn: ["shell"] },
  { id: "auth", label: "Authentication", layer: "core", paths: ["app.py"], maturity: "implemented", dependsOn: [] },
  { id: "authorization", label: "Authorization", layer: "core", paths: ["workspace_platform.py"], maturity: "partial", dependsOn: ["auth", "permissions"] },
  { id: "plugins", label: "Plugin Manager", layer: "core", paths: ["bos/architecture.py"], maturity: "planned", dependsOn: [] },
];

/** @type {readonly LayerModuleDef[]} */
export const PLATFORM_MODULES = [
  { id: "customers", label: "Customer Platform", layer: "platform", paths: ["customer_platform.py", "static/bos/features/customers-page.js"], maturity: "implemented", dependsOn: ["shell", "events", "domain"] },
  { id: "feedback", label: "Feedback Platform", layer: "platform", paths: ["feedback_platform.py", "static/bos/features/feedback-page.js"], maturity: "implemented", dependsOn: ["shell", "events", "domain"] },
  { id: "qr", label: "QR Platform", layer: "platform", paths: ["app.py"], maturity: "implemented", dependsOn: ["shell", "domain"] },
  { id: "catalog", label: "Product Platform", layer: "platform", paths: ["bos_modules_platform.py", "static/bos/features/catalog-page.js"], maturity: "stable", dependsOn: ["shell"] },
  { id: "transactions", label: "Order Platform", layer: "platform", paths: ["bos_modules_platform.py", "static/bos/features/transactions-page.js"], maturity: "stable", dependsOn: ["shell"] },
  { id: "team", label: "Team Platform", layer: "platform", paths: ["team_platform.py", "static/bos/features/team-page.js", "bos/permissions.py"], maturity: "implemented", dependsOn: ["shell", "events", "auth"] },
  { id: "tasks", label: "Task Platform", layer: "platform", paths: ["task_platform.py", "static/bos/features/operations-page.js"], maturity: "implemented", dependsOn: ["shell", "events", "team"] },
  { id: "inventory", label: "Inventory Platform", layer: "platform", paths: [], maturity: "planned", dependsOn: ["shell", "catalog"] },
  { id: "appointments", label: "Appointment Platform", layer: "platform", paths: [], maturity: "planned", dependsOn: ["shell", "customers"] },
  { id: "membership", label: "Membership Platform", layer: "platform", paths: [], maturity: "planned", dependsOn: ["shell", "customers"] },
  { id: "analytics", label: "Analytics Platform", layer: "platform", paths: ["event_platform.py"], maturity: "partial", dependsOn: ["events"] },
];

/** @type {readonly LayerModuleDef[]} */
export const SHARED_MODULES = [
  { id: "design_tokens", label: "Design Tokens", layer: "shared", paths: ["static/tokens.css", "static/materials.css"], maturity: "implemented", dependsOn: [] },
  { id: "components", label: "Component Library", layer: "shared", paths: ["static/bos/components/", "static/bos/components.css"], maturity: "implemented", dependsOn: [] },
  { id: "services", label: "JS Services", layer: "shared", paths: ["static/bos/services/"], maturity: "implemented", dependsOn: [] },
  { id: "api_client", label: "API Client", layer: "shared", paths: ["static/bos/services/api.js"], maturity: "implemented", dependsOn: [] },
];

/** @type {readonly LayerModuleDef[]} */
export const EXTENSION_MODULES = [
  { id: "integrations", label: "Integrations", layer: "extension", paths: [], maturity: "planned", dependsOn: [] },
  { id: "ai_copilot", label: "AI Copilot", layer: "extension", paths: [], maturity: "planned", dependsOn: [] },
];

/** @type {Record<string, LayerModuleDef>} */
export const ALL_MODULES = Object.fromEntries(
  [...FOUNDATION_MODULES, ...CORE_MODULES, ...PLATFORM_MODULES, ...SHARED_MODULES, ...EXTENSION_MODULES]
    .map((m) => [m.id, m]),
);

/** @type {readonly { id: string, label: string, examples: string[], locations: string[] }[]} */
export const STATE_LEVELS = [
  { id: "global", label: "Global State", examples: ["current_workspace", "current_user", "theme", "notifications"], locations: ["session", "workspace-context.js", "store.js"] },
  { id: "platform", label: "Platform State", examples: ["selected_rows", "filters", "drawer"], locations: ["selection.js", "ui-state.js"] },
  { id: "local", label: "Local State", examples: ["form_input", "dialog_open"], locations: ["component scope"] },
];

/** @type {readonly string[]} */
export const API_LAYERS = ["ui", "platform_api", "domain", "infrastructure"];

/** @type {readonly string[]} */
export const NAV_LEVELS = ["workspace", "platform", "object_list", "object_detail"];

/** @type {readonly { id: string, label: string }[]} */
export const PLUGIN_HOOKS = [
  { id: "register_page", label: "Register platform page" },
  { id: "register_object", label: "Register domain object type" },
  { id: "register_command", label: "Register command palette command" },
  { id: "register_event", label: "Subscribe to domain event" },
  { id: "register_nav", label: "Register sidebar nav item" },
  { id: "register_settings", label: "Register settings panel" },
  { id: "register_integration", label: "Register external integration" },
];

/** @param {string} moduleId @returns {ArchitectureLayer|null} */
export function layerForModule(moduleId) {
  return ALL_MODULES[moduleId]?.layer ?? null;
}

/** @param {string} fromId @param {string} toId */
export function allowedDependency(fromId, toId) {
  const a = ALL_MODULES[fromId];
  const b = ALL_MODULES[toId];
  if (!a || !b) return true;
  const order = Object.fromEntries(DEPENDENCY_ORDER.map((l, i) => [l, DEPENDENCY_ORDER.length - 1 - i]));
  return (order[a.layer] ?? 0) >= (order[b.layer] ?? 0);
}

/** @param {ArchitectureLayer} layer */
export function modulesInLayer(layer) {
  return Object.values(ALL_MODULES).filter((m) => m.layer === layer);
}
