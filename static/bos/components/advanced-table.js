import { escapeHtml } from "../services/search.js";
import { emptyState } from "./index.js";

/**
 * @param {{ key: string, label: string, render?: (row: Record<string, unknown>) => string }[]} columns
 * @param {{ order?: string[], hidden?: string[], widths?: Record<string, number>, pinned?: string[] }} layout
 */
export function resolveColumns(columns, layout = {}) {
  const order = layout.order?.length
    ? layout.order.filter((k) => columns.some((c) => c.key === k))
    : columns.map((c) => c.key);
  const hidden = new Set(layout.hidden || []);
  const pinned = new Set(layout.pinned || []);
  return order
    .map((key) => columns.find((c) => c.key === key))
    .filter(Boolean)
    .filter((c) => !hidden.has(c.key))
    .map((c) => ({ ...c, pinned: pinned.has(c.key), width: layout.widths?.[c.key] }));
}

/**
 * @param {HTMLElement} container
 * @param {Record<string, unknown>[]} items
 * @param {{ key: string, label: string, render?: (row: Record<string, unknown>) => string, pinned?: boolean, width?: number }[]} columns
 * @param {object} options
 * @param {(layout: object) => void} [onLayoutChange]
 */
export function renderAdvancedTable(container, items, columns, options = {}, onLayoutChange) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = emptyState({ title: "No results", text: "Try adjusting search or filters." });
    return;
  }

  const density = options.density || "comfortable";
  const visibleCols = columns.length ? columns : [];

  const head = visibleCols.map((c) => {
    const w = c.width ? ` style="width:${c.width}px;min-width:${c.width}px"` : "";
    const pin = c.pinned ? ' data-pinned="1"' : "";
    return `<th data-col="${escapeHtml(c.key)}"${pin}${w}><span class="bos-th-label">${escapeHtml(c.label)}</span><span class="bos-col-resize" data-resize-col="${escapeHtml(c.key)}" aria-hidden="true"></span></th>`;
  }).join("");

  const slice = options.virtualize && items.length > 80 ? items.slice(0, 80) : items;
  const body = slice
    .map((row) => {
      const id = row.id;
      const selected = options.selected?.has(id);
      const cells = visibleCols
        .map((c) => {
          const content = c.render ? c.render(row) : escapeHtml(row[c.key]);
          const pin = c.pinned ? ' data-pinned="1"' : "";
          return `<td${pin}>${content}</td>`;
        })
        .join("");
      const check = options.selectable
        ? `<td class="bos-table__check" data-pinned="1"><input type="checkbox"${selected ? " checked" : ""} data-id="${escapeHtml(String(id))}"></td>`
        : "";
      return `<tr data-clickable data-id="${escapeHtml(String(id))}" class="${selected ? "is-selected" : ""}">${check}${cells}</tr>`;
    })
    .join("");

  const checkHead = options.selectable
    ? '<th class="bos-table__check" data-pinned="1"><input type="checkbox" data-select-all aria-label="Select all"></th>'
    : "";

  const more = options.virtualize && items.length > 80
    ? `<tr class="bos-table-more"><td colspan="${visibleCols.length + 1}">Showing 80 of ${items.length} — refine filters to narrow</td></tr>`
    : "";

  container.innerHTML = `<div class="bos-table-wrap bos-table-wrap--${density}"><table class="bos-table bos-table--advanced"><thead><tr>${checkHead}${head}</tr></thead><tbody>${body}${more}</tbody></table></div>`;

  container.querySelectorAll("tr[data-clickable]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target instanceof HTMLInputElement) return;
      const id = tr.getAttribute("data-id");
      const row = items.find((i) => String(i.id) === id);
      if (row && options.onRowClick) options.onRowClick(row, e);
    });
  });

  container.querySelectorAll('input[type="checkbox"][data-id]').forEach((input) => {
    input.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = input.getAttribute("data-id");
      if (id && options.onToggle) options.onToggle(id, e.shiftKey);
    });
  });

  const selectAll = container.querySelector("[data-select-all]");
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      if (!(selectAll instanceof HTMLInputElement)) return;
      options.onSelectAll?.(selectAll.checked, items);
    });
  }

  if (onLayoutChange) {
    container.querySelectorAll("[data-resize-col]").forEach((handle) => {
      handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const key = handle.getAttribute("data-resize-col");
        const th = handle.closest("th");
        if (!key || !th) return;
        const startX = e.clientX;
        const startW = th.offsetWidth;
        const onMove = (ev) => {
          const w = Math.max(60, startW + ev.clientX - startX);
          onLayoutChange({ widths: { ...(options.layout?.widths || {}), [key]: w } });
        };
        const onUp = () => {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  }
}

/** @param {HTMLElement} host @param {{ key: string, label: string }[]} allColumns @param {object} layout @param {(patch: object) => void} onChange */
export function renderColumnPicker(host, allColumns, layout, onChange) {
  if (!host) return;
  const hidden = new Set(layout.hidden || []);
  host.innerHTML = `<details class="bos-col-picker"><summary class="bos-filter-chip">Columns</summary><div class="bos-col-picker__panel">${allColumns.map((c) => `
    <label class="bos-col-picker__item"><input type="checkbox" data-col-toggle="${escapeHtml(c.key)}"${hidden.has(c.key) ? "" : " checked"}> ${escapeHtml(c.label)}</label>`).join("")}</div></details>`;
  host.querySelectorAll("[data-col-toggle]").forEach((input) => {
    input.addEventListener("change", () => {
      if (!(input instanceof HTMLInputElement)) return;
      const key = input.getAttribute("data-col-toggle");
      const next = new Set(layout.hidden || []);
      if (input.checked) next.delete(key);
      else next.add(key);
      onChange({ hidden: [...next] });
    });
  });
}
