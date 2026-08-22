/** Zintriq — Catalog (API-backed products across workspace stores). */

import { statusBadge } from "../components/index.js";
import { showToast } from "../services/api.js";
import { fetchJson, esc, wsQuery, money } from "../services/bos-api.js";

export async function mountCatalogPage(root) {
  root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading catalog…</p></div>`;
  try {
    const items = await fetchJson(`/api/catalog${wsQuery()}`);
    if (!items.length) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No products yet</p><p>Products linked to your workspace appear here. Add catalog content via an Information experience.</p><a class="bos-btn bos-btn-primary bos-btn-sm" href="/app/store#experiences">Create experience</a></div>`;
      return;
    }
    root.innerHTML = `
      <div class="bos-table-wrap">
        <table class="bos-table">
          <thead><tr><th>Name</th><th>SKU</th><th>Store</th><th>Price</th><th>Status</th><th></th></tr></thead>
          <tbody>${items.map((i) => `<tr>
            <td>${esc(i.name)}</td><td>${esc(i.sku || "—")}</td><td>${esc(i.store_name)}</td>
            <td>${money(i.price)}</td><td>${statusBadge(i.status)}</td>
            <td>${i.href ? `<a class="bos-btn bos-btn-ghost bos-btn-sm" href="${esc(i.href)}">Edit in store</a>` : ""}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  } catch (err) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load catalog</p><p>${esc(err instanceof Error ? err.message : "Error")}</p></div>`;
    showToast("Catalog load failed");
  }
}
