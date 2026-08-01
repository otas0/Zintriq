import { escapeHtml } from "../services/search.js";

/** @param {string} status */
export function statusBadge(status) {
  const key = String(status || "unknown").toLowerCase().replace(/\s+/g, "_");
  return `<span class="bos-badge bos-badge--${escapeHtml(key)}">${escapeHtml(status || "—")}</span>`;
}

/** @param {string} label @param {string} [variant] */
export function tag(label, variant = "") {
  return `<span class="bos-tag${variant ? ` bos-tag--${variant}` : ""}">${escapeHtml(label)}</span>`;
}

/** @param {string} title @param {string} [text] @param {string} [actionHtml] @param {string} [extraClass] */
export function emptyState(title, text = "", actionHtml = "", extraClass = "") {
  return `<div class="bos-empty${extraClass ? ` ${extraClass}` : ""}">
    <p class="bos-empty__title">${escapeHtml(title)}</p>
    ${text ? `<p class="bos-empty__text">${escapeHtml(text)}</p>` : ""}
    ${actionHtml}
  </div>`;
}

/**
 * @param {string[]} filters
 * @param {string} active
 * @param {(filter: string) => void} onChange
 */
export function renderFilterBar(container, filters, active, onChange) {
  if (!container || !filters.length) {
    if (container) container.innerHTML = "";
    return;
  }
  container.innerHTML = filters
    .map(
      (f) =>
        `<button type="button" class="bos-filter-chip${active === f ? " is-active" : ""}" data-filter="${escapeHtml(f)}">${escapeHtml(f === "all" ? "All" : f.replace(/_/g, " "))}</button>`
    )
    .join("");
  container.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => onChange(btn.getAttribute("data-filter") || "all"));
  });
}

/**
 * @param {Record<string, unknown>[]} items
 * @param {{ key: string, label: string, render?: (row: Record<string, unknown>) => string }[]} columns
 * @param {{ selectable?: boolean, selected?: Set<string|number>, onRowClick?: (row: Record<string, unknown>) => void, onToggle?: (id: string|number) => void, onSelectAll?: (checked: boolean, rows: Record<string, unknown>[]) => void }} options
 */
export function renderDataTable(container, items, columns, options = {}) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = emptyState("No results", "Try adjusting search or filters.");
    return;
  }
  const head = columns.map((c) => `<th>${escapeHtml(c.label)}</th>`).join("");
  const body = items
    .map((row) => {
      const id = row.id;
      const selected = options.selected?.has(id);
      const cells = columns
        .map((c) => {
          const content = c.render ? c.render(row) : escapeHtml(row[c.key]);
          return `<td>${content}</td>`;
        })
        .join("");
      const check = options.selectable
        ? `<td class="bos-table__check"><input type="checkbox"${selected ? " checked" : ""} data-id="${escapeHtml(String(id))}"></td>`
        : "";
      return `<tr data-clickable data-id="${escapeHtml(String(id))}" class="${selected ? "is-selected" : ""}">${check}${cells}</tr>`;
    })
    .join("");
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

/**
 * @param {Record<string, unknown>[]} items
 * @param {(item: Record<string, unknown>) => string} renderCard
 */
export function renderCardGrid(container, items, renderCard) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = emptyState("Nothing here yet");
    return;
  }
  container.innerHTML = `<div class="bos-card-grid">${items.map(renderCard).join("")}</div>`;
}

/**
 * @param {MouseEvent} event
 * @param {{ label: string, action: string }[]} items
 * @param {(action: string) => void} onSelect
 */
export function showContextMenu(event, items, onSelect) {
  const menu = document.getElementById("bos-context-menu");
  if (!menu) return;
  event.preventDefault();
  menu.innerHTML = items
    .map((i) => `<button type="button" class="bos-nav__item" data-action="${escapeHtml(i.action)}">${escapeHtml(i.label)}</button>`)
    .join("");
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
