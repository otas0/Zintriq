/** Business OS — Assets (API-backed QR domain aggregate). */

import { fetchJson, esc, wsQuery } from "../services/bos-api.js";

const TYPE_LABELS = {
  store_qr: "Store QR",
  business_card: "Business card",
  product_qr: "Product QR",
  event: "Event pass",
  check_in: "Check-in point",
};

export async function mountAssetsPage(root) {
  root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading assets…</p></div>`;
  try {
    const assets = await fetchJson(`/api/assets${wsQuery()}`);
    if (!assets.length) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No assets yet</p><p>QR codes and customer touchpoints from your experiences appear here.</p><a class="bos-btn bos-btn-primary bos-btn-sm" href="/app/store">Open store</a></div>`;
      return;
    }
    root.innerHTML = `
      <div class="bos-table-wrap">
        <table class="bos-table">
          <thead><tr><th>Name</th><th>Type</th><th>Code</th><th>Store</th><th></th></tr></thead>
          <tbody>${assets.map((a) => `<tr>
            <td>${esc(a.name || a.code || "—")}</td>
            <td>${esc(TYPE_LABELS[a.asset_type] || a.asset_type)}</td>
            <td>${esc(a.code || "—")}</td><td>${esc(a.store_name)}</td>
            <td>${a.href ? `<a class="bos-btn bos-btn-ghost bos-btn-sm" href="${esc(a.href)}">Manage</a>` : ""}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  } catch (err) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load assets</p><p>${esc(err instanceof Error ? err.message : "Error")}</p></div>`;
  }
}
