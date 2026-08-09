/**
 * Business OS Object Standards — universal behavior registry (JavaScript mirror).
 *
 * Spec: docs/bos/OBJECT_STANDARDS.md
 * Backend mirror: bos/object_standards.py
 * Domain ownership: domain-model.js
 */

/** @typedef {{ id: string, label: string, optional?: boolean }} MenuAction */
/** @typedef {{ id: string, label: string }} DrawerTab */

/** Universal foundation layers every object extends */
export const FOUNDATION_LAYERS = [
  "identity", "metadata", "ownership", "relationships",
  "activity", "notes", "attachments", "tags", "permissions", "status", "audit",
];

/** @type {readonly string[]} */
export const IDENTITY_FIELDS = ["id", "name", "description", "icon", "coverImage"];

/** @type {readonly string[]} */
export const METADATA_FIELDS = ["createdAt", "updatedAt", "createdBy", "updatedBy"];

/** @type {readonly string[]} */
export const OWNERSHIP_FIELDS = ["ownerType", "ownerId"];

/** Minimum lifecycle statuses for every object */
export const STATUS_MINIMUM = ["draft", "active", "archived"];

/** @type {readonly string[]} */
export const STANDARD_PERMISSIONS = [
  "view", "create", "edit", "archive", "delete", "export", "assign",
];

/** @type {readonly string[]} */
export const STANDARD_BATCH_ACTIONS = [
  "select", "selectAll", "archive", "delete", "export", "addTags", "removeTags",
];

/** @type {readonly MenuAction[]} */
export const STANDARD_CONTEXT_MENU = [
  { id: "open", label: "Open" },
  { id: "rename", label: "Rename" },
  { id: "duplicate", label: "Duplicate" },
  { id: "archive", label: "Archive" },
  { id: "delete", label: "Delete" },
];

/** @type {readonly MenuAction[]} */
export const OPTIONAL_CONTEXT_MENU = [
  { id: "export", label: "Export", optional: true },
  { id: "share", label: "Share", optional: true },
  { id: "move", label: "Move", optional: true },
  { id: "assign", label: "Assign", optional: true },
];

/** @type {readonly string[]} */
export const STANDARD_FILTERS = ["status", "tags", "createdDate", "updatedDate"];

/** @type {readonly string[]} */
export const STANDARD_SEARCH_FIELDS = ["name", "id", "description", "tags"];

/** Standard drawer tabs — used by object-detail.js */
/** @type {readonly DrawerTab[]} */
export const STANDARD_DRAWER_TABS = [
  { id: "overview", label: "Overview" },
  { id: "properties", label: "Properties" },
  { id: "related", label: "Related" },
  { id: "activity", label: "Activity" },
  { id: "attachments", label: "Attachments" },
  { id: "notes", label: "Notes" },
];

/** @type {ReadonlySet<string>} */
export const ACTIVITY_EVENT_TYPES = new Set([
  "created", "updated", "renamed", "status_changed",
  "tagged", "attached", "noted", "archived", "restored", "deleted",
]);

/** REST API operation patterns */
export const API_PATTERNS = {
  create: { method: "POST", path: "{base}" },
  read: { method: "GET", path: "{base}/{id}" },
  update: { method: "PATCH", path: "{base}/{id}" },
  archive: { method: "POST", path: "{base}/{id}/archive" },
  delete: { method: "DELETE", path: "{base}/{id}" },
  restore: { method: "POST", path: "{base}/{id}/restore" },
  list: { method: "GET", path: "{base}" },
  search: { method: "GET", path: "{base}?q={q}" },
  export: { method: "GET", path: "{base}/export" },
  batch: { method: "POST", path: "{base}/batch" },
  notes: { method: "POST", path: "{base}/{id}/notes" },
  timeline: { method: "GET", path: "{base}/{id}/timeline" },
};

/** @type {readonly string[]} */
export const VALIDATION_CHECKLIST = [
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
];

/** @type {readonly string[]} */
export const NON_NEGOTIABLE_RULES = [
  "Every business object follows the same interaction model.",
  "Every business object inherits the same core behaviors.",
  "Shared functionality must never be reimplemented per module.",
  "Archive is the default lifecycle action — not Delete.",
  "Relationships use references — never duplicated data.",
  "Every future module must comply before development begins.",
];

/**
 * Per-type behavioral standard + conformance tracking.
 * @type {Record<string, object>}
 */
