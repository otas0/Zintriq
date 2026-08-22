/** Zintriq — Store hub (experiences + responses + store info). */

import { fetchJson } from "../services/bos-api.js";
import { button, pageHeader, loadingState, emptyState, setPageActions } from "../components/index.js";
import { mountQrExperiencesPage } from "./qr-experiences-page.js";
import { mountResponsesPage } from "./responses-page.js";

const STORE_TABS = [
  ["overview", "Overview"],
  ["experiences", "Experiences"],
  ["responses", "Responses"],
];

function storeTabFromHash() {
  const m = window.location.hash.match(/^#?(overview|experiences|responses|experience\/\d+|builder\/\d+)/);
  if (!m) return "overview";
  if (m[1].startsWith("experience") || m[1].startsWith("builder")) return "experiences";
  return m[1];
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function renderStoreOverview(panel) {
  panel.innerHTML = loadingState();
  try {
    const [ws, summary] = await Promise.all([
      fetchJson("/api/workspaces/current").catch(() => ({})),
      fetchJson("/api/home/summary").catch(() => ({})),
    ]);
    const stores = ws?.id
      ? await fetchJson(`/api/workspaces/${ws.id}/stores`).catch(() => [])
      : [];
    const store = Array.isArray(stores) && stores[0] ? stores[0] : null;
    const expCount = summary.total_experiences ?? summary.qr_experiences?.length ?? 0;
    const respCount = summary.total_responses ?? summary.recent_responses?.length ?? 0;
    const activeCount = summary.active_experiences ?? summary.qr_status?.filter?.((q) => q.status === "active")?.length ?? 0;

    panel.innerHTML = `
      <section class="bos-dash-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:24px">
        <article class="bos-stat-card"><span class="bos-stat-val">${activeCount}</span><span class="bos-stat-lbl">Active experiences</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${expCount}</span><span class="bos-stat-lbl">Total experiences</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${respCount}</span><span class="bos-stat-lbl">Responses</span></article>
      </section>
      <div class="bos-panel" style="padding:20px;margin-bottom:16px">
        <h3 class="bos-panel-title" style="margin:0 0 8px">${escapeHtml(store?.name || ws.name || "Your store")}</h3>
        <p class="cp-muted" style="margin:0 0 16px">${escapeHtml(ws.name || "")} workspace · customer experiences and feedback live here.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="bos-btn bos-btn-primary bos-btn-sm" href="/app/store#experiences">Manage experiences</a>
          <a class="bos-btn bos-btn-ghost bos-btn-sm" href="/app/store#responses">View responses</a>
          ${store?.slug ? `<a class="bos-btn bos-btn-ghost bos-btn-sm" href="/manage/${escapeHtml(store.slug)}" target="_blank" rel="noopener">Store settings</a>` : ""}
          ${store?.slug ? `<a class="bos-btn bos-btn-ghost bos-btn-sm" href="/store/${escapeHtml(store.slug)}" target="_blank" rel="noopener">Public storefront</a>` : ""}
        </div>
      </div>`;
  } catch (err) {
    panel.innerHTML = emptyState({
      title: "Could not load store",
      text: err.message,
    });
  }
}

/** @param {HTMLElement} root */
export async function mountStorePage(root) {
  let tab = storeTabFromHash();

  const paint = async () => {
    tab = storeTabFromHash();
    root.innerHTML = `
      <div class="merchant-page">
        ${pageHeader({
          title: "Store",
          subtitle: "Experiences, QR codes, and customer responses for your business",
          actionsHtml: tab === "experiences"
            ? button({ variant: "primary", label: "Create Experience", id: "store-create-exp", sm: true })
            : "",
        })}
        <nav class="bos-subnav" style="margin:0 0 20px" id="store-tabs">
          ${STORE_TABS.map(([id, label]) =>
            `<button type="button" class="bos-subnav__item${tab === id ? " is-active" : ""}" data-store-tab="${id}">${label}</button>`
          ).join("")}
        </nav>
        <div id="store-panel"></div>
      </div>`;

    const panel = root.querySelector("#store-panel");
    root.querySelectorAll("[data-store-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        window.location.hash = btn.dataset.storeTab;
        paint();
      });
    });

    if (tab === "overview") {
      setPageActions(null);
      await renderStoreOverview(panel);
    } else if (tab === "experiences") {
      setPageActions(button({ variant: "primary", label: "Create Experience", id: "store-create-exp-top", sm: true }));
      await mountQrExperiencesPage(panel, { embedded: true });
      document.getElementById("store-create-exp")?.addEventListener("click", () => {
        document.getElementById("qrx-create-top")?.click();
      });
      document.getElementById("store-create-exp-top")?.addEventListener("click", () => {
        document.getElementById("qrx-create-top")?.click();
      });
    } else if (tab === "responses") {
      setPageActions(null);
      await mountResponsesPage(panel, { embedded: true });
    }
  };

  window.addEventListener("hashchange", () => paint());
  await paint();
}
