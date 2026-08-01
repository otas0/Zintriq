/** @typedef {Object} BosItem
 * @property {string|number} id
 * @property {string} [name]
 * @property {string} [status]
 */

/**
 * @param {string} query
 * @param {Record<string, unknown>[]} items
 * @param {(item: Record<string, unknown>) => string} haystack
 */
export function searchItems(query, items, haystack) {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  const tokens = q.split(/\s+/);
  return items.filter((item) => tokens.every((token) => haystack(item).includes(token)));
}

/**
 * @param {Record<string, unknown>[]} items
 * @param {string} filter
 * @param {string} field
 */
export function filterByStatus(items, filter, field = "status") {
  if (!filter || filter === "all") return items;
  return items.filter((item) => String(item[field] || "").toLowerCase() === filter);
}

/**
 * @param {Record<string, unknown>[]} items
 * @param {string} key
 * @param {boolean} asc
 */
export function sortItems(items, key, asc = true) {
  const sorted = [...items].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return String(av).localeCompare(String(bv), undefined, { numeric: true });
  });
  return asc ? sorted : sorted.reverse();
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
