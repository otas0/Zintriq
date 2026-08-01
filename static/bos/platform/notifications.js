import * as store from "../core/store.js";
import { getObjectTitle, getObjectType } from "./object-types.js";

/** @typedef {'info'|'success'|'warning'|'error'} NotificationPriority */

export function createNotification(opts) {
  return store.create("notifications", {
    title: opts.title,
    body: opts.body || "",
    priority: opts.priority || "info",
    read: false,
    entityType: opts.entityType || null,
    entityId: opts.entityId || null,
    href: opts.href || null,
  });
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

export function notifyForAction(action, collection, entityId) {
  const typeDef = getObjectType(collection);
  const record = store.getById(collection, entityId);
  const title = record ? getObjectTitle(record, typeDef) : entityId;
  const href = typeDef ? `${typeDef.modulePath}#obj/${collection}/${entityId}` : "/app";

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

export function seedActionNotifications() {
  /* notifications are seeded in data; runtime actions create new ones */
}
