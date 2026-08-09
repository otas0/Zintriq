/**
 * Business OS Domain Model — canonical registry (JavaScript mirror).
 *
 * Spec: docs/bos/DOMAIN_MODEL.md
 * Backend mirror: bos/domain.py
 *
 * Defines ownership, references, lifecycle, and platform mapping.
 * NOT UI schema (see object-types.js) and NOT database DDL.
 */

/** @typedef {'implemented'|'partial'|'planned'} Maturity */

/**
 * @typedef {Object} DomainObjectDef
 * @property {string} type
 * @property {string} label
 * @property {string|null} collection
 * @property {string} ownerType
 * @property {string|null} ownerField
 * @property {string[]} references
 * @property {string} platform
 * @property {string[]} lifecycle
 * @property {string[]} behaviors
 * @property {boolean} ownsData
 * @property {Maturity} maturity
 * @property {string|null} [table]
 */

/** @type {readonly string[]} */
export const LIFECYCLE_DEFAULT = ["created", "active", "updated", "archived", "restored", "deleted"];

/** @type {readonly string[]} */
export const PERMISSION_ACTIONS = [
  "create", "read", "update", "archive", "delete", "export", "assign", "reply", "publish",
];

/** @type {readonly string[]} */
export const SHARED_BEHAVIORS = [
  "activity", "notes", "attachments", "tags", "search", "filters",
  "archive", "restore", "permissions", "audit",
];

/** @type {ReadonlySet<string>} */
export const ROOT_TYPES = new Set(["user", "organization", "workspace"]);

/** QR may point to these targets — QR never owns them */
/** @type {ReadonlySet<string>} */
export const QR_TARGET_TYPES = new Set([
  "product", "feedback_template", "event", "store", "check_in", "business_card",
]);

