/** @typedef {'created'|'updated'|'archived'|'restored'|'deleted'|'assigned'|'moved'|'tagged'|'noted'|'attached'|'duplicated'} ActivityAction */

/**
 * @param {string} action
 * @param {string} collection
 * @param {string} entityId
 * @param {string} [message]
 * @param {string} [actor]
 * @returns {object}
 */
export function buildActivityEntry(action, collection, entityId, message, actor = "You") {
  const labels = {
    created: "Created",
    updated: "Updated",
    archived: "Archived",
    restored: "Restored",
    deleted: "Deleted",
    assigned: "Assigned",
    moved: "Moved",
    tagged: "Tagged",
    noted: "Added note",
    attached: "Attached file",
    duplicated: "Duplicated",
  };
  return {
    action,
    message: message || `${labels[action] || action} ${collection.replace(/s$/, "")}`,
    actor,
    entityType: collection,
    entityId,
    at: new Date().toISOString(),
  };
}

export function formatActivityAction(action) {
  const map = {
    created: "Created",
    updated: "Updated",
    archived: "Archived",
    restored: "Restored",
    deleted: "Deleted",
    assigned: "Assigned",
    moved: "Moved",
    tagged: "Tagged",
    noted: "Noted",
    attached: "Attached",
    duplicated: "Duplicated",
  };
  return map[action] || action;
}
