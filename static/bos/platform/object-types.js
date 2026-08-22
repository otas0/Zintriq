/**
 * UI property schema for Zintriq modules.
 *
 * Domain authority (ownership, relationships, lifecycle):
 *   static/bos/platform/domain-model.js
 *   bos/domain.py
 *   docs/bos/DOMAIN_MODEL.md
 *
 * Object standards (behavior, interaction, API):
 *   static/bos/platform/object-standards.js
 *   bos/object_standards.py
 *   docs/bos/OBJECT_STANDARDS.md
 *
 * @typedef {'text'|'number'|'currency'|'date'|'status'|'tag'|'boolean'|'relationship'|'url'|'email'|'phone'|'select'} PropertyType
 * @typedef {{ key: string, label: string, type: PropertyType, required?: boolean, readonly?: boolean, options?: string[], relation?: string, multi?: boolean }} PropertyDef
 * @typedef {{ field: string, target: string, label: string, multi?: boolean, inverse?: string }} RelationDef
 * @typedef {{ type: string, collection: string, label: string, labelPlural: string, moduleId: string, modulePath: string, titleField: string, createLabel: string, taggable?: boolean, properties: PropertyDef[], relations: RelationDef[], filters?: string[], sortKey?: string }} ObjectTypeDef
 */

/** @type {Record<string, ObjectTypeDef>} */
export const OBJECT_TYPES = {
  organizations: {
    type: "organization",
    collection: "organizations",
    label: "Organization",
    labelPlural: "Organizations",
    moduleId: "organizations",
    modulePath: "/app/organizations",
    titleField: "name",
    createLabel: "New organization",
    taggable: false,
    sortKey: "name",
    filters: ["all", "active", "inactive"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "slug", label: "Slug", type: "text", readonly: true },
      { key: "status", label: "Status", type: "status", options: ["active", "inactive"] },
      { key: "createdAt", label: "Created", type: "date", readonly: true },
      { key: "updatedAt", label: "Updated", type: "date", readonly: true },
    ],
    relations: [
      { field: "_workspaces", target: "workspaces", label: "Workspaces", inverse: "organizationId" },
    ],
  },
  workspaces: {
    type: "workspace",
    collection: "workspaces",
    label: "Workspace",
    labelPlural: "Workspaces",
    moduleId: "workspaces",
    modulePath: "/app/workspaces",
    titleField: "name",
    createLabel: "New workspace",
    taggable: true,
    sortKey: "name",
    filters: ["all", "active", "archived"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "organizationId", label: "Organization", type: "relationship", relation: "organizations" },
      { key: "type", label: "Type", type: "text" },
      { key: "status", label: "Status", type: "status", options: ["active", "archived"] },
      { key: "createdAt", label: "Created", type: "date", readonly: true },
      { key: "updatedAt", label: "Updated", type: "date", readonly: true },
    ],
    relations: [
      { field: "organizationId", target: "organizations", label: "Organization" },
      { field: "_catalog", target: "catalog", label: "Catalog items", inverse: "workspaceId" },
      { field: "_assets", target: "assets", label: "Assets", inverse: "workspaceId" },
      { field: "_team", target: "team", label: "Team members", inverse: "workspaceIds" },
      { field: "_documents", target: "documents", label: "Documents", inverse: "workspaceId" },
      { field: "_operations", target: "operations", label: "Operations", inverse: "workspaceId" },
    ],
  },
  catalog: {
    type: "catalog_item",
    collection: "catalog",
    label: "Catalog item",
    labelPlural: "Catalog items",
    moduleId: "catalog",
    modulePath: "/app/catalog",
    titleField: "name",
    createLabel: "New item",
    taggable: true,
    sortKey: "name",
    filters: ["all", "active", "draft", "archived"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "sku", label: "SKU", type: "text" },
      { key: "category", label: "Category", type: "text" },
      { key: "price", label: "Price", type: "currency" },
      { key: "workspaceId", label: "Workspace", type: "relationship", relation: "workspaces" },
      { key: "status", label: "Status", type: "status", options: ["active", "draft", "archived"] },
      { key: "updatedAt", label: "Updated", type: "date", readonly: true },
    ],
    relations: [
      { field: "workspaceId", target: "workspaces", label: "Workspace" },
      { field: "tagIds", target: "tags", label: "Tags", multi: true },
      { field: "_transactions", target: "transactions", label: "Transactions", inverse: "catalogItemIds" },
    ],
  },
  customers: {
    type: "customer",
    collection: "customers",
    label: "Customer",
    labelPlural: "Customers",
    moduleId: "customers",
    modulePath: "/app/customers",
    titleField: "name",
    createLabel: "New customer",
    taggable: true,
    sortKey: "name",
    filters: ["all", "active", "inactive", "blocked", "archived"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "email", label: "Email", type: "email", required: true },
      { key: "phone", label: "Phone", type: "phone" },
      { key: "workspaceId", label: "Workspace", type: "relationship", relation: "workspaces" },
      { key: "status", label: "Status", type: "status", options: ["active", "inactive", "blocked", "archived"] },
      { key: "updatedAt", label: "Updated", type: "date", readonly: true },
    ],
    relations: [
      { field: "workspaceId", target: "workspaces", label: "Workspace" },
      { field: "tagIds", target: "tags", label: "Tags", multi: true },
      { field: "_transactions", target: "transactions", label: "Transactions", inverse: "customerId" },
      { field: "_feedback", target: "feedback", label: "Feedback", inverse: "customerId" },
    ],
  },
  transactions: {
    type: "transaction",
    collection: "transactions",
    label: "Transaction",
    labelPlural: "Transactions",
    moduleId: "transactions",
    modulePath: "/app/transactions",
    titleField: "reference",
    createLabel: "New transaction",
    taggable: true,
    sortKey: "date",
    filters: ["all", "completed", "pending"],
    properties: [
      { key: "reference", label: "Reference", type: "text", required: true },
      { key: "customerId", label: "Customer", type: "relationship", relation: "customers" },
      { key: "workspaceId", label: "Workspace", type: "relationship", relation: "workspaces" },
      { key: "catalogItemIds", label: "Catalog items", type: "relationship", relation: "catalog", multi: true },
      { key: "amount", label: "Amount", type: "currency" },
      { key: "status", label: "Status", type: "status", options: ["completed", "pending"] },
      { key: "date", label: "Date", type: "date" },
    ],
    relations: [
      { field: "customerId", target: "customers", label: "Customer" },
      { field: "workspaceId", target: "workspaces", label: "Workspace" },
      { field: "catalogItemIds", target: "catalog", label: "Catalog items", multi: true },
      { field: "tagIds", target: "tags", label: "Tags", multi: true },
    ],
  },
  team: {
    type: "team_member",
    collection: "team",
    label: "Team member",
    labelPlural: "Team members",
    moduleId: "team",
    modulePath: "/app/team",
    titleField: "name",
    createLabel: "Invite member",
    taggable: true,
    sortKey: "name",
    filters: ["all", "active", "invited"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "email", label: "Email", type: "email", required: true },
      { key: "role", label: "Role", type: "select", options: ["owner", "admin", "member"] },
      { key: "workspaceIds", label: "Workspaces", type: "relationship", relation: "workspaces", multi: true },
      { key: "status", label: "Status", type: "status", options: ["active", "invited"] },
    ],
    relations: [
      { field: "workspaceIds", target: "workspaces", label: "Workspaces", multi: true },
      { field: "_operations", target: "operations", label: "Operations", inverse: "assigneeIds" },
    ],
  },
  operations: {
    type: "operation",
    collection: "operations",
    label: "Operation",
    labelPlural: "Operations",
    moduleId: "operations",
    modulePath: "/app/operations",
    titleField: "title",
    createLabel: "New operation",
    taggable: true,
    sortKey: "dueAt",
    filters: ["all", "open", "in_progress", "done"],
    properties: [
      { key: "title", label: "Title", type: "text", required: true },
      { key: "workspaceId", label: "Workspace", type: "relationship", relation: "workspaces" },
      { key: "assigneeIds", label: "Assignees", type: "relationship", relation: "team", multi: true },
      { key: "assetIds", label: "Assets", type: "relationship", relation: "assets", multi: true },
      { key: "priority", label: "Priority", type: "select", options: ["low", "medium", "high"] },
      { key: "status", label: "Status", type: "status", options: ["open", "in_progress", "done"] },
      { key: "dueAt", label: "Due", type: "date" },
    ],
    relations: [
      { field: "workspaceId", target: "workspaces", label: "Workspace" },
      { field: "assigneeIds", target: "team", label: "Assignees", multi: true },
      { field: "assetIds", target: "assets", label: "Assets", multi: true },
      { field: "tagIds", target: "tags", label: "Tags", multi: true },
    ],
  },
  documents: {
    type: "document",
    collection: "documents",
    label: "Document",
    labelPlural: "Documents",
    moduleId: "documents",
    modulePath: "/app/documents",
    titleField: "name",
    createLabel: "Upload document",
    taggable: true,
    sortKey: "name",
    filters: ["all", "active", "archived", "pdf", "doc"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "type", label: "Type", type: "select", options: ["pdf", "doc", "image"] },
      { key: "size", label: "Size", type: "text" },
      { key: "workspaceId", label: "Workspace", type: "relationship", relation: "workspaces" },
      { key: "status", label: "Status", type: "status", options: ["active", "archived"] },
      { key: "updatedAt", label: "Updated", type: "date", readonly: true },
    ],
    relations: [
      { field: "workspaceId", target: "workspaces", label: "Workspace" },
      { field: "tagIds", target: "tags", label: "Tags", multi: true },
    ],
  },
  assets: {
    type: "asset",
    collection: "assets",
    label: "Asset",
    labelPlural: "Assets",
    moduleId: "assets",
    modulePath: "/app/assets",
    titleField: "name",
    createLabel: "New asset",
    taggable: true,
    sortKey: "name",
    filters: ["all", "active", "archived", "qr", "file"],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "type", label: "Type", type: "select", options: ["qr", "file", "image"] },
      { key: "url", label: "URL", type: "url" },
      { key: "workspaceId", label: "Workspace", type: "relationship", relation: "workspaces" },
      { key: "status", label: "Status", type: "status", options: ["active", "archived"] },
      { key: "updatedAt", label: "Updated", type: "date", readonly: true },
    ],
    relations: [
      { field: "workspaceId", target: "workspaces", label: "Workspace" },
      { field: "_operations", target: "operations", label: "Operations", inverse: "assetIds" },
      { field: "tagIds", target: "tags", label: "Tags", multi: true },
    ],
  },
  tags: {
    type: "tag",
    collection: "tags",
    label: "Tag",
    labelPlural: "Tags",
    moduleId: "tags",
    modulePath: "/app/tags",
    titleField: "name",
    createLabel: "New tag",
    taggable: false,
    sortKey: "name",
    filters: [],
    properties: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "color", label: "Color", type: "select", options: ["info", "warning", "danger", "muted"] },
      { key: "status", label: "Status", type: "status", options: ["active", "archived"] },
    ],
    relations: [],
  },
};

/** Generic relation field registry for reverse lookups. */
export const RELATION_FIELDS = [
  { field: "organizationId", target: "organizations" },
  { field: "workspaceId", target: "workspaces" },
  { field: "workspaceIds", target: "workspaces", multi: true },
  { field: "customerId", target: "customers" },
  { field: "catalogItemIds", target: "catalog", multi: true },
  { field: "assigneeIds", target: "team", multi: true },
  { field: "assetIds", target: "assets", multi: true },
  { field: "tagIds", target: "tags", multi: true },
];

export const TAGGABLE_COLLECTIONS = Object.values(OBJECT_TYPES)
  .filter((t) => t.taggable)
  .map((t) => t.collection);

export function getObjectType(collection) {
  return OBJECT_TYPES[collection] || null;
}

export function getObjectTitle(record, typeDef) {
  if (!record) return "—";
  const field = typeDef?.titleField || "name";
  return String(record[field] || record.name || record.title || record.reference || record.id);
}

export function collectionForType(type) {
  return Object.values(OBJECT_TYPES).find((t) => t.type === type)?.collection || null;
}
