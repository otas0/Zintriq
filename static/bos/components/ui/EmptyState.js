/** EmptyState — never show blank screens. */

import { esc } from "./_utils.js";

/**
 * @param {object} opts
 * @param {string} opts.title
 * @param {string} [opts.text]
 * @param {string} [opts.actionHtml]
 * @param {string} [opts.extraClass]
 */
export function EmptyState({ title, text = "", actionHtml = "", extraClass = "" } = {}) {
  return `<div class="bos-empty bos-ui-empty${extraClass ? ` ${extraClass}` : ""}" role="status">
    <p class="bos-empty__title">${esc(title)}</p>
    ${text ? `<p class="bos-empty__text">${esc(text)}</p>` : ""}
    ${actionHtml ? `<div class="bos-empty__actions">${actionHtml}</div>` : ""}
  </div>`;
}

/** @deprecated */
export const emptyState = EmptyState;
