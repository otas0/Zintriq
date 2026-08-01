/** @typedef {import('../core/store.js').BosRecord} BosRecord */

const iso = (daysAgo = 0) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString();
};

/** @type {Record<string, BosRecord[]>} */
export const SEED_DATA = {
  organizations: [
    {
      id: "org-1",
      name: "My Organization",
      slug: "my-organization",
      status: "active",
      createdAt: iso(30),
      updatedAt: iso(1),
    },
  ],
  workspaces: [
    {
      id: "ws-1",
      organizationId: "org-1",
      name: "Main Workspace",
      slug: "main-workspace",
      type: "general",
      status: "active",
      tagIds: ["tag-2"],
      createdAt: iso(28),
      updatedAt: iso(0),
    },
    {
      id: "ws-2",
      organizationId: "org-1",
      name: "Regional Office",
      slug: "regional-office",
      type: "general",
      status: "active",
      tagIds: [],
      createdAt: iso(14),
      updatedAt: iso(3),
    },
  ],
  catalog: [
    { id: "cat-1", workspaceId: "ws-1", name: "Standard Service Package", sku: "SRV-001", status: "active", price: 99, category: "Services", tagIds: ["tag-2"], updatedAt: iso(1) },
    { id: "cat-2", workspaceId: "ws-1", name: "Premium Consultation", sku: "SRV-002", status: "active", price: 249, category: "Services", tagIds: [], updatedAt: iso(3) },
    { id: "cat-3", workspaceId: "ws-2", name: "Physical Product A", sku: "PRD-101", status: "draft", price: 45.5, category: "Products", tagIds: ["tag-1"], updatedAt: iso(5) },
    { id: "cat-4", workspaceId: "ws-2", name: "Physical Product B", sku: "PRD-102", status: "active", price: 78, category: "Products", tagIds: [], updatedAt: iso(2) },
    { id: "cat-5", workspaceId: "ws-1", name: "Add-on Module", sku: "ADD-010", status: "archived", price: 19, category: "Add-ons", tagIds: ["tag-4"], updatedAt: iso(14) },
  ],
  customers: [
    { id: "cus-1", name: "Acme Corp", email: "billing@acme.example", phone: "+1 555-0100", status: "active", tagIds: ["tag-2"], updatedAt: iso(1) },
    { id: "cus-2", name: "Northwind LLC", email: "accounts@northwind.example", phone: "+1 555-0101", status: "active", tagIds: ["tag-3"], updatedAt: iso(3) },
    { id: "cus-3", name: "Globex Inc", email: "hello@globex.example", status: "inactive", tagIds: [], updatedAt: iso(10) },
  ],
  transactions: [
    { id: "txn-1", reference: "TXN-2026-001", customerId: "cus-1", workspaceId: "ws-1", catalogItemIds: ["cat-1", "cat-2"], amount: 1240, status: "completed", tagIds: ["tag-2"], date: iso(0) },
    { id: "txn-2", reference: "TXN-2026-002", customerId: "cus-2", workspaceId: "ws-1", catalogItemIds: ["cat-2"], amount: 580, status: "pending", tagIds: [], date: iso(1) },
    { id: "txn-3", reference: "TXN-2026-003", customerId: "cus-3", workspaceId: "ws-2", catalogItemIds: ["cat-3"], amount: 3200, status: "completed", tagIds: [], date: iso(4) },
  ],
  team: [
    { id: "tm-1", name: "Alex Morgan", email: "alex@example.com", role: "owner", status: "active", workspaceIds: ["ws-1", "ws-2"] },
    { id: "tm-2", name: "Jordan Lee", email: "jordan@example.com", role: "admin", status: "active", workspaceIds: ["ws-1"] },
    { id: "tm-3", name: "Sam Rivera", email: "sam@example.com", role: "member", status: "invited", workspaceIds: ["ws-2"] },
  ],
  operations: [
    { id: "op-1", title: "Monthly inventory review", workspaceId: "ws-1", assigneeIds: ["tm-1", "tm-2"], assetIds: ["ast-2"], status: "in_progress", priority: "medium", tagIds: ["tag-1"], dueAt: iso(-2) },
    { id: "op-2", title: "Update catalog pricing", workspaceId: "ws-1", assigneeIds: ["tm-2"], assetIds: [], status: "open", priority: "high", tagIds: [], dueAt: iso(-5) },
    { id: "op-3", title: "Archive inactive assets", workspaceId: "ws-2", assigneeIds: ["tm-3"], assetIds: ["ast-3"], status: "done", priority: "low", tagIds: [], dueAt: iso(7) },
  ],
  documents: [
    { id: "doc-1", workspaceId: "ws-1", name: "Business Plan 2026.pdf", type: "pdf", size: "2.4 MB", status: "active", tagIds: [], updatedAt: iso(2) },
    { id: "doc-2", workspaceId: "ws-1", name: "Vendor Agreement.docx", type: "doc", size: "840 KB", status: "active", tagIds: [], updatedAt: iso(8) },
    { id: "doc-3", workspaceId: "ws-2", name: "Brand Guidelines.pdf", type: "pdf", size: "5.1 MB", status: "archived", tagIds: ["tag-4"], updatedAt: iso(15) },
  ],
  assets: [
    { id: "ast-1", workspaceId: "ws-1", name: "Main Storefront QR", type: "qr", status: "active", url: "/my-stores", tagIds: [], updatedAt: iso(0) },
    { id: "ast-2", workspaceId: "ws-1", name: "Product Catalog PDF", type: "file", status: "active", tagIds: [], updatedAt: iso(4) },
    { id: "ast-3", workspaceId: "ws-2", name: "Regional QR Entry", type: "qr", status: "active", url: "/my-stores", tagIds: [], updatedAt: iso(2) },
  ],
  tags: [
    { id: "tag-1", name: "Priority", color: "warning", status: "active" },
    { id: "tag-2", name: "Enterprise", color: "info", status: "active" },
    { id: "tag-3", name: "Internal", color: "muted", status: "active" },
    { id: "tag-4", name: "Archived", color: "danger", status: "active" },
  ],
  activities: [
    { id: "act-1", action: "updated", message: "Workspace updated", actor: "You", entityType: "workspaces", entityId: "ws-1", at: iso(0) },
    { id: "act-2", action: "created", message: "Catalog item added", actor: "Jordan Lee", entityType: "catalog", entityId: "cat-2", at: iso(1) },
    { id: "act-3", action: "created", message: "Customer record created", actor: "You", entityType: "customers", entityId: "cus-1", at: iso(2) },
    { id: "act-4", action: "assigned", message: "Operation assigned to team", actor: "Alex Morgan", entityType: "operations", entityId: "op-1", at: iso(1) },
    { id: "act-5", action: "tagged", message: "Transaction tagged Enterprise", actor: "You", entityType: "transactions", entityId: "txn-1", at: iso(0) },
  ],
  notes: [
    { id: "note-1", entityType: "customers", entityId: "cus-1", body: "Primary billing contact is **Sarah Chen**. Net-30 terms.", author: "You", status: "active", createdAt: iso(2), updatedAt: iso(2) },
    { id: "note-2", entityType: "workspaces", entityId: "ws-1", body: "Main hub for all storefront operations.", author: "Alex Morgan", status: "active", createdAt: iso(5), updatedAt: iso(5) },
    { id: "note-3", entityType: "operations", entityId: "op-1", body: "Check inventory levels before Friday review.", author: "Jordan Lee", status: "active", createdAt: iso(1), updatedAt: iso(1) },
  ],
  attachments: [
    { id: "att-1", entityType: "customers", entityId: "cus-1", name: "acme-contract.pdf", type: "pdf", size: "1.8 MB", mime: "application/pdf", url: "#", status: "active", createdAt: iso(3) },
    { id: "att-2", entityType: "documents", entityId: "doc-1", name: "cover-image.png", type: "image", size: "240 KB", mime: "image/png", url: "#", status: "active", createdAt: iso(2) },
    { id: "att-3", entityType: "assets", entityId: "ast-1", name: "qr-preview.png", type: "image", size: "64 KB", mime: "image/png", url: "#", status: "active", createdAt: iso(0) },
  ],
  notifications: [
    { id: "ntf-1", title: "Operation assigned to you", body: "Monthly inventory review", priority: "info", read: false, entityType: "operations", entityId: "op-1", href: "/app/operations#obj/operations/op-1", createdAt: iso(0) },
    { id: "ntf-2", title: "Transaction completed", body: "TXN-2026-001 — $1,240.00", priority: "success", read: false, entityType: "transactions", entityId: "txn-1", href: "/app/transactions#obj/transactions/txn-1", createdAt: iso(0) },
    { id: "ntf-3", title: "New catalog item", body: "Premium Consultation", priority: "info", read: true, entityType: "catalog", entityId: "cat-2", href: "/app/catalog#obj/catalog/cat-2", createdAt: iso(1) },
  ],
};

export const COLLECTIONS = [
  "organizations",
  "workspaces",
  "catalog",
  "customers",
  "transactions",
  "team",
  "operations",
  "documents",
  "assets",
  "tags",
  "activities",
  "notes",
  "attachments",
  "notifications",
];

export const BUSINESS_COLLECTIONS = COLLECTIONS.filter(
  (c) => !["activities", "notes", "attachments", "notifications"].includes(c)
);
