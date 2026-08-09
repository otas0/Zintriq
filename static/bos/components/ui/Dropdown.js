/** Dropdown — actions, filters, workspace panels. */

import { esc } from "./_utils.js";

/**
 * @param {HTMLElement} anchor
 * @param {{ id: string, label: string, danger?: boolean }[]} items
 * @param {(id: string) => void} onSelect
 */
export function openDropdown(anchor, items, onSelect) {
  closeDropdown();
  const rect = anchor.getBoundingClientRect();
  const menu = document.createElement("div");
  menu.className = "bos-ui-dropdown material-panel";
  menu.id = "bos-ui-dropdown-active";
  menu.setAttribute("role", "menu");
  menu.innerHTML = items.map((item) =>
    `<button type="button" class="bos-ui-dropdown__item${item.danger ? " bos-ui-dropdown__item--danger" : ""}" role="menuitem" data-id="${esc(item.id)}">${esc(item.label)}</button>`
  ).join("");
  menu.style.position = "fixed";
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.max(8, rect.left)}px`;
  menu.style.minWidth = `${Math.max(rect.width, 160)}px`;
  document.body.appendChild(menu);

  menu.querySelectorAll("[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      onSelect(btn.getAttribute("data-id") || "");
      closeDropdown();
    });
  });

  setTimeout(() => {
    document.addEventListener("click", _outsideClick);
    document.addEventListener("keydown", _escClose);
  }, 0);
}

function _outsideClick(e) {
  const menu = document.getElementById("bos-ui-dropdown-active");
  if (menu && !menu.contains(e.target)) closeDropdown();
}

function _escClose(e) {
  if (e.key === "Escape") closeDropdown();
}

export function closeDropdown() {
  document.getElementById("bos-ui-dropdown-active")?.remove();
  document.removeEventListener("click", _outsideClick);
  document.removeEventListener("keydown", _escClose);
}
