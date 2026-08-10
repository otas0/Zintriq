/** BOS Customer QR tab — overview with links to store manage pages. */

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function fetchJson(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

function countByStore(experiences) {
  const map = new Map();
  for (const row of experiences) {
    if (row.status === "archived") continue;
    const sid = row.store_id;
    if (!sid) continue;
    map.set(sid, (map.get(sid) || 0) + 1);
  }
  return map;
}

/**
 * @param {HTMLElement} root
 * @param {{ storeId?: number | null }} [opts]
 */
export async function mountCustomerQrOverview(root, opts = {}) {
  const { storeId = null } = opts;
  const stores = window.WORKSPACE_BOOT?.stores || [];
  const visible = storeId ? stores.filter((s) => s.id === storeId) : stores;

  root.innerHTML = `<div class="bos-store-qr-overview"><p class="cp-muted">Loading…</p></div>`;

  let landingByStore = new Map();
  try {
    const experiences = await fetchJson("/api/qr-experiences");
    landingByStore = countByStore(experiences);
  } catch {
    /* overview still useful without counts */
  }

  if (!visible.length) {
    root.innerHTML = `
      <div class="bos-store-qr-overview material-panel" style="padding:24px">
        <h2 class="bos-panel-title">Customer QR</h2>
        <p class="cp-muted">Add a store first, then manage shop QR, landing pages, and passes from the store.</p>
        <a class="bos-btn bos-btn-primary bos-btn-sm" href="/create">Add store</a>
      </div>`;
    return;
  }

  const cards = visible.map((store) => {
    const landing = landingByStore.get(store.id) || 0;
    const qrAssets = store.qr_assets ?? store.qr_count ?? 0;
    return `
      <article class="bos-store-qr-card material-panel">
        <h3 class="bos-store-qr-card__name">${escapeHtml(store.name)}</h3>
        <p class="bos-store-qr-card__meta cp-muted">
          ${qrAssets} shop QR · ${landing} landing page${landing === 1 ? "" : "s"}
        </p>
        <div class="bos-store-qr-card__actions">
          <a class="bos-btn bos-btn-primary bos-btn-sm" href="/manage/${escapeHtml(store.slug)}/qr?add=1">Add customer QR</a>
          <a class="bos-btn bos-btn-ghost bos-btn-sm" href="/manage/${escapeHtml(store.slug)}/qr">Manage all</a>
        </div>
      </article>`;
  }).join("");

  root.innerHTML = `
    <div class="bos-store-qr-overview">
      <p class="cp-muted bos-store-qr-overview__lead">
        Edit shop QR, landing pages, and specialized passes in each store — one place per storefront.
      </p>
      <div class="bos-store-qr-grid">${cards}</div>
    </div>`;
}