/** @type {Record<string, DomainObjectDef>} */
export const DOMAIN_OBJECTS = {
  user: {
    type: "user", label: "User", collection: null,
    ownerType: "none", ownerField: null, references: [],
    platform: "auth", lifecycle: ["active"], behaviors: ["permissions", "audit"],
    ownsData: true, maturity: "implemented", table: "users",
  },
  organization: {
    type: "organization", label: "Organization", collection: "organizations",
    ownerType: "user", ownerField: "ownerId", references: ["user"],
    platform: "organizations", lifecycle: ["active", "inactive"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "partial", table: "organizations",
  },
  workspace: {
    type: "workspace", label: "Workspace", collection: "workspaces",
    ownerType: "organization", ownerField: "organizationId", references: ["organization"],
    platform: "workspaces", lifecycle: ["active", "archived", "suspended"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "implemented", table: "workspaces",
  },
  store: {
    type: "store", label: "Store", collection: null,
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace"],
    platform: "qr_workspace", lifecycle: ["draft", "active", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "implemented", table: "stores",
  },
  customer: {
    type: "customer", label: "Customer", collection: "customers",
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace", "store"],
    platform: "customers", lifecycle: ["active", "inactive", "blocked", "archived"],
    behaviors: [...SHARED_BEHAVIORS, "export", "timeline", "files"],
    ownsData: true, maturity: "implemented", table: "customer_profiles",
  },
  product: {
    type: "product", label: "Product", collection: "catalog",
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace"],
    platform: "catalog", lifecycle: ["draft", "active", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "partial", table: "items",
  },
  service: {
    type: "service", label: "Service", collection: null,
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace"],
    platform: "catalog", lifecycle: ["draft", "active", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "planned",
  },
  employee: {
    type: "employee", label: "Employee", collection: "team",
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace", "user"],
    platform: "team", lifecycle: ["invited", "active", "inactive", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "partial",
  },
  qr: {
    type: "qr", label: "QR", collection: null,
    ownerType: "store", ownerField: "storeId", references: ["store"],
    platform: "qr", lifecycle: ["draft", "active", "archived"],
    behaviors: ["publish", "archive", "search"], ownsData: false, maturity: "implemented", table: "qr_codes",
  },
  feedback_template: {
    type: "feedback_template", label: "Feedback Template", collection: null,
    ownerType: "store", ownerField: "storeId", references: ["workspace", "store"],
    platform: "feedback", lifecycle: ["draft", "published", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "implemented", table: "feedback_templates",
  },
  feedback: {
    type: "feedback", label: "Feedback", collection: null,
    ownerType: "store", ownerField: "storeId",
    references: ["workspace", "store", "feedback_template", "customer", "qr"],
    platform: "feedback", lifecycle: ["new", "read", "replied", "archived", "hidden", "flagged"],
    behaviors: [...SHARED_BEHAVIORS, "reply", "export"],
    ownsData: true, maturity: "implemented", table: "feedback_records",
  },
  event: {
    type: "event", label: "Event", collection: null,
    ownerType: "store", ownerField: "storeId",
    references: ["workspace", "store", "customer", "employee", "qr"],
    platform: "qr", lifecycle: ["draft", "published", "completed", "archived"],
    behaviors: [...SHARED_BEHAVIORS, "export"], ownsData: true, maturity: "implemented", table: "events",
  },
  appointment: {
    type: "appointment", label: "Appointment", collection: null,
    ownerType: "store", ownerField: "storeId",
    references: ["customer", "employee", "service", "store", "workspace"],
    platform: "booking", lifecycle: ["scheduled", "confirmed", "completed", "cancelled", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "planned",
  },
  order: {
    type: "order", label: "Order", collection: "transactions",
    ownerType: "workspace", ownerField: "workspaceId",
    references: ["customer", "product", "service", "store", "employee", "workspace"],
    platform: "transactions", lifecycle: ["pending", "completed", "refunded", "archived"],
    behaviors: [...SHARED_BEHAVIORS, "export"], ownsData: true, maturity: "planned",
  },
  membership: {
    type: "membership", label: "Membership", collection: null,
    ownerType: "workspace", ownerField: "workspaceId", references: ["customer", "workspace"],
    platform: "membership", lifecycle: ["active", "expiring", "expired", "cancelled", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "planned",
  },
  inventory: {
    type: "inventory", label: "Inventory", collection: null,
    ownerType: "store", ownerField: "storeId", references: ["product", "store", "workspace"],
    platform: "inventory", lifecycle: ["active", "low", "out", "archived"],
    behaviors: ["search", "archive", "audit"], ownsData: true, maturity: "planned",
  },
  document: {
    type: "document", label: "Document", collection: "documents",
    ownerType: "workspace", ownerField: "workspaceId",
    references: ["workspace", "customer", "employee", "product", "order", "event"],
    platform: "documents", lifecycle: ["active", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "partial", table: "customer_files",
  },
  notification: {
    type: "notification", label: "Notification", collection: null,
    ownerType: "user", ownerField: "userId", references: [],
    platform: "notifications", lifecycle: ["unread", "read", "dismissed"],
    behaviors: ["read", "search"], ownsData: false, maturity: "partial",
  },
  task: {
    type: "task", label: "Task", collection: "operations",
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace"],
    platform: "operations", lifecycle: ["open", "in_progress", "done", "archived"],
    behaviors: [...SHARED_BEHAVIORS, "assign"], ownsData: true, maturity: "partial",
  },
  automation: {
    type: "automation", label: "Automation", collection: null,
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace"],
    platform: "automation", lifecycle: ["draft", "active", "paused", "archived"],
    behaviors: [...SHARED_BEHAVIORS], ownsData: true, maturity: "planned",
  },
  analytics: {
    type: "analytics", label: "Analytics", collection: null,
    ownerType: "none", ownerField: null, references: [],
    platform: "analytics", lifecycle: [],
    behaviors: ["read", "export"], ownsData: false, maturity: "partial",
  },
  settings: {
    type: "settings", label: "Settings", collection: null,
    ownerType: "workspace", ownerField: "workspaceId", references: ["workspace", "store"],
    platform: "settings", lifecycle: ["active"],
    behaviors: ["read", "update"], ownsData: true, maturity: "partial",
  },
};

/** @type {Record<string, { id: string, label: string, operatesOn: string[], readOnly?: boolean }>} */
export const PLATFORMS = {
  auth: { id: "auth", label: "Authentication", operatesOn: ["user"] },
  organizations: { id: "organizations", label: "Organization", operatesOn: ["organization"] },
  workspaces: { id: "workspaces", label: "Workspaces", operatesOn: ["workspace"] },
  qr_experiences: { id: "qr_experiences", label: "Experiences", operatesOn: ["experience", "settings"] },
  qr: { id: "qr", label: "QR Platform", operatesOn: ["qr", "event", "product", "store"] },
  customers: { id: "customers", label: "Customer Platform", operatesOn: ["customer"] },
  feedback: { id: "feedback", label: "Feedback Platform", operatesOn: ["feedback_template", "feedback", "settings"] },
  catalog: { id: "catalog", label: "Catalog", operatesOn: ["product", "service"] },
  team: { id: "team", label: "Team", operatesOn: ["employee"] },
  documents: { id: "documents", label: "Documents", operatesOn: ["document"] },
  operations: { id: "operations", label: "Operations", operatesOn: ["task"] },
  transactions: { id: "transactions", label: "Transactions", operatesOn: ["order"] },
  notifications: { id: "notifications", label: "Notifications", operatesOn: ["notification"] },
  analytics: { id: "analytics", label: "Analytics", operatesOn: ["analytics"], readOnly: true },
  booking: { id: "booking", label: "Booking", operatesOn: ["appointment"] },
  membership: { id: "membership", label: "Membership", operatesOn: ["membership"] },
  inventory: { id: "inventory", label: "Inventory", operatesOn: ["inventory"] },
  automation: { id: "automation", label: "Automation Engine", operatesOn: ["automation"] },
  settings: { id: "settings", label: "Settings", operatesOn: ["settings"] },
};

/** @type {readonly string[]} */
export const NON_NEGOTIABLE_RULES = [
  "One object = one responsibility.",
  "Every object has exactly one owner.",
  "Relationships use references — never duplicated data.",
  "Platforms operate on objects; they do not own business domain data.",
  "Shared behaviors must remain consistent across all objects.",
  "New modules must update docs/bos/DOMAIN_MODEL.md and both code registries.",
];

/** @param {string} typeKey @returns {DomainObjectDef|null} */
export function getDomainObject(typeKey) {
  return DOMAIN_OBJECTS[typeKey] || null;
}

/** @param {string} typeKey */
export function isRootType(typeKey) {
  return ROOT_TYPES.has(typeKey);
}

/** @param {string} typeKey @returns {boolean} */
export function ownsData(typeKey) {
  const obj = getDomainObject(typeKey);
  return obj ? obj.ownsData : false;
}

/** @param {string} sourceType @param {string} targetType */
export function validateReference(sourceType, targetType) {
  const source = getDomainObject(sourceType);
  if (!source) return false;
  return source.references.includes(targetType) || targetType === "workspace";
}

/** @param {string} platformId @returns {DomainObjectDef[]} */
export function objectsForPlatform(platformId) {
  return Object.values(DOMAIN_OBJECTS).filter((o) => o.platform === platformId);
}

/** Map BOS collection name → domain type key */
/** @type {Record<string, string>} */
export const COLLECTION_TO_DOMAIN = {
  organizations: "organization",
  workspaces: "workspace",
  catalog: "product",
  customers: "customer",
  transactions: "order",
  team: "employee",
  operations: "task",
  documents: "document",
  assets: "qr",
};

/** @param {string} collection */
export function domainTypeForCollection(collection) {
  return COLLECTION_TO_DOMAIN[collection] || null;
}

/** @param {string} collection @returns {DomainObjectDef|null} */
export function getDomainForCollection(collection) {
  const typeKey = domainTypeForCollection(collection);
  return typeKey ? getDomainObject(typeKey) : null;
}
