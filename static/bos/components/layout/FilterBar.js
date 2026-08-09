/** FilterBar — standard tab filters (All, Active, Draft, …). */

import { esc } from "../ui/_utils.js";

/**
 * @param {{ id: string, label: string }[]} tabs
 * @param {string} active
 */
export function FilterBar(tabs, active) {
  return `<nav class="bos-subnav bos-subnav--filters bos-ui-filter-bar" aria-label="Filter">
    ${tabs.map(({ id, label }) =>
      `<button type="button" class="bos-subnav__item${active === id ? " is-active" : ""}" data-filter="${esc(id)}">${esc(label)}</button>`
    ).join("")}
  </nav>`;
}

/**
 * @param {HTMLElement} container
 * @param {{ id: string, label: string }[]} tabs
 * @param {string} active
 * @param {(id: string) => void} onChange
 */
export function mountFilterBar(container, tabs, active, onChange) {
  if (!container) return;
  container.innerHTML = FilterBar(tabs, active);
  container.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => onChange(btn.dataset.filter || "all"));
  });
}

/** Chip-style filter bar (legacy). */
export function mountFilterChips(container, filters, active, onChange) {
  if (!container || !filters.length) {
    if (container) container.innerHTML = "";
    return;
  }
  container.innerHTML = filters.map((f) =>
    `<button type="button" class="bos-filter-chip${active === f ? " is-active" : ""}" data-filter="${esc(f)}">${esc(f === "all" ? "All" : f.replace(/_/g, " "))}</button>`
  ).join("");
  container.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => onChange(btn.getAttribute("data-filter") || "all"));
  });
}

/** @deprecated */
export const renderFilterTabs = mountFilterBar;
