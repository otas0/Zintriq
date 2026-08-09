/**
 * Business OS Platform Specification — registry mirror (JavaScript).
 *
 * Spec: docs/bos/PLATFORM_SPECIFICATION.md
 * Backend mirror: bos/platform_spec.py
 */

/** @typedef {'implemented'|'partial'|'planned'} PlatformMaturity */

/**
 * @typedef {Object} PlatformSectionDef
 * @property {string} id
 * @property {string} label
 * @property {boolean} [required]
 */

/**
 * @typedef {Object} PlatformConformanceDef
 * @property {boolean} shellIntegrated
 * @property {boolean} emitsEvents
 * @property {boolean} usesSharedComponents
 * @property {boolean} drawerDetail
 * @property {boolean} batchOperations
 * @property {boolean} globalSearchRegistered
 * @property {boolean} noDirectNotifications
 * @property {boolean} apiBacked
 * @property {boolean} settingsSection
 * @property {boolean} activitySection
 */

/**
 * @typedef {Object} PlatformSpecDef
 * @property {string} id
 * @property {string} label
 * @property {string[]} operatesOn
 * @property {PlatformSectionDef[]} sections
 * @property {string[]} [backend]
 * @property {string[]} [frontend]
 * @property {PlatformMaturity} maturity
 * @property {PlatformConformanceDef} conformance
 * @property {string} [notes]
 */

/** @type {readonly string[]} */
export const PLATFORM_SECTIONS = [
  "overview", "object_list", "detail", "activity", "analytics", "settings", "integrations",
];

/** @type {ReadonlySet<string>} */
export const REQUIRED_SECTIONS = new Set(["overview", "object_list", "detail", "settings"]);

/** @type {ReadonlySet<string>} */
export const REQUIRED_BATCH_ACTIONS = new Set([
  "select", "select_all", "archive", "delete", "export", "add_tags",
]);

/** @type {ReadonlySet<string>} */
export const FOUNDATION_SERVICES = new Set([
  "events", "notifications", "search", "permissions", "files", "settings_framework",
]);

/** @type {ReadonlySet<string>} */
export const CORE_SERVICES = new Set([
  "shell", "navigation", "workspace", "auth", "authorization",
]);

/** @type {readonly PlatformSectionDef[]} */
export const STANDARD_SECTIONS = [
  { id: "overview", label: "Overview", required: true },
  { id: "object_list", label: "Object List", required: true },
  { id: "detail", label: "Detail", required: true },
  { id: "activity", label: "Activity" },
  { id: "analytics", label: "Analytics" },
  { id: "settings", label: "Settings", required: true },
  { id: "integrations", label: "Integrations" },
];

