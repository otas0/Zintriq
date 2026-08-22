/** StatusBadge — standard status display across Zintriq. */

import { esc } from "./_utils.js";

export const STATUS_LABELS = {
  active: "Active",
  draft: "Draft",
  archived: "Archived",
  disabled: "Disabled",
  pending: "Pending",
  completed: "Completed",
  paused: "Needs attention",
  needs_attention: "Needs attention",
  published: "Active",
  open: "Pending",
  confirmed: "Active",
  cancelled: "Archived",
  inactive: "Archived",
  invited: "Pending",
  in_progress: "Pending",
  connected: "Active",
  not_connected: "Draft",
};

/** @param {string} status */
export function normalizeStatus(status) {
  const key = String(status || "unknown").toLowerCase().replace(/\s+/g, "_");
  const label = STATUS_LABELS[key] || String(status || "—");
  let visualKey = key;
  if (key === "paused" || key === "needs_attention") visualKey = "needs_attention";
  if (key === "disabled") visualKey = "disabled";
  return { key: visualKey, label };
}

/** @param {string} status */
export function StatusBadge(status) {
  const { key, label } = normalizeStatus(status);
  return `<span class="bos-badge bos-ui-badge bos-badge--${esc(key)}" role="status">${esc(label)}</span>`;
}

/** @param {string} label @param {string} [variant] */
export function Tag(label, variant = "") {
  return `<span class="bos-tag bos-ui-tag${variant ? ` bos-tag--${variant}` : ""}">${esc(label)}</span>`;
}

/** @param {string} priority */
export function PriorityBadge(priority) {
  const key = String(priority || "medium").toLowerCase();
  return `<span class="bos-priority bos-priority--${esc(key)}">${esc(priority || "medium")}</span>`;
}

/** @deprecated */
export const statusBadge = StatusBadge;
export const tag = Tag;
export const priorityBadge = PriorityBadge;
