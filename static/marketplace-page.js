/**
 * Community list inside the desktop app.
 * Browse is open. Remix creates a project in this app and does not run package code.
 */
import { api } from "/static/builder/universal-api.js";

const grid = document.getElementById("zm-community-grid");
const empty = document.getElementById("zm-community-empty");
const search = document.getElementById("zm-community-search");
const clearBtn = document.getElementById("zm-community-clear");
const filters = document.querySelectorAll(".zm-community-filter[data-type]");
const sorts = document.querySelectorAll(".zm-community-filter[data-sort]");
const boot = window.COMMUNITY_BOOT || {};
const loggedIn = Boolean(boot.loggedIn);
const builderUrl = boot.studioUrl || boot.builderUrl || "/studio";
const t = (key) => {
  const value = boot.i18n && boot.i18n[key];
  return value == null ? "" : String(value);
};
const fill = (key, vars) => {
  let text = t(key);
  Object.keys(vars || {}).forEach((name) => {
    text = text.replaceAll("{" + name + "}", String(vars[name]));
  });
  return text;
};

let activeType = "";
let activeSort = "popular";
let dialog;

const esc = (value = "") => {
  const node = document.createElement("span");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
};

function showEmpty(on) {
  if (!empty) return;
  empty.classList.toggle("hidden", !on);
  empty.toggleAttribute("hidden", !on);
  empty.setAttribute("aria-hidden", on ? "false" : "true");
  if (grid) grid.classList.toggle("hidden", on);
}

function card(item) {
  const official = item.trust_level === "official";
  const name = item.creator?.display_name || item.publisher || "";
  const count = item.install_count || 0;
  const installs = fill(Number(count) === 1 ? "installsOne" : "installs", { n: count });
  return `<article class="zm-community-card" data-package-id="${esc(item.id)}">
    <div class="zm-community-card__body">
      <div class="zm-community-card__badges">
        ${official ? `<span class="zm-community-badge zm-community-badge--official">${esc(t("official"))}</span>` : ""}
        <span class="zm-community-badge">${esc(item.package_type === "template" ? t("template") : t("project"))}</span>
      </div>
      <h2>${esc(item.name)}</h2>
      <p>${esc(item.description || "")}</p>
      <div class="zm-community-card__meta">${esc(fill("by", { name }))} · ${esc(installs)}</div>
    </div>
    <div class="zm-community-card__actions">
      <button type="button" class="zw-btn zw-btn--primary" data-view-package="${esc(item.id)}">${esc(t("overview"))}</button>
    </div>
  </article>`;
}

function sortItems(items) {
  const copy = items.slice();
  if (activeSort === "new") {
    copy.sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || "")));
  } else if (activeSort === "remixed") {
    copy.sort((a, b) => (b.remix_count || 0) - (a.remix_count || 0));
  } else {
    copy.sort((a, b) => (b.install_count || 0) - (a.install_count || 0));
  }
  return copy;
}

let lastItems = [];

function desktopCatalog() {
  return Boolean(window.zintriqDesktop && typeof window.zintriqDesktop.listCatalog === "function");
}

async function fetchPackages(params) {
  if (desktopCatalog()) {
    const query = Object.fromEntries(new URLSearchParams(params).entries());
    const data = await window.zintriqDesktop.listCatalog(query);
    return data && data.packages ? data.packages : [];
  }
  const { packages } = await api.marketplacePackages(params.toString());
  return packages || [];
}

async function fetchPackage(packageId) {
  if (desktopCatalog()) {
    const found = lastItems.find((item) => String(item.id) === String(packageId));
    if (found) return found;
    const packages = await fetchPackages("");
    lastItems = packages;
    return packages.find((item) => String(item.id) === String(packageId)) || null;
  }
  return api.marketplacePackage(packageId);
}

async function load() {
  if (!grid) return;
  if (!navigator.onLine) {
    grid.innerHTML = `<div class="zm-community-error">${esc(t("offline"))}</div>`;
    showEmpty(false);
    return;
  }
  showEmpty(false);
  grid.innerHTML = "";
  const params = new URLSearchParams();
  if (search?.value.trim()) params.set("q", search.value.trim());
  if (activeType === "template" || activeType === "project") params.set("type", activeType);
  try {
    let items = await fetchPackages(params);
    if (activeType === "official") items = items.filter((item) => item.trust_level === "official");
    items = sortItems(items);
    lastItems = items;
    if (!items.length) {
      grid.innerHTML = "";
      showEmpty(true);
      return;
    }
    grid.innerHTML = items.map(card).join("");
    grid.querySelectorAll("[data-view-package]").forEach((button) => {
      button.addEventListener("click", () => showDetail(button.dataset.viewPackage));
    });
  } catch (error) {
    grid.innerHTML = `<div class="zm-community-error">${esc(t("error"))}</div>`;
    showEmpty(false);
  }
}

