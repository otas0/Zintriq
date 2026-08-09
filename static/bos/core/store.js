import { COLLECTIONS, SEED_DATA, BUSINESS_COLLECTIONS } from "../data/seed.js";
import { escapeHtml, searchItems, sortItems } from "../services/search.js";
import { buildActivityEntry } from "../platform/activity.js";
import { notifyForAction } from "../platform/notifications.js";
import { OBJECT_TYPES, getObjectTitle, getObjectType } from "../platform/object-types.js";

/** @typedef {Record<string, unknown> & { id: string }} BosRecord */

const STORAGE_KEY = "bos-ui-prefs-v2";
const ID_COUNTER_KEY = "bos-id-counter";

let idCounter = loadIdCounter();
const nextId = (prefix) => `${prefix}-${++idCounter}`;

function loadIdCounter() {
  try {
    const n = Number(localStorage.getItem(ID_COUNTER_KEY));
    return Number.isFinite(n) && n > 0 ? n : 2000;
  } catch {
    return 2000;
  }
}

function loadPersistedState() {
  return structuredClone(SEED_DATA);
}

/** @type {Record<string, BosRecord[]>} */
let state = loadPersistedState();

/** @type {Set<(collection: string | null) => void>} */
const listeners = new Set();

/** @type {{ type: string, id: string, label: string, path: string, at: string }[]} */
let moduleRecents = [];

/** @type {Set<string>} */
let moduleFavorites = loadModuleFavorites();

function loadModuleFavorites() {
  try {
    const raw = localStorage.getItem("bos-favorites");
    if (raw) return new Set(JSON.parse(raw));
  } catch {
    /* ignore */
  }
  return new Set(["workspaces", "catalog"]);
}

function saveModuleFavorites() {
  localStorage.setItem("bos-favorites", JSON.stringify([...moduleFavorites]));
}

function notify(collection = null) {
  listeners.forEach((fn) => fn(collection));
}

function logActivity(action, entityType, entityId, message, actor = "You") {
  const entry = {
    id: nextId("act"),
    ...buildActivityEntry(action, entityType, entityId, message, actor),
  };
  state.activities.unshift(entry);
  if (state.activities.length > 100) state.activities.length = 100;
  listeners.forEach((fn) => fn("activities"));

  window.dispatchEvent(new CustomEvent("bos:domain-event", {
    detail: {
      event_type: `${entityType}.${action}`,
      object_type: entityType,
      object_id: entityId,
      title: message,
      actor,
      created_at: entry.at,
    },
  }));
}

