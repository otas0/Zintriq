import * as store from "../core/store.js";
import { escapeHtml } from "../services/search.js";
import { openDrawer, closeDrawer } from "../services/api.js";

/** @param {string} collection @param {string[]} ids */
export function exportRecords(collection, ids) {
  const rows = ids.map((id) => store.getById(collection, id)).filter(Boolean);
  const blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${collection}-export-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * @param {string} title
 * @param {{ value: string, label: string }[]} options
 * @param {(value: string) => void} onSelect
 */
export function openPickerDrawer(title, options, onSelect) {
  openDrawer(title, `<form class="os-form" id="bos-picker-form">
    <div class="os-field"><label class="os-label">Choose</label>
      <select class="os-select" name="value" required>${options.map((o) => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join("")}</select>
    </div>
    <div class="bos-drawer-form__actions">
      <button type="button" class="os-btn os-btn-ghost" data-picker-cancel>Cancel</button>
      <button type="submit" class="os-btn os-btn-primary">Apply</button>
    </div>
  </form>`);
  document.getElementById("bos-drawer-body")?.querySelector("[data-picker-cancel]")?.addEventListener("click", closeDrawer);
  document.getElementById("bos-drawer-body")?.querySelector("#bos-picker-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const value = new FormData(e.target).get("value");
    if (value) onSelect(String(value));
    closeDrawer();
  });
}

export function openWorkspacePicker(onSelect) {
  const options = store.getCollection("workspaces").map((w) => ({ value: w.id, label: String(w.name) }));
  if (!options.length) return false;
  openPickerDrawer("Move to workspace", options, onSelect);
  return true;
}

export function openTagPicker(onSelect) {
  const options = store.getCollection("tags").map((t) => ({ value: t.id, label: String(t.name) }));
  if (!options.length) return false;
  openPickerDrawer("Apply tag", options, onSelect);
  return true;
}
