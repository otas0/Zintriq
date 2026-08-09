/** Skeleton — loading placeholders. */

/** @param {"page"|"inline"|"table"|"card-grid"} [variant] @param {number} [rows] */
export function Skeleton(variant = "page", rows = 3) {
  if (variant === "table") {
    return `<div class="bos-module-loading bos-module-loading--table bos-ui-skeleton" role="status" aria-label="Loading">
      ${Array.from({ length: rows }, () => `<div class="bos-skeleton bos-skeleton--row"></div>`).join("")}
    </div>`;
  }
  if (variant === "inline") {
    return `<p class="bos-loading-inline bos-ui-skeleton" role="status"><span class="bos-spinner" aria-hidden="true"></span> Loading…</p>`;
  }
  if (variant === "card-grid") {
    return `<div class="merchant-grid bos-ui-skeleton" role="status" aria-label="Loading">
      ${Array.from({ length: rows }, () => `<div class="bos-skeleton bos-skeleton--card"></div>`).join("")}
    </div>`;
  }
  return `<div class="bos-module-loading bos-ui-skeleton" role="status" aria-label="Loading">
    <div class="bos-skeleton bos-skeleton--card"></div>
    ${Array.from({ length: Math.max(1, rows - 1) }, () => `<div class="bos-skeleton bos-skeleton--row"></div>`).join("")}
  </div>`;
}

/** @deprecated */
export const loadingState = Skeleton;
