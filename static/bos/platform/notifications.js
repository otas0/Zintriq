import * as store from "../core/store.js";
import { getObjectTitle, getObjectType } from "./object-types.js";

/** @typedef {'info'|'success'|'warning'|'error'} NotificationPriority */

export function createNotification(opts) {
  return store.create("notifications", {
    title: opts.title,
    body: opts.body || "",
    priority: opts.priority || "info",
    read: opts.read ?? false,
    entityType: opts.entityType || null,
    entityId: opts.entityId || null,
    href: opts.href || null,
    serverId: opts.serverId || null,
  }, { skipActivity: true, skipNotify: true });
}

export function markRead(id) {
  return store.update("notifications", id, { read: true });
}

export function markAllRead() {
  store.getCollection("notifications").forEach((n) => {
    if (!n.read) store.update("notifications", n.id, { read: true });
  });
}

export function getUnreadCount() {
  return store.getCollection("notifications").filter((n) => !n.read).length;
}

/** React to domain events — notifications subscribe, never triggered by modules. */
export function handleDomainEventNotification(event) {
  const priority = event.event_type.includes("deleted") ? "warning"
    : event.metadata?.rating != null && Number(event.metadata.rating) <= 2 ? "warning"
    : "info";

  const titles = {
    "feedback.submitted": "New feedback received",
    "customer.created": "New customer",
    "customer.joined": "New customer",
    "customer.archived": "Customer archived",
    "customer.deleted": "Customer deleted",
    "workspace.created": "Workspace created",
  };

  createNotification({
    title: titles[event.event_type] || event.title || event.event_type,
    body: event.detail || event.object_type,
    priority,
    entityType: event.object_type,
    entityId: String(event.object_id),
    href: event.href || "/app/store",
  });
}

export function notifyForAction(action, collection, entityId) {
  const typeDef = getObjectType(collection);
  const record = store.getById(collection, entityId);
  const title = record ? getObjectTitle(record, typeDef) : entityId;
  const href = typeDef ? `${typeDef.modulePath}#obj/${collection}/${entityId}` : "/app/store";

  const messages = {
    created: `New ${typeDef?.label || "object"}: ${title}`,
    updated: `${title} was updated`,
    archived: `${title} was archived`,
    deleted: `${title} was deleted`,
    assigned: `${title} was assigned`,
    moved: `${title} was moved`,
    tagged: `${title} was tagged`,
    noted: `New note on ${title}`,
    attached: `File attached to ${title}`,
  };

  createNotification({
    title: messages[action] || `${title} — ${action}`,
    body: typeDef?.labelPlural || collection,
    priority: action === "deleted" ? "warning" : "info",
    entityType: collection,
    entityId,
    href,
  });
}

/** Merge server notifications into local store for bell UI. */
export async function syncServerNotifications() {
  try {
    const res = await fetch("/api/notifications?limit=50", { credentials: "same-origin" });
    if (!res.ok) return;
    const items = await res.json();
    const existing = new Set(store.getCollection("notifications").map((n) => n.serverId).filter(Boolean));
    items.forEach((n) => {
      if (existing.has(n.id)) return;
      createNotification({
        title: n.title,
        body: n.body,
        priority: n.priority,
        entityType: n.object_type,
        entityId: n.object_id ? String(n.object_id) : null,
        href: n.href,
        serverId: n.id,
        read: n.read,
      });
    });
  } catch { /* offline */ }
}

export function seedActionNotifications() {
  /* notifications are seeded in data; runtime actions create new ones */
}
