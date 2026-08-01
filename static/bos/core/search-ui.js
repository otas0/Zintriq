import * as store from "./store.js";
import { escapeHtml } from "../services/search.js";

/** Global search dropdown for modules without a local list filter. */
export function initGlobalSearchUi() {
  const input = document.getElementById("bos-search-input");
  const results = document.getElementById("bos-global-search-results");
  if (!input || !results) return;

  const moduleId = window.BOS_MODULE || "";
  const globalOnly = moduleId === "home" || moduleId === "organizations";
  if (!globalOnly) return;

  input.addEventListener("input", () => {
    const q = input.value.trim();
    if (!q) {
      results.classList.add("hidden");
      results.innerHTML = "";
      return;
    }
    const hits = store.globalSearch(q);
    results.innerHTML = hits.length
      ? hits.map((h) => `<a class="bos-global-hit" href="${h.path}">${escapeHtml(h.label)} <span>${escapeHtml(h.collection)}</span></a>`).join("")
      : `<p class="bos-palette-empty" style="padding:12px">No results</p>`;
    results.classList.remove("hidden");
  });

  input.addEventListener("blur", () => {
    setTimeout(() => {
      results.classList.add("hidden");
    }, 150);
  });
}

export function initSearchShortcut() {
  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    e.preventDefault();
    document.getElementById("bos-search-input")?.focus();
  });
}
