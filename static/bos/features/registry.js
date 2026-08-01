import { OBJECT_TYPES } from "../platform/object-types.js";
import * as store from "../core/store.js";
import { statusBadge, tag } from "../components/index.js";

/** Custom column renderers keyed by collection.field */
const COLUMN_RENDERERS = {
  "catalog.price": (r) => `$${Number(r.price).toFixed(2)}`,
  "catalog.status": (r) => statusBadge(String(r.status)),
  "customers.status": (r) => statusBadge(String(r.status)),
  "customers.tagIds": (r) => (r.tagIds || []).map((id) => tag(store.resolveRelation("tags", id))).join(" "),
  "transactions.customerId": (r) => store.resolveRelation("customers", String(r.customerId)),
  "transactions.catalogItemIds": (r) => String((r.catalogItemIds || []).length || "—"),
  "transactions.amount": (r) => `$${Number(r.amount).toFixed(2)}`,
  "transactions.status": (r) => statusBadge(String(r.status)),
  "transactions.date": (r) => String(r.date || "").slice(0, 10),
  "team.status": (r) => statusBadge(String(r.status)),
  "operations.status": (r) => statusBadge(String(r.status)),
  "operations.dueAt": (r) => String(r.dueAt || "").slice(0, 10),
  "documents.updatedAt": (r) => String(r.updatedAt || "").slice(0, 10),
  "assets.workspaceId": (r) => store.resolveRelation("workspaces", String(r.workspaceId)),
  "assets.status": (r) => statusBadge(String(r.status)),
  "tags.name": (r) => tag(String(r.name), String(r.color)),
  "tags.id": (r) => String(store.tagUsageCount(String(r.id))),
  "tags.status": (r) => statusBadge(String(r.status)),
  "workspaces.organizationId": (r) => store.resolveRelation("organizations", String(r.organizationId)),
  "workspaces.status": (r) => statusBadge(String(r.status)),
  "organizations.status": (r) => statusBadge(String(r.status)),
};

/** Which properties appear as table columns per collection */
const COLUMN_KEYS = {
  organizations: ["name", "slug", "status"],
  workspaces: ["name", "organizationId", "type", "status"],
  catalog: ["name", "sku", "category", "price", "status"],
  customers: ["name", "email", "status", "tagIds"],
  transactions: ["reference", "customerId", "catalogItemIds", "amount", "status", "date"],
  team: ["name", "email", "role", "status"],
  operations: ["title", "priority", "status", "dueAt"],
  documents: ["name", "type", "size", "updatedAt"],
  assets: ["name", "type", "workspaceId", "status"],
  tags: ["name", "id", "status"],
};

function buildColumns(collection, typeDef) {
  const keys = COLUMN_KEYS[collection] || typeDef.properties.slice(0, 5).map((p) => p.key);
  return keys.map((key) => {
    const prop = typeDef.properties.find((p) => p.key === key);
    const label = prop?.label || key;
    const renderKey = `${collection}.${key}`;
    const render = COLUMN_RENDERERS[renderKey];
    return render ? { key, label, render } : { key, label };
  });
}

function buildModuleConfig(collection, typeDef) {
  return {
    collection,
    label: typeDef.label,
    labelPlural: typeDef.labelPlural,
    createLabel: typeDef.createLabel,
    filters: typeDef.filters || [],
    sortKey: typeDef.sortKey || "name",
    columns: buildColumns(collection, typeDef),
    /** @deprecated fields/relations kept for batch-move eligibility; source of truth is OBJECT_TYPES */
    fields: typeDef.properties.filter((p) => !p.readonly).map((p) => ({
      key: p.key,
      label: p.label,
      type: p.type === "relationship" ? "relation" : p.type === "select" || p.type === "status" ? "select" : p.type,
      relation: p.relation,
      options: p.options,
      required: p.required,
    })),
    relations: (typeDef.relations || []).filter((r) => r.field && !r.field.startsWith("_")).map((r) => ({
      key: r.field,
      collection: r.target,
      label: r.label,
      multi: r.multi,
    })),
  };
}

/** @type {Record<string, object>} — derived from OBJECT_TYPES (single source of truth) */
export const MODULE_REGISTRY = Object.fromEntries(
  Object.entries(OBJECT_TYPES).map(([collection, typeDef]) => [
    typeDef.moduleId,
    buildModuleConfig(collection, typeDef),
  ])
);

export const MODULE_NAV = [
  { id: "home", label: "Home", icon: "⌂", path: "/app" },
  { id: "organizations", label: "Organization", icon: "◉", path: "/app/organizations" },
  { id: "workspaces", label: "Workspaces", icon: "◫", path: "/app/workspaces" },
  { id: "catalog", label: "Catalog", icon: "▦", path: "/app/catalog" },
  { id: "transactions", label: "Transactions", icon: "⇄", path: "/app/transactions" },
  { id: "customers", label: "Customers", icon: "◎", path: "/app/customers" },
  { id: "team", label: "Team", icon: "◈", path: "/app/team" },
  { id: "operations", label: "Operations", icon: "⚙", path: "/app/operations" },
  { id: "documents", label: "Documents", icon: "▤", path: "/app/documents" },
  { id: "assets", label: "Assets", icon: "⬡", path: "/app/assets" },
  { id: "tags", label: "Tags", icon: "◆", path: "/app/tags" },
];
