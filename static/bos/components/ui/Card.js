/** Card — universal container with optional actions. */

import { esc } from "./_utils.js";

/**
 * @param {object} opts
 * @param {string} [opts.title]
 * @param {string} [opts.bodyHtml]
 * @param {string} [opts.footerHtml]
 * @param {string} [opts.extraClass]
 * @param {string|number} [opts.id]
 * @param {boolean} [opts.clickable]
 */
export function Card({
  title = "",
  bodyHtml = "",
  footerHtml = "",
  extraClass = "",
  id = "",
  clickable = false,
} = {}) {
  return `<article class="bos-ui-card bos-card${clickable ? " bos-ui-card--clickable" : ""}${extraClass ? ` ${extraClass}` : ""}"${id ? ` data-id="${esc(String(id))}"` : ""}>
    ${title ? `<header class="bos-ui-card__head"><h3 class="bos-ui-card__title">${esc(title)}</h3></header>` : ""}
    ${bodyHtml ? `<div class="bos-ui-card__body">${bodyHtml}</div>` : ""}
    ${footerHtml ? `<footer class="bos-ui-card__foot">${footerHtml}</footer>` : ""}
  </article>`;
}

/** Render a grid of card HTML strings. */
export function CardGrid(items, renderCard, { extraClass = "" } = {}) {
  if (!items?.length) return "";
  return `<div class="merchant-grid bos-ui-card-grid${extraClass ? ` ${extraClass}` : ""}">${items.map(renderCard).join("")}</div>`;
}

/**
 * @param {HTMLElement} container
 * @param {object[]} items
 * @param {(item: object) => string} renderCard
 * @param {object} [opts]
 * @returns {boolean}
 */
export function mountCardGrid(container, items, renderCard, opts = {}) {
  if (!container || !items?.length) return false;
  container.innerHTML = CardGrid(items, renderCard, opts);
  return true;
}
