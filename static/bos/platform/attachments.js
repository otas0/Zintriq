import * as store from "../core/store.js";

const FILE_TYPES = {
  image: { icon: "🖼", label: "Image" },
  pdf: { icon: "📄", label: "PDF" },
  doc: { icon: "📝", label: "Document" },
  other: { icon: "📎", label: "File" },
};

export function inferFileType(name, mime = "") {
  const lower = name.toLowerCase();
  if (/\.(png|jpe?g|gif|webp|svg)$/.test(lower) || mime.startsWith("image/")) return "image";
  if (/\.pdf$/.test(lower) || mime === "application/pdf") return "pdf";
  if (/\.(doc|docx|txt|md)$/.test(lower)) return "doc";
  return "other";
}

export function listAttachments(entityType, entityId) {
  return store.getCollection("attachments").filter(
    (a) => a.entityType === entityType && a.entityId === entityId
  );
}

export function addAttachment(entityType, entityId, fileMeta) {
  const type = inferFileType(fileMeta.name, fileMeta.mime);
  return store.create("attachments", {
    entityType,
    entityId,
    name: fileMeta.name,
    type,
    size: fileMeta.size || "—",
    mime: fileMeta.mime || "",
    url: fileMeta.url || "#",
    status: "active",
  }, { action: "attached", entityType, entityId, skipNotify: true });
}

export function removeAttachment(id) {
  const att = store.getById("attachments", id);
  if (!att) return false;
  return store.remove("attachments", id, {
    action: "deleted",
    entityType: String(att.entityType),
    entityId: String(att.entityId),
    activityMessage: "Attachment removed",
    skipNotify: true,
  });
}

export function getFileIcon(type) {
  return FILE_TYPES[type]?.icon || FILE_TYPES.other.icon;
}

export function getFileLabel(type) {
  return FILE_TYPES[type]?.label || FILE_TYPES.other.label;
}

export function mockPickFile() {
  const samples = [
    { name: "screenshot.png", size: "420 KB", mime: "image/png" },
    { name: "invoice.pdf", size: "1.2 MB", mime: "application/pdf" },
    { name: "notes.docx", size: "88 KB", mime: "application/doc" },
  ];
  return samples[Math.floor(Math.random() * samples.length)];
}
