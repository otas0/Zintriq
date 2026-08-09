/** PageHeader — fix resourceRow import */
import { StatusBadge } from "../ui/Badge.js";
import { esc } from "../ui/_utils.js";

export function PageHeader({ title, subtitle = "", actionsHtml = "" }) {
  return `<header class="merchant-page-head bos-ui-page-header">
    <div class="merchant-page-head__text">
      <h1 class="merchant-page-head__title">${esc(title)}</h1>
      ${subtitle ? `<p class="merchant-page-head__subtitle">${esc(subtitle)}</p>` : ""}
    </div>
    ${actionsHtml ? `<div class="merchant-page-head__actions">${actionsHtml}</div>` : ""}
  </header>`;
}

export const pageHeader = PageHeader;

export function setPageActions(html) {
  clearPageActions();
  const toolbar = document.getElementById("bos-page-actions-mount");
  if (!toolbar || !html) return;
  const el = document.createElement("div");
  el.id = "bos-page-actions";
  el.className = "bos-page-actions";
  el.innerHTML = html;
  toolbar.insertBefore(el, toolbar.firstChild);
}

export function clearPageActions() {
  document.getElementById("bos-page-actions")?.remove();
}

export function sectionHeader({ title, actionsHtml = "" }) {
  return `<div class="bos-panel-head">
    <h2 class="bos-panel-title">${esc(title)}</h2>
    ${actionsHtml ? `<div class="bos-panel-head__actions">${actionsHtml}</div>` : ""}
  </div>`;
}

export function resourceRow({ title, status = "", meta = "", actionsHtml = "", id = "" }) {
  return `<article class="bos-resource-row"${id ? ` data-id="${esc(String(id))}"` : ""}>
    <div class="bos-resource-row__main"${id ? ` data-open="${esc(String(id))}"` : ""}>
      <strong>${esc(title)}</strong>
      ${meta ? `<p class="bos-resource-row__meta cp-muted">${meta}</p>` : ""}
    </div>
    <div class="bos-resource-row__aside">
      ${status ? StatusBadge(status) : ""}
      ${actionsHtml ? `<div class="bos-resource-row__actions">${actionsHtml}</div>` : ""}
    </div>
  </article>`;
}