/** @type {Record<string, PlatformSpecDef>} */
export const PLATFORM_REGISTRY = {
  workspaces: {
    id: "workspaces", label: "Workspace Platform",
    operatesOn: ["workspace", "store"],
    sections: [
      { id: "overview", label: "Overview", required: true },
      { id: "object_list", label: "Stores" },
      { id: "detail", label: "Members" },
      { id: "activity", label: "Activity" },
      { id: "settings", label: "Settings", required: true },
    ],
    backend: ["workspace_platform.py"],
    frontend: ["static/bos/features/workspaces-page.js"],
    maturity: "implemented",
    conformance: {
      shellIntegrated: true, emitsEvents: true, usesSharedComponents: true,
      drawerDetail: false, batchOperations: false, globalSearchRegistered: false,
      noDirectNotifications: true, apiBacked: true, settingsSection: true, activitySection: true,
    },
  },
  customers: {
    id: "customers", label: "Customer Platform",
    operatesOn: ["customer"],
    sections: [
      { id: "overview", label: "Overview", required: true },
      { id: "object_list", label: "Customers", required: true },
      { id: "detail", label: "Detail", required: true },
      { id: "activity", label: "Activity" },
      { id: "settings", label: "Settings", required: true },
    ],
    backend: ["customer_platform.py"],
    frontend: ["static/bos/features/customers-page.js"],
    maturity: "implemented",
    conformance: {
      shellIntegrated: true, emitsEvents: true, usesSharedComponents: true,
      drawerDetail: true, batchOperations: true, globalSearchRegistered: true,
      noDirectNotifications: true, apiBacked: true, settingsSection: true, activitySection: true,
    },
  },
  feedback: {
    id: "feedback", label: "Feedback Platform",
    operatesOn: ["feedback", "feedback_template"],
    sections: [
      { id: "overview", label: "Overview", required: true },
      { id: "object_list", label: "Templates" },
      { id: "object_list", label: "Inbox", required: true },
      { id: "analytics", label: "Analytics" },
      { id: "settings", label: "Settings", required: true },
    ],
    backend: ["feedback_platform.py"],
    frontend: ["static/bos/features/feedback-page.js"],
    maturity: "implemented",
    conformance: {
      shellIntegrated: true, emitsEvents: true, usesSharedComponents: true,
      drawerDetail: true, batchOperations: false, globalSearchRegistered: true,
      noDirectNotifications: true, apiBacked: true, settingsSection: true, activitySection: false,
    },
    notes: "QR is publish channel only.",
  },
  qr: {
    id: "qr", label: "QR Platform",
    operatesOn: ["store", "qr", "product", "event"],
    sections: [
      { id: "object_list", label: "Stores", required: true },
      { id: "detail", label: "QR Assets" },
      { id: "settings", label: "Store Settings" },
    ],
    backend: ["app.py"],
    frontend: ["templates/owner/"],
    maturity: "implemented",
    conformance: {
      shellIntegrated: true, emitsEvents: false, usesSharedComponents: false,
      drawerDetail: false, batchOperations: false, globalSearchRegistered: false,
      noDirectNotifications: true, apiBacked: true, settingsSection: true, activitySection: false,
    },
  },
  catalog: {
    id: "catalog", label: "Product Platform",
    operatesOn: ["product", "catalog"],
    sections: STANDARD_SECTIONS,
    frontend: ["static/bos/features/module-page.js"],
    maturity: "partial",
    conformance: {
      shellIntegrated: true, emitsEvents: false, usesSharedComponents: true,
      drawerDetail: true, batchOperations: true, globalSearchRegistered: false,
      noDirectNotifications: true, apiBacked: false, settingsSection: false, activitySection: false,
    },
  },
  transactions: {
    id: "transactions", label: "Order Platform",
    operatesOn: ["order", "transaction"],
    sections: STANDARD_SECTIONS,
    frontend: ["static/bos/features/module-page.js"],
    maturity: "partial",
    conformance: {
      shellIntegrated: true, emitsEvents: false, usesSharedComponents: true,
      drawerDetail: true, batchOperations: true, globalSearchRegistered: false,
      noDirectNotifications: true, apiBacked: false, settingsSection: false, activitySection: false,
    },
  },
  analytics: {
    id: "analytics", label: "Analytics Platform",
    operatesOn: [],
    sections: [
      { id: "overview", label: "Overview", required: true },
      { id: "analytics", label: "Analytics", required: true },
    ],
    backend: ["event_platform.py"],
    maturity: "partial",
    conformance: {
      shellIntegrated: true, emitsEvents: false, usesSharedComponents: true,
      drawerDetail: false, batchOperations: false, globalSearchRegistered: false,
      noDirectNotifications: true, apiBacked: true, settingsSection: false, activitySection: false,
    },
    notes: "Event consumer only.",
  },
};

/** @param {string} platformId @returns {PlatformSpecDef|null} */
export function platformSpec(platformId) {
  return PLATFORM_REGISTRY[platformId] ?? null;
}

/** @param {string} platformId */
export function isPlatformComplete(platformId) {
  const spec = PLATFORM_REGISTRY[platformId];
  if (!spec || spec.maturity !== "implemented") return false;
  const sectionIds = new Set(spec.sections.map((s) => s.id));
  for (const req of REQUIRED_SECTIONS) {
    if (!sectionIds.has(req)) return false;
  }
  const c = spec.conformance;
  return c.shellIntegrated && c.emitsEvents && c.usesSharedComponents
    && c.apiBacked && c.noDirectNotifications && c.settingsSection;
}

/** @param {string} platformId @returns {string[]} */
export function conformanceGaps(platformId) {
  const spec = PLATFORM_REGISTRY[platformId];
  if (!spec) return ["Platform not registered"];
  const gaps = [];
  const checks = [
    ["shellIntegrated", "Integrate with Application Shell"],
    ["emitsEvents", "Emit domain events"],
    ["usesSharedComponents", "Use shared components"],
    ["drawerDetail", "Drawer-first detail"],
    ["batchOperations", "Batch operations"],
    ["globalSearchRegistered", "Global Search registration"],
    ["noDirectNotifications", "No direct notifications"],
    ["apiBacked", "Backend API"],
    ["settingsSection", "Settings section"],
    ["activitySection", "Activity section"],
  ];
  for (const [key, label] of checks) {
    if (!spec.conformance[key]) gaps.push(label);
  }
  const sectionIds = new Set(spec.sections.map((s) => s.id));
  for (const req of REQUIRED_SECTIONS) {
    if (!sectionIds.has(req)) gaps.push(`Missing section: ${req}`);
  }
  return gaps;
}
