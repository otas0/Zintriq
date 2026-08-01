import * as store from "./store.js";
import { MODULE_NAV } from "../features/registry.js";
import { escapeHtml } from "../services/search.js";

export function renderBreadcrumbs(moduleId) {
  const el = document.getElementById("bos-breadcrumbs");
  if (!el) return;
  const mod = MODULE_NAV.find((m) => m.id === moduleId);
  if (!mod || moduleId === "home") {
    el.innerHTML = "";
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML = `
    <a href="/app">Home</a>
    <span class="bos-breadcrumbs__sep" aria-hidden="true">/</span>
    <span aria-current="page">${escapeHtml(mod.label)}</span>`;
}

export function renderSidebarFavorites() {
  const host = document.getElementById("bos-sidebar-pinned");
  if (!host) return;
  const favoriteIds = new Set(store.getFavorites());
  const pinned = MODULE_NAV.filter((m) => favoriteIds.has(m.id) && m.id !== "home");
  if (!pinned.length) {
    host.innerHTML = "";
    host.classList.add("hidden");
    return;
  }
  host.classList.remove("hidden");
  const active = document.body.dataset.module || "";
  host.innerHTML = `
    <p class="bos-sidebar__section-label">Pinned</p>
    ${pinned.map((m) => `<a href="${m.path}" class="bos-nav__item${active === m.id ? " is-active" : ""}"><span class="bos-nav__icon">${escapeHtml(m.icon)}</span><span class="bos-nav__label">${escapeHtml(m.label)}</span></a>`).join("")}`;
}

export function wireSidebarPinButtons() {
  document.querySelectorAll(".bos-nav__item[data-module-id]").forEach((link) => {
    const moduleId = link.getAttribute("data-module-id");
    if (!moduleId || moduleId === "home") return;
    if (link.querySelector(".bos-nav__pin")) return;

    const pin = document.createElement("button");
    pin.type = "button";
    pin.className = `bos-nav__pin${store.getFavorites().includes(moduleId) ? " is-pinned" : ""}`;
    pin.setAttribute("aria-label", "Pin module");
    pin.textContent = store.getFavorites().includes(moduleId) ? "★" : "☆";
    pin.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      store.toggleFavorite(moduleId);
      const pinned = store.getFavorites().includes(moduleId);
      pin.classList.toggle("is-pinned", pinned);
      pin.textContent = pinned ? "★" : "☆";
      pin.setAttribute("aria-label", pinned ? "Unpin module" : "Pin module");
      renderSidebarFavorites();
    });
    link.appendChild(pin);
  });
  renderSidebarFavorites();
}

export function initNavigation(moduleId) {
  renderBreadcrumbs(moduleId);
  wireSidebarPinButtons();
  store.subscribe((col) => {
    if (col === "favorites") renderSidebarFavorites();
  });
}
