import * as store from "../core/store.js";
import { escapeHtml } from "../services/search.js";
import { MODULE_NAV } from "./registry.js";
import { getObjectRecents, getObjectFavorites, subscribe as subscribeRecents } from "../platform/recents.js";
import { openObjectDetail } from "../platform/object-detail.js";
import { formatActivityAction } from "../platform/activity.js";

export function mountHomePage(root) {
  const render = () => {
    const orgs = store.getCollection("organizations");
    const workspaces = store.getCollection("workspaces");
    const activities = store.getGlobalActivities(15);
    const moduleRecents = store.getRecents();
    const moduleFavorites = store.getFavorites();
    const objectRecents = getObjectRecents().slice(0, 8);
    const objectFavorites = getObjectFavorites();

    root.innerHTML = `
      <div class="bos-dash-grid">
        <div class="bos-stat-card"><div class="bos-stat-card__value">${orgs.length}</div><div class="bos-stat-card__label">Organizations</div></div>
        <div class="bos-stat-card"><div class="bos-stat-card__value">${workspaces.length}</div><div class="bos-stat-card__label">Workspaces</div></div>
        <div class="bos-stat-card"><div class="bos-stat-card__value">${store.getCollection("catalog").length}</div><div class="bos-stat-card__label">Catalog items</div></div>
        <div class="bos-stat-card"><div class="bos-stat-card__value">${store.getCollection("customers").length}</div><div class="bos-stat-card__label">Customers</div></div>
      </div>

      <h2 class="bos-section-title">Quick access</h2>
      <div class="bos-quick-links bos-home-section">
        <a class="os-btn os-btn-primary os-btn-sm" href="/my-stores">QR Workspace</a>
        ${MODULE_NAV.filter((m) => m.id !== "home").slice(0, 6).map((m) => `<a class="os-btn os-btn-ghost os-btn-sm" href="${m.path}">${escapeHtml(m.icon)} ${escapeHtml(m.label)}</a>`).join("")}
      </div>

      ${objectFavorites.length ? `<h2 class="bos-section-title">Favorite objects</h2>
      <div class="bos-quick-links bos-home-section">${objectFavorites.map((r) => `<button type="button" class="os-btn os-btn-ghost os-btn-sm" data-open-obj="${r.collection}:${r.id}">★ ${escapeHtml(r.label)}</button>`).join("")}</div>` : ""}

      ${moduleFavorites.length ? `<h2 class="bos-section-title">Pinned modules</h2>
      <div class="bos-quick-links bos-home-section">${moduleFavorites.map((id) => {
        const m = MODULE_NAV.find((n) => n.id === id);
        return m ? `<a class="os-btn os-btn-ghost os-btn-sm" href="${m.path}">${escapeHtml(m.icon)} ${escapeHtml(m.label)}</a>` : "";
      }).join("")}</div>` : ""}

      ${objectRecents.length ? `<h2 class="bos-section-title">Recent objects</h2>
      <ul class="bos-activity-list bos-home-section">${objectRecents.map((r) => `<li><button type="button" class="bos-link-btn" data-open-obj="${r.collection}:${r.id}">${escapeHtml(r.label)}</button><span class="bos-home-meta">${escapeHtml(r.collection)}</span></li>`).join("")}</ul>` : ""}

      <h2 class="bos-section-title">Global activity</h2>
      <ul class="bos-activity-list bos-timeline">
        ${activities.length ? activities.map((a) => `<li class="bos-timeline__item">
          <span class="bos-timeline__action">${escapeHtml(formatActivityAction(String(a.action || "updated")))}</span>
          <span class="bos-timeline__msg">${escapeHtml(String(a.message))}</span>
          <span class="bos-timeline__meta">${escapeHtml(String(a.actor))} · ${escapeHtml(String(a.at).slice(0, 10))}</span>
        </li>`).join("") : `<li class="bos-empty bos-empty--inline"><p class="bos-empty__title">No activity yet</p><p class="bos-empty__text">Create or update records to see activity here.</p></li>`}
      </ul>

      <p class="bos-home-footer">Press <kbd>⌘K</kbd> for command palette · navigate the connected graph</p>`;

    root.querySelectorAll("[data-open-obj]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [collection, id] = (btn.getAttribute("data-open-obj") || "").split(":");
        if (collection && id) openObjectDetail(collection, id);
      });
    });
  };

  store.subscribe(() => render());
  subscribeRecents(render);
  render();
}
