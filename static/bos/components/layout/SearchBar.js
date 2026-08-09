/** SearchBar — reusable search input. */

import { esc } from "../ui/_utils.js";

/**
 * @param {object} opts
 * @param {string} [opts.id]
 * @param {string} [opts.placeholder]
 * @param {string} [opts.value]
 * @param {string} [opts.ariaLabel]
 */
export function SearchBar({
  id = "bos-search",
  placeholder = "Search…",
  value = "",
  ariaLabel = "Search",
}) {
  return `<div class="bos-ui-search">
    <label class="visually-hidden" for="${esc(id)}">${esc(ariaLabel)}</label>
    <input type="search" class="bos-input merchant-search bos-ui-search__input" id="${esc(id)}" placeholder="${esc(placeholder)}" value="${esc(value)}" autocomplete="off">
  </div>`;
}

/** Bind Enter key to callback. */
export function bindSearchBar(input, onSearch) {
  if (!input) return;
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onSearch(input.value || "");
  });
}