function ensureDialog() {
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.className = "zm-community-dialog";
  dialog.innerHTML = `<div class="zm-community-dialog__inner" id="zm-community-dialog-content"></div>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  return dialog;
}

async function showDetail(packageId) {
  const dlg = ensureDialog();
  const content = document.getElementById("zm-community-dialog-content");
  content.innerHTML = "";
  dlg.showModal();
  try {
    const item = await fetchPackage(packageId);
    if (!item) throw new Error("missing");
    const shareUrl = desktopCatalog()
      ? `zintriq://c/${encodeURIComponent(item.id)}`
      : `${location.origin}/app/community?package=${encodeURIComponent(item.id)}`;
    const remix = item.package_type === "template" || desktopCatalog();
    content.innerHTML = `
      <div class="zm-community-dialog__head">
        <div>
          <p class="zm-community-dialog__eyebrow">${esc(fill("version", { version: item.version || "" }))}</p>
          <h2>${esc(item.name)}</h2>
        </div>
        <button type="button" class="zw-btn zw-btn--secondary" data-close>×</button>
      </div>
      <p>${esc(t("overview"))}</p>
      <p>${esc(item.description || "")}</p>
      <p>${esc(fill("updated", { date: item.updated_at || item.published_at || "" }))}</p>
      ${remix ? `<p>${esc(t("remixHelp"))}</p>` : ""}
      <div class="zm-community-dialog__actions">
        ${remix && loggedIn ? `<button type="button" class="zw-btn zw-btn--primary" data-remix-package="${esc(item.id)}">${esc(t("useTemplate"))}</button>` : ""}
        ${remix && !loggedIn ? `<a class="zw-btn zw-btn--primary" href="/login">${esc(t("remix"))}</a>` : ""}
        <button type="button" class="zw-btn zw-btn--secondary" data-copy-link="${esc(shareUrl)}">${esc(t("share"))}</button>
        <button type="button" class="zw-btn zw-btn--secondary" data-report="${esc(item.id)}">${esc(t("report"))}</button>
      </div>
      <p data-copy-status hidden></p>`;
    content.querySelector("[data-close]")?.addEventListener("click", () => dlg.close());
    content.querySelector("[data-copy-link]")?.addEventListener("click", async (event) => {
      const url = event.currentTarget.getAttribute("data-copy-link");
      try {
        await navigator.clipboard.writeText(url);
      } catch (copyError) {
        return;
      }
      const status = content.querySelector("[data-copy-status]");
      if (status) {
        status.hidden = false;
        status.textContent = t("copied");
      }
    });
    content.querySelector("[data-remix-package]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      if (desktopCatalog() && window.zintriqDesktop.openShare) {
        await window.zintriqDesktop.openShare(button.getAttribute("data-remix-package"));
        return;
      }
      const result = await api.remixPackage(button.getAttribute("data-remix-package"), {});
      window.location.href = `${builderUrl}/p/${result.project_id}`;
    });
  } catch (error) {
    content.innerHTML = `<div class="zm-community-error">${esc(t("error"))}</div>`;
  }
}

filters.forEach((button) => {
  button.addEventListener("click", () => {
    activeType = button.dataset.type || "";
    filters.forEach((item) => {
      const on = item === button;
      item.classList.toggle("zm-community-filter--active", on);
      item.setAttribute("aria-pressed", on ? "true" : "false");
    });
    load();
  });
});

sorts.forEach((button) => {
  button.addEventListener("click", () => {
    activeSort = button.dataset.sort || "popular";
    sorts.forEach((item) => {
      const on = item === button;
      item.classList.toggle("zm-community-filter--active", on);
      item.setAttribute("aria-pressed", on ? "true" : "false");
    });
    load();
  });
});

clearBtn?.addEventListener("click", () => {
  if (search) search.value = "";
  activeType = "";
  filters.forEach((item) => {
    const on = !item.dataset.type;
    item.classList.toggle("zm-community-filter--active", on);
    item.setAttribute("aria-pressed", on ? "true" : "false");
  });
  load();
});

let searchTimer;
search?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(load, 220);
});

load();
if (boot.pendingPackage) showDetail(boot.pendingPackage);
