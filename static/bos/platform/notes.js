import * as store from "../core/store.js";

export function addNote(entityType, entityId, body, author = "You") {
  return store.create("notes", {
    entityType,
    entityId,
    body,
    author,
    status: "active",
  }, { action: "noted", entityType, entityId, skipNotify: true });
}

export function updateNote(id, body) {
  const note = store.getById("notes", id);
  if (!note) return null;
  return store.update("notes", id, { body, updatedAt: new Date().toISOString() }, {
    action: "updated",
    entityType: String(note.entityType),
    entityId: String(note.entityId),
    activityMessage: "Note updated",
    skipNotify: true,
  });
}

export function deleteNote(id) {
  const note = store.getById("notes", id);
  if (!note) return false;
  return store.remove("notes", id, {
    action: "deleted",
    entityType: String(note.entityType),
    entityId: String(note.entityId),
    activityMessage: "Note deleted",
    skipNotify: true,
  });
}

export function listNotes(entityType, entityId) {
  return store.getCollection("notes")
    .filter((n) => n.entityType === entityType && n.entityId === entityId)
    .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
}

export function renderNoteBody(body) {
  return String(body)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}
