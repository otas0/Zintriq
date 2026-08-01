import * as store from "../core/store.js";
import { OBJECT_TYPES, RELATION_FIELDS, getObjectTitle, getObjectType } from "./object-types.js";

/**
 * @typedef {{ collection: string, id: string, label: string, relationLabel: string, direction: 'outgoing'|'incoming' }} RelatedObject
 */

function matchesRelation(record, field, id, multi) {
  const val = record[field];
  if (multi && Array.isArray(val)) return val.includes(id);
  return val === id;
}

/** @returns {RelatedObject[]} */
export function getRelatedObjects(collection, id) {
  const typeDef = getObjectType(collection);
  const record = store.getById(collection, id);
  if (!typeDef || !record) return [];

  /** @type {RelatedObject[]} */
  const related = [];
  const seen = new Set();

  const add = (col, objId, label, relationLabel, direction) => {
    const key = `${col}:${objId}`;
    if (seen.has(key) || (col === collection && objId === id)) return;
    seen.add(key);
    const obj = store.getById(col, objId);
    if (!obj) return;
    related.push({
      collection: col,
      id: objId,
      label: getObjectTitle(obj, getObjectType(col)),
      relationLabel: label,
      direction,
    });
  };

  (typeDef.relations || []).forEach((rel) => {
    if (rel.inverse) {
      const targetType = getObjectType(rel.target);
      if (!targetType) return;
      store.getCollection(rel.target).forEach((row) => {
        const field = rel.inverse;
        const multi = field.endsWith("Ids");
        if (matchesRelation(row, field, id, multi)) {
          add(rel.target, row.id, rel.label, typeDef.label, "incoming");
        }
      });
      return;
    }

    const val = record[rel.field];
    if (rel.multi && Array.isArray(val)) {
      val.forEach((objId) => add(rel.target, objId, rel.label, typeDef.label, "outgoing"));
    } else if (val) {
      add(rel.target, String(val), rel.label, typeDef.label, "outgoing");
    }
  });

  RELATION_FIELDS.forEach(({ field, target, multi }) => {
    if (target !== collection) return;
    Object.values(OBJECT_TYPES).forEach((srcType) => {
      if (srcType.collection === collection) return;
      store.getCollection(srcType.collection).forEach((row) => {
        if (matchesRelation(row, field, id, multi)) {
          add(srcType.collection, row.id, srcType.labelPlural, typeDef.label, "incoming");
        }
      });
    });
  });

  return related;
}

/** @returns {Record<string, RelatedObject[]>} */
export function groupRelatedObjects(collection, id) {
  const items = getRelatedObjects(collection, id);
  /** @type {Record<string, RelatedObject[]>} */
  const groups = {};
  items.forEach((item) => {
    if (!groups[item.relationLabel]) groups[item.relationLabel] = [];
    groups[item.relationLabel].push(item);
  });
  return groups;
}

export function getModulePath(collection) {
  return getObjectType(collection)?.modulePath || "/app";
}
