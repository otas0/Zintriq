import * as store from "../core/store.js";
import { escapeHtml } from "../services/search.js";
import { statusBadge, tag as tagBadge } from "../components/index.js";

/** @param {import('./object-types.js').PropertyDef} prop @param {unknown} value @param {{ edit?: boolean, name?: string }} [opts] */
export function renderPropertyInput(prop, value, opts = {}) {
  const name = opts.name || prop.key;
  const val = value ?? "";

  if (prop.readonly && !opts.edit) {
    return renderPropertyDisplay(prop, value);
  }

  switch (prop.type) {
    case "status":
    case "select":
      return `<select class="os-select" name="${name}">${(prop.options || []).map((o) => `<option value="${o}"${val === o ? " selected" : ""}>${escapeHtml(o.replace(/_/g, " "))}</option>`).join("")}</select>`;
    case "relationship": {
      const options = store.getCollection(prop.relation || "").map((r) => {
        const label = String(r.name || r.title || r.reference || r.id);
        const selected = prop.multi
          ? Array.isArray(val) && val.includes(r.id)
          : val === r.id;
        return prop.multi
          ? `<option value="${r.id}"${selected ? " selected" : ""}>${escapeHtml(label)}</option>`
          : `<option value="${r.id}"${selected ? " selected" : ""}>${escapeHtml(label)}</option>`;
      });
      if (prop.multi) {
        return `<select class="os-select" name="${name}" multiple size="4">${options.join("")}</select>`;
      }
      return `<select class="os-select" name="${name}"><option value="">—</option>${options.join("")}</select>`;
    }
    case "boolean":
      return `<label class="bos-bool-field"><input type="checkbox" name="${name}"${val ? " checked" : ""}> ${escapeHtml(prop.label)}</label>`;
    case "number":
    case "currency":
      return `<input class="os-input" name="${name}" type="number" step="${prop.type === "currency" ? "0.01" : "1"}" value="${escapeHtml(String(val))}"${prop.required ? " required" : ""}>`;
    case "date":
      return `<input class="os-input" name="${name}" type="date" value="${escapeHtml(String(val).slice(0, 10))}"${prop.required ? " required" : ""}>`;
    case "email":
      return `<input class="os-input" name="${name}" type="email" value="${escapeHtml(String(val))}"${prop.required ? " required" : ""}>`;
    case "phone":
      return `<input class="os-input" name="${name}" type="tel" value="${escapeHtml(String(val))}"${prop.required ? " required" : ""}>`;
    case "url":
      return `<input class="os-input" name="${name}" type="url" value="${escapeHtml(String(val))}"${prop.required ? " required" : ""}>`;
    case "tag":
      return renderPropertyDisplay(prop, value);
    default:
      return `<input class="os-input" name="${name}" type="text" value="${escapeHtml(String(val))}"${prop.required ? " required" : ""}>`;
  }
}

/** @param {import('./object-types.js').PropertyDef} prop @param {unknown} value */
export function renderPropertyDisplay(prop, value) {
  if (value == null || value === "") return `<span class="bos-prop-empty">—</span>`;

  switch (prop.type) {
    case "status":
      return statusBadge(String(value));
    case "currency":
      return `$${Number(value).toFixed(2)}`;
    case "date":
      return escapeHtml(String(value).slice(0, 10));
    case "boolean":
      return value ? "Yes" : "No";
    case "relationship": {
      if (prop.multi && Array.isArray(value)) {
        return value.map((id) => escapeHtml(store.resolveRelation(prop.relation || "", id))).join(", ") || "—";
      }
      return escapeHtml(store.resolveRelation(prop.relation || "", String(value)));
    }
    case "tag": {
      if (Array.isArray(value)) {
        return value.map((id) => {
          const t = store.getById("tags", id);
          return t ? tagBadge(String(t.name), String(t.color)) : "";
        }).join(" ");
      }
      return escapeHtml(String(value));
    }
    case "url":
      return `<a href="${escapeHtml(String(value))}" target="_blank" rel="noopener">${escapeHtml(String(value))}</a>`;
    case "email":
      return `<a href="mailto:${escapeHtml(String(value))}">${escapeHtml(String(value))}</a>`;
    default:
      return escapeHtml(String(value));
  }
}

/** @param {import('./object-types.js').PropertyDef[]} properties @param {Record<string, unknown>} record @param {{ editable?: boolean }} [opts] */
export function renderPropertiesPanel(properties, record, opts = {}) {
  const editable = opts.editable !== false;
  const fields = properties.filter((p) => p.type !== "tag" || (record.tagIds && record.tagIds.length));

  if (editable) {
    return `<form class="os-form bos-prop-form" id="bos-prop-form">
      ${fields.map((p) => `<div class="os-field"><label class="os-label">${escapeHtml(p.label)}</label>${renderPropertyInput(p, record[p.key], { edit: !p.readonly })}</div>`).join("")}
      <div class="bos-drawer-form__actions"><button type="submit" class="os-btn os-btn-primary">Save properties</button></div>
    </form>`;
  }

  return `<dl class="bos-prop-list">${fields.map((p) => `<div class="bos-prop-row"><dt>${escapeHtml(p.label)}</dt><dd>${renderPropertyDisplay(p, record[p.key])}</dd></div>`).join("")}</dl>`;
}

/** @param {FormData} fd @param {import('./object-types.js').PropertyDef[]} properties */
export function parsePropertyForm(fd, properties) {
  /** @type {Record<string, unknown>} */
  const patch = {};
  properties.forEach((p) => {
    if (p.readonly) return;
    if (p.type === "relationship" && p.multi) {
      patch[p.key] = fd.getAll(p.key);
      return;
    }
    if (p.type === "boolean") {
      patch[p.key] = fd.has(p.key);
      return;
    }
    const raw = fd.get(p.key);
    if (raw == null || raw === "") return;
    if (p.type === "number" || p.type === "currency") patch[p.key] = Number(raw);
    else patch[p.key] = raw;
  });
  return patch;
}
