/**
 * Business OS Data Architecture — principles registry (JavaScript mirror).
 *
 * Spec: docs/bos/DATA_ARCHITECTURE.md
 * Backend: bos/data_architecture.py
 */

/** @type {readonly string[]} */
export const DATA_PRINCIPLES = [
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
];

/** @type {readonly string[]} */
export const NON_NEGOTIABLE_RULES = [
  "One object = one source of truth",
  "Relationships use references, never duplicated records",
  "Events propagate changes",
  "Derived data is never authoritative",
  "Archived data remains recoverable",
  "Every platform follows the same ownership model",
];

/** @type {readonly string[]} */
export const DATA_LAYERS = [
  "authoritative", "reference", "immutable", "projection", "derived", "cache",
];

/** @type {readonly string[]} */
export const DEFAULT_LIFECYCLE = ["draft", "active", "archived", "deleted"];

export const SOFT_DELETE_DEFAULT = "archived";

/** @type {ReadonlySet<string>} */
export const IMMUTABLE_STORES = new Set([
  "domain_events",
  "feedback_activity",
  "workflow_executions",
  "pass_scan_log",
  "check_in_log",
]);

/** @type {Record<string, { objectType: string, ownerType: string, ownerField: string, table: string|null }>} */
export const OWNERSHIP_REGISTRY = {
  workspace: { objectType: "workspace", ownerType: "organization", ownerField: "organization_id", table: "workspaces" },
  store: { objectType: "store", ownerType: "workspace", ownerField: "workspace_id", table: "stores" },
  customer: { objectType: "customer", ownerType: "workspace", ownerField: "workspace_id", table: "customer_profiles" },
  feedback: { objectType: "feedback", ownerType: "store", ownerField: "store_id", table: "feedback_records" },
  feedback_template: { objectType: "feedback_template", ownerType: "store", ownerField: "store_id", table: "feedback_templates" },
  event: { objectType: "event", ownerType: "store", ownerField: "store_id", table: "events" },
};

/** @type {readonly { fromType: string, field: string, toType: string, required?: boolean }[]} */
export const REFERENCE_REGISTRY = [
  { fromType: "feedback", field: "customer_id", toType: "customer" },
  { fromType: "feedback", field: "store_id", toType: "store", required: true },
  { fromType: "store", field: "workspace_id", toType: "workspace", required: true },
  { fromType: "customer", field: "workspace_id", toType: "workspace" },
  { fromType: "event_attendee", field: "customer_id", toType: "customer" },
];

/** @type {readonly { id: string, label: string, sources: string[], rebuild: string, maturity?: string }[]} */
export const DERIVED_STORES = [
  { id: "event_analytics", label: "Analytics Counters", sources: ["domain_events"], rebuild: "Re-aggregate from events" },
  { id: "workspace_search", label: "Search Results", sources: ["customer", "store", "feedback"], rebuild: "Live SQL query" },
  { id: "customer_activities", label: "Customer Timeline", sources: ["domain_events"], rebuild: "Event projection" },
  { id: "bos_local_store", label: "BOS Mock Store", sources: ["seed.js"], rebuild: "Migrate to API", maturity: "partial" },
];

export const SYNC_MECHANISM = "event_bus";

/** @type {readonly string[]} */
export const WORKSPACE_DATA_HIERARCHY = [
  "stores", "customers", "products", "services", "employees",
  "orders", "appointments", "feedback", "documents", "tasks", "events",
];

/** @param {string} objectType */
export function ownershipFor(objectType) {
  return OWNERSHIP_REGISTRY[objectType] ?? null;
}

/** @param {string} objectType */
export function referencesFrom(objectType) {
  return REFERENCE_REGISTRY.filter((r) => r.fromType === objectType);
}

/** @param {string} storeId */
export function isImmutableStore(storeId) {
  return IMMUTABLE_STORES.has(storeId);
}

/** @returns {string[]} */
export function conformanceGaps() {
  return ["cache_not_source"];
}
