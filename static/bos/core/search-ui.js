import { escapeHtml } from "../services/search.js";
import { globalSearchGrouped } from "../services/global-search.js";

/** Global search dropdown — API-backed workspace search. */
export function initGlobalSearchUi() {
  const input = document.getElementById("bos-search-input");
  const results = document.getElementById("bos-global-search-results");
  if (!input || !results) return;

  const moduleId = window.BOS_MODULE || "";
  const globalOnly = moduleId === "organizations";
  if (!globalOnly) return;

  let seq = 0;
  input.addEventListener("input", async () => {
    const q = input.value.trim();
    if (!q) {
      results.classList.add("hidden");
      results.innerHTML = "";
      return;
    }
    const mySeq = ++seq;
    const { api } = await globalSearchGrouped(q);
    if (mySeq !== seq) return;
    results.innerHTML = api.length
      ? api.map((h) => `<a class="bos-global-hit" href="${escapeHtml(h.href)}">${escapeHtml(h.label)} <span>${escapeHtml(h.type)}</span></a>`).join("")
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
    const filterRow = document.getElementById("bos-filter-row");
    const moduleSearch = document.getElementById("bos-search-input");
    if (moduleSearch && filterRow && !filterRow.classList.contains("hidden")) {
      moduleSearch.focus();
      return;
    }
    window.dispatchEvent(new CustomEvent("bos:open-command-palette"));
  });
}
