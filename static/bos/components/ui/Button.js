/** Button — primary, secondary, danger, ghost variants. */

import { esc } from "./_utils.js";

/**
 * @param {object} opts
 * @param {"primary"|"secondary"|"danger"|"ghost"} [opts.variant]
 * @param {string} opts.label
 * @param {string} [opts.tag] button | a
 * @param {string} [opts.href]
 * @param {string} [opts.id]
 * @param {string} [opts.type]
 * @param {boolean} [opts.sm]
 * @param {boolean} [opts.loading]
 * @param {boolean} [opts.disabled]
 * @param {string} [opts.extraClass]
 * @param {string} [opts.attrs]
 */
export function Button({
  variant = "secondary",
  label,
  tag = "button",
  href = "",
  id = "",
  type = "button",
  sm = false,
  loading = false,
  disabled = false,
  extraClass = "",
  attrs = "",
} = {}) {
  const cls = [
    "bos-btn",
    "bos-ui-btn",
    variant === "primary" ? "bos-btn-primary" : "",
    variant === "ghost" || variant === "secondary" ? "bos-btn-ghost" : "",
    variant === "danger" ? "bos-btn-danger" : "",
    sm ? "bos-btn-sm" : "",
    loading ? "is-loading" : "",
    extraClass,
  ].filter(Boolean).join(" ");
  const idAttr = id ? ` id="${esc(id)}"` : "";
  const disabledAttr = disabled || loading ? " disabled aria-busy=\"true\"" : "";
  const text = loading ? `${esc(label)}…` : esc(label);
  if (tag === "a") {
    return `<a class="${cls}" href="${esc(href)}"${idAttr} ${attrs}>${text}</a>`;
  }
  return `<button type="${esc(type)}" class="${cls}"${idAttr}${disabledAttr} ${attrs}>${text}</button>`;
}

/** @deprecated use Button */
export const button = Button;
