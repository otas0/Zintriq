import * as store from "../core/store.js";
import { TAGGABLE_COLLECTIONS } from "./object-types.js";
import { buildActivityEntry } from "./activity.js";

export function assignTag(collection, objectId, tagId) {
  if (!TAGGABLE_COLLECTIONS.includes(collection)) return null;
  const row = store.getById(collection, objectId);
  if (!row) return null;
  const tagIds = new Set([...(row.tagIds || []), tagId]);
  return store.update(collection, objectId, { tagIds: [...tagIds] }, { action: "tagged" });
}

export function removeTag(collection, objectId, tagId) {
  const row = store.getById(collection, objectId);
  if (!row) return null;
  const tagIds = (row.tagIds || []).filter((id) => id !== tagId);
  return store.update(collection, objectId, { tagIds }, { action: "updated" });
}

export function getObjectsWithTag(tagId) {
  /** @type {{ collection: string, id: string }[]} */
  const results = [];
  TAGGABLE_COLLECTIONS.forEach((col) => {
    store.getCollection(col).forEach((row) => {
      if ((row.tagIds || []).includes(tagId)) {
        results.push({ collection: col, id: row.id });
      }
    });
  });
  return results;
}

export function tagUsageCount(tagId) {
  return getObjectsWithTag(tagId).length;
}

export function filterByTag(collection, tagId) {
  return store.getCollection(collection).filter((row) => (row.tagIds || []).includes(tagId));
}

export function searchByTag(query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return store.getCollection("tags").filter((t) => String(t.name).toLowerCase().includes(q));
}

export function createTag(name, color = "info") {
  return store.create("tags", { name, color, status: "active" }, { action: "created" });
}
