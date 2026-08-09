/**
 * Business OS MVP Component Library
 * ui/ · layout/ · business/ · qr/ · response/ · team/
 *
 * Build pages by composing these — do not duplicate UI patterns.
 */

export * from "./ui/index.js";
export * from "./layout/index.js";
export * from "./business/index.js";
export * from "./qr/index.js";
export * from "./response/index.js";
export * from "./team/index.js";

import { esc as escapeHtml } from "./ui/_utils.js";
import { EmptyState } from "./ui/EmptyState.js";
import { mountFilterChips } from "./layout/FilterBar.js";

export { escapeHtml };

/** @param {string[]} filters @param {string} active @param {(filter: string) => void} onChange */
export function renderFilterBar(container, filters, active, onChange) {
  mountFilterChips(container, filters, active, onChange);
}

export function renderDataTable(container, items, columns, options = {}) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = EmptyState({ title: "No results", text: "Try adjusting search or filters." });
    return;
  }
  const head = columns.map((c) => `<th>${escapeHtml(c.label)}</th>`).join("");
  const body = items.map((row) => {
    const id = row.id;
    const selected = options.selected?.has(id);
    const cells = columns.map((c) => {
      const content = c.render ? c.render(row) : escapeHtml(row[c.key]);
      return `<td>${content}</td>`;
    }).join("");
    const check = options.selectable
      ? `<td class="bos-table__check"><input type="checkbox"${selected ? " checked" : ""} data-id="${escapeHtml(String(id))}"></td>`
      : "";
    return `<tr data-clickable data-id="${escapeHtml(String(id))}" class="${selected ? "is-selected" : ""}">${check}${cells}</tr>`;
  }).join("");
  const checkHead = options.selectable ? '<th class="bos-table__check"><input type="checkbox" data-select-all></th>' : "";
  container.innerHTML = `<div class="bos-table-wrap"><table class="bos-table"><thead><tr>${checkHead}${head}</tr></thead><tbody>${body}</tbody></table></div>`;

  container.querySelectorAll("tr[data-clickable]").forEach((tr) => {
    tr.addEventListener("click", (e) => {
      if (e.target instanceof HTMLInputElement) return;
      const id = tr.getAttribute("data-id");
      const row = items.find((i) => String(i.id) === id);
      if (row && options.onRowClick) options.onRowClick(row);
    });
  });
  container.querySelectorAll('input[type="checkbox"][data-id]').forEach((input) => {
    input.addEventListener("click", (e) => e.stopPropagation());
    input.addEventListener("change", () => {
      const id = input.getAttribute("data-id");
      if (id && options.onToggle) options.onToggle(id.includes("-") ? id : Number(id) || id);
    });
  });
  const selectAll = container.querySelector("[data-select-all]");
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      if (!(selectAll instanceof HTMLInputElement)) return;
      options.onSelectAll?.(selectAll.checked, items);
    });
  }
}

export function renderCardGrid(container, items, renderCard) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = EmptyState({ title: "Nothing here yet" });
    return;
  }
  container.innerHTML = `<div class="bos-card-grid">${items.map(renderCard).join("")}</div>`;
}

export function showContextMenu(event, items, onSelect) {
  const menu = document.getElementById("bos-context-menu");
  if (!menu) return;
  event.preventDefault();
  menu.innerHTML = items.map((i) =>
    `<button type="button" class="bos-nav__item" data-action="${escapeHtml(i.action)}">${escapeHtml(i.label)}</button>`
  ).join("");
  menu.style.left = `${event.clientX}px`;
  menu.style.top = `${event.clientY}px`;
  menu.classList.remove("hidden");
  const close = () => {
    menu.classList.add("hidden");
    document.removeEventListener("click", close);
  };
  menu.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      onSelect(btn.getAttribute("data-action") || "");
      close();
    });
  });
  setTimeout(() => document.addEventListener("click", close), 0);
}