export const OBJECT_STANDARDS = {
  customer: {
    type: "customer",
    foundationLayers: FOUNDATION_LAYERS,
    statuses: ["active", "inactive", "blocked", "archived"],
    searchableFields: ["full_name", "email", "phone", "customer_code", "company", "tags"],
    apiBase: "/api/customers",
    drawerTabs: STANDARD_DRAWER_TABS,
    batchActions: STANDARD_BATCH_ACTIONS,
    conformance: {
      "Uses universal object foundation": true,
      "Globally unique ID": true,
      "Lifecycle management (draft/active/archived minimum)": true,
      "Tags support": true,
      "Notes support": true,
      "Activity timeline": true,
      "Audit history": true,
      "Search": true,
      "Filters": true,
      "Batch operations": true,
      "Drawer detail experience": true,
      "Shared UI components only": true,
    },
  },
  feedback: {
    type: "feedback",
    foundationLayers: ["identity", "metadata", "ownership", "relationships", "activity", "tags", "status", "audit"],
    statuses: ["new", "read", "replied", "archived", "hidden", "flagged"],
    searchableFields: ["comment", "customer_name", "rating", "feedback_type", "tags"],
    apiBase: "/api/feedback/records",
    conformance: {
      "Uses universal object foundation": true,
      "Globally unique ID": true,
      "Lifecycle management (draft/active/archived minimum)": true,
      "Tags support": true,
      "Activity timeline": true,
      "Search": true,
      "Filters": true,
      "Shared UI components only": true,
      "Attachments support": true,
    },
  },
  workspace: {
    type: "workspace",
    foundationLayers: ["identity", "metadata", "ownership", "relationships", "activity", "tags", "status", "audit"],
    statuses: ["active", "archived", "suspended"],
    searchableFields: ["name", "slug", "tags"],
    drawerTabs: STANDARD_DRAWER_TABS,
    conformance: {
      "Uses universal object foundation": true,
      "Globally unique ID": true,
      "Lifecycle management (draft/active/archived minimum)": true,
      "Tags support": true,
      "Drawer detail experience": true,
      "Shared UI components only": true,
    },
  },
  product: {
    type: "product",
    foundationLayers: FOUNDATION_LAYERS,
    statuses: ["draft", "active", "archived"],
    searchableFields: ["name", "sku", "description", "tags"],
    drawerTabs: STANDARD_DRAWER_TABS,
    conformance: {
      "Uses universal object foundation": true,
      "Drawer detail experience": true,
      "Tags support": true,
      "Notes support": true,
      "Attachments support": true,
      "Activity timeline": true,
      "Batch operations": true,
    },
  },
  store: {
    type: "store",
    foundationLayers: ["identity", "metadata", "ownership", "relationships", "status", "audit"],
    statuses: ["draft", "active", "archived"],
    searchableFields: ["name", "slug", "description"],
    conformance: { "Uses universal object foundation": true, "Globally unique ID": true },
  },
  event: {
    type: "event",
    foundationLayers: ["identity", "metadata", "ownership", "relationships", "activity", "status", "audit"],
    statuses: ["draft", "published", "completed", "archived"],
    searchableFields: ["name", "description"],
    conformance: { "Uses universal object foundation": true, "Activity timeline": true },
  },
  task: {
    type: "task",
    foundationLayers: FOUNDATION_LAYERS,
    statuses: ["open", "in_progress", "done", "archived"],
    searchableFields: ["title", "description", "tags"],
    drawerTabs: STANDARD_DRAWER_TABS,
    conformance: {
      "Uses universal object foundation": true,
      "Tags support": true,
      "Notes support": true,
      "Attachments support": true,
      "Activity timeline": true,
      "Batch operations": true,
      "Drawer detail experience": true,
    },
  },
};

/** Interaction model: Select → View → Edit → Done */
export const INTERACTION_MODEL = ["select", "view", "edit", "done"];

/** @param {string} typeKey */
export function getObjectStandard(typeKey) {
  return OBJECT_STANDARDS[typeKey] || null;
}

/**
 * @param {string} typeKey
 * @param {string} operation
 * @param {string|number} [id]
 */
export function apiPath(typeKey, operation, id) {
  const std = getObjectStandard(typeKey);
  if (!std?.apiBase) return null;
  const base = std.apiBase.replace(/\/$/, "");
  if (operation === "list" || operation === "search") return base;
  if (operation === "export") return `${base}/export`;
  if (operation === "batch") return `${base}/batch`;
  if (id == null) return null;
  const paths = {
    read: `${base}/${id}`,
    update: `${base}/${id}`,
    delete: `${base}/${id}`,
    archive: `${base}/${id}/archive`,
    restore: `${base}/${id}/restore`,
    timeline: `${base}/${id}/timeline`,
    notes: `${base}/${id}/notes`,
  };
  return paths[operation] || null;
}

/** @param {string} typeKey @returns {{ passed: number, total: number, items: Record<string, boolean> }} */
export function checklistScore(typeKey) {
  const std = getObjectStandard(typeKey);
  const items = {};
  VALIDATION_CHECKLIST.forEach((item) => { items[item] = false; });
  if (std?.conformance) Object.assign(items, std.conformance);
  const passed = Object.values(items).filter(Boolean).length;
  return { passed, total: VALIDATION_CHECKLIST.length, items };
}

/**
 * Build a minimal foundation record shape for new objects.
 * @param {Partial<{ id: string, name: string, status: string }>} overrides
 */
export function createFoundationRecord(overrides = {}) {
  const now = new Date().toISOString();
  return {
    id: overrides.id || "",
    name: overrides.name || "",
    description: "",
    status: overrides.status || "draft",
    createdAt: now,
    updatedAt: now,
    createdBy: null,
    updatedBy: null,
    tagIds: [],
    ...overrides,
  };
}

/**
 * Emit a standard platform notification event name.
 * @param {string} type e.g. "customer"
 * @param {string} action e.g. "created"
 */
export function platformEventName(type, action) {
  return `${type}.${action}`;
}