function cloneState() {
  return structuredClone(state);
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getState() {
  return cloneState();
}

export function getCollection(name) {
  return [...(state[name] || [])];
}

export function getById(collection, id) {
  return state[collection]?.find((r) => r.id === id) || null;
}

export function resolveRelation(collection, id) {
  const row = getById(collection, id);
  if (!row) return "—";
  return getObjectTitle(row, getObjectType(collection));
}

export function trackRecent(type, id, label, path) {
  moduleRecents = [{ type, id, label, path, at: new Date().toISOString() }, ...moduleRecents.filter((r) => r.id !== id || r.type !== type)].slice(0, 12);
}

export function getRecents() {
  return [...moduleRecents];
}

export function toggleFavorite(moduleId) {
  if (moduleFavorites.has(moduleId)) moduleFavorites.delete(moduleId);
  else moduleFavorites.add(moduleId);
  saveModuleFavorites();
  notify("favorites");
}

export function getFavorites() {
  return [...moduleFavorites];
}

/**
 * @param {string} collection
 * @param {Record<string, unknown>} data
 * @param {{ action?: string, entityType?: string, entityId?: string, skipNotify?: boolean }} [opts]
 */
export function create(collection, data, opts = {}) {
  const prefix = collection.slice(0, 3);
  const now = new Date().toISOString();
  const record = {
    ...data,
    id: nextId(prefix),
    status: data.status || "active",
    createdAt: data.createdAt || now,
    updatedAt: now,
  };
  if (!state[collection]) state[collection] = [];
  state[collection].unshift(record);

  if (!opts.skipActivity) {
    const action = opts.action || "created";
    const entityType = opts.entityType || collection;
    const entityId = opts.entityId || record.id;
    logActivity(action, entityType, entityId);
  }
  if (!opts.skipNotify && BUSINESS_COLLECTIONS.includes(collection)) {
    notifyForAction(opts.action || "created", collection, record.id);
  }
  notify(collection);
  return structuredClone(record);
}

/**
 * @param {string} collection
 * @param {string} id
 * @param {Record<string, unknown>} patch
 * @param {{ action?: string, entityType?: string, entityId?: string, activityMessage?: string, skipNotify?: boolean }} [opts]
 */
export function update(collection, id, patch, opts = {}) {
  const list = state[collection];
  if (!list) return null;
  const idx = list.findIndex((r) => r.id === id);
  if (idx < 0) return null;
  list[idx] = { ...list[idx], ...patch, updatedAt: new Date().toISOString() };
  const action = opts.action || "updated";
  const entityType = opts.entityType || collection;
  const entityId = opts.entityId || id;
  logActivity(action, entityType, entityId, opts.activityMessage);
  if (!opts.skipNotify && BUSINESS_COLLECTIONS.includes(collection)) {
    notifyForAction(action, collection, id);
  }
  notify(collection);
  return structuredClone(list[idx]);
}

/** Re-insert a previously removed record (undo delete). */
export function insertRecord(collection, record, opts = {}) {
  if (!state[collection]) state[collection] = [];
  if (state[collection].some((r) => r.id === record.id)) return null;
  state[collection].unshift(structuredClone(record));
  logActivity(opts.action || "restored", collection, record.id, opts.activityMessage || "Restored record");
  notify(collection);
  return structuredClone(record);
}

/**
 * @param {string} collection
 * @param {string} id
 * @param {{ action?: string, entityType?: string, entityId?: string, activityMessage?: string, skipNotify?: boolean }} [opts]
 */
export function remove(collection, id, opts = {}) {
  const list = state[collection];
  if (!list) return false;
  const idx = list.findIndex((r) => r.id === id);
  if (idx < 0) return false;
  const row = list[idx];
  const typeDef = getObjectType(collection);
  const label = getObjectTitle(row, typeDef);
  list.splice(idx, 1);
  const action = opts.action || "deleted";
  const entityType = opts.entityType || collection;
  const entityId = opts.entityId || id;
  logActivity(action, entityType, entityId, opts.activityMessage || `Deleted ${label}`);
  if (!opts.skipNotify && BUSINESS_COLLECTIONS.includes(collection)) {
    notifyForAction(action, collection, id);
  }
  notify(collection);
  return true;
}

export function duplicate(collection, id) {
  const row = getById(collection, id);
  if (!row) return null;
  const copy = { ...row, id: undefined };
  const typeDef = getObjectType(collection);
  const titleField = typeDef?.titleField || "name";
  if (copy[titleField]) copy[titleField] = `${copy[titleField]} (copy)`;
  if (copy.reference) copy.reference = `${copy.reference}-COPY`;
  if (copy.sku) copy.sku = `${copy.sku}-C`;
  return create(collection, copy, { action: "duplicated" });
}

export function archive(collection, id) {
  const row = getById(collection, id);
  if (!row) return null;
  const patch = { status: "archived" };
  if (row.status && row.status !== "archived") patch._priorStatus = row.status;
  return update(collection, id, patch, { action: "archived" });
}

const RESTORE_STATUS = {
  operations: "open",
  transactions: "completed",
  team: "active",
  catalog: "active",
  documents: "active",
  assets: "active",
  workspaces: "active",
  customers: "active",
  organizations: "active",
  tags: "active",
};

export function restore(collection, id) {
  const row = getById(collection, id);
  if (!row) return null;
  const prior = row._priorStatus;
  const status = prior || RESTORE_STATUS[collection] || "active";
  return update(collection, id, { status, _priorStatus: undefined }, { action: "restored" });
}

export function batch(collection, ids, action, extra = {}) {
  const results = [];
  ids.forEach((id) => {
    if (action === "delete") results.push(remove(collection, id));
    else if (action === "archive") results.push(archive(collection, id));
    else if (action === "restore") results.push(restore(collection, id));
    else if (action === "duplicate") results.push(duplicate(collection, id));
    else if (action === "tag" && extra.tagId) {
      const row = getById(collection, id);
      if (row) {
        const tagIds = new Set([...(row.tagIds || []), extra.tagId]);
        results.push(update(collection, id, { tagIds: [...tagIds] }, { action: "tagged" }));
      }
    }
  });
  notify(collection);
  return results;
}

export function getObjectActivities(collection, id) {
  return state.activities.filter((a) => a.entityType === collection && a.entityId === id);
}

export function getGlobalActivities(limit = 30) {
  return state.activities.slice(0, limit);
}

/**
 * @param {string} query
 */
export function globalSearch(_query) {
  return [];
}

export function query(collection, opts = {}) {
  let list = getCollection(collection);
  if (opts.search && opts.haystack) {
    list = searchItems(opts.search, list, opts.haystack);
  }
  if (opts.tagId) {
    list = list.filter((row) => (row.tagIds || []).includes(opts.tagId));
  }
  if (opts.filter && opts.filter !== "all") {
    list = list.filter((row) => {
      if (row.status === opts.filter) return true;
      if (row.type === opts.filter) return true;
      if (row.role === opts.filter) return true;
      return false;
    });
  }
  if (opts.sortKey) list = sortItems(list, opts.sortKey, opts.sortAsc !== false);
  return list;
}

export function tagUsageCount(tagId) {
  let count = 0;
  BUSINESS_COLLECTIONS.forEach((col) => {
    count += (state[col] || []).filter((r) => (r.tagIds || []).includes(tagId)).length;
  });
  return count;
}

export function resetStore() {
  state = structuredClone(SEED_DATA);
  idCounter = 2000;
  moduleRecents = [];
  moduleFavorites = new Set(["workspaces", "catalog"]);
  saveModuleFavorites();
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(ID_COUNTER_KEY);
  notify(null);
}

export { escapeHtml, COLLECTIONS, BUSINESS_COLLECTIONS, OBJECT_TYPES };
