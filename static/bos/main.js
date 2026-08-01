import { MODULE_REGISTRY } from "./features/registry.js";
import { mountInteractiveModule } from "./features/module-page.js";
import { mountHomePage } from "./features/home-page.js";
import { initCommandPalette } from "./core/command-palette.js";
import { initNavigation } from "./core/nav.js";
import { initGlobalSearchUi, initSearchShortcut } from "./core/search-ui.js";
import { initNotifications } from "./platform/notifications-ui.js";
import { openObjectDetail, openCreateObject, parseObjectHash, closeObjectDrawer } from "./platform/object-detail.js";
import { closeDrawer, showToast, initToastUndo } from "./services/api.js";
import { selection } from "./services/selection.js";
import * as store from "./core/store.js";
import { initQuickActions } from "./core/quick-actions.js";
import { isSidebarCollapsed, toggleSidebarCollapsed } from "./core/ui-state.js";

/** @param {string} moduleId @param {HTMLElement} root */
export function mountModule(moduleId, root) {
  selection.clear();
  const toolbarActions = document.getElementById("bos-toolbar-actions");
  if (toolbarActions) {
    const keep = toolbarActions.querySelector("#bos-notifications-btn");
    const panel = toolbarActions.querySelector("#bos-notifications-panel");
    toolbarActions.innerHTML = "";
    if (keep) toolbarActions.appendChild(keep);
    if (panel) toolbarActions.appendChild(panel);
  }

  if (moduleId === "home") {
    mountHomePage(root);
    return;
  }

  const config = MODULE_REGISTRY[moduleId];
  if (config) {
    mountInteractiveModule(root, moduleId, config);
    return;
  }

  root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Module not found</p></div>`;
}

export function closeDrawerFully() {
  closeObjectDrawer();
}

function handleDeepLink() {
  const ref = parseObjectHash();
  if (!ref) return;
  if (store.getById(ref.collection, ref.id)) {
    openObjectDetail(ref.collection, ref.id);
  }
}

export function initShell() {
  const sidebar = document.getElementById("bos-sidebar");
  const backdrop = document.getElementById("bos-sidebar-backdrop");
  const menuBtn = document.getElementById("bos-menu-btn");
  const closeBtn = document.getElementById("bos-sidebar-close");
  const drawerClose = document.getElementById("bos-drawer-close");

  const openSidebar = () => { sidebar?.classList.add("is-open"); backdrop?.classList.remove("hidden"); };
  const closeSidebar = () => { sidebar?.classList.remove("is-open"); backdrop?.classList.add("hidden"); };

  menuBtn?.addEventListener("click", openSidebar);
  closeBtn?.addEventListener("click", closeSidebar);
  backdrop?.addEventListener("click", closeSidebar);
  drawerClose?.addEventListener("click", closeDrawerFully);

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const palette = document.getElementById("bos-command-palette");
    if (palette && !palette.classList.contains("hidden")) return;
    const drawer = document.getElementById("bos-drawer");
    if (drawer && !drawer.classList.contains("hidden")) {
      e.preventDefault();
      closeDrawerFully();
    }
  });

  initCommandPalette();
  initSearchShortcut();
  initNotifications();
  initToastUndo();
  initQuickActions();

  if (isSidebarCollapsed()) {
    sidebar?.classList.add("is-collapsed");
    document.querySelector(".bos-app")?.classList.add("bos-sidebar-collapsed");
  }

  document.getElementById("bos-sidebar")?.querySelector(".bos-brand")?.addEventListener("dblclick", () => {
    const collapsed = toggleSidebarCollapsed();
    sidebar?.classList.toggle("is-collapsed", collapsed);
    document.querySelector(".bos-app")?.classList.toggle("bos-sidebar-collapsed", collapsed);
  });

  const moduleId = window.BOS_MODULE || document.body.dataset.module || "";
  initNavigation(moduleId);
  initGlobalSearchUi();

  window.addEventListener("bos:open-object", (e) => {
    const { collection, id } = e.detail || {};
    if (collection && id) openObjectDetail(collection, id);
  });

  window.addEventListener("bos:create-object", (e) => {
    const { collection } = e.detail || {};
    if (collection) openCreateObject(collection);
  });

  const theme = localStorage.getItem("bos-theme");
  if (theme) document.documentElement.setAttribute("data-theme", theme);
}

export function initModule() {
  const root = document.getElementById("bos-module-root");
  const loading = document.getElementById("bos-module-loading");
  const moduleId = window.BOS_MODULE || root?.dataset.module;
  if (!root || !moduleId) return;

  const mount = () => {
    try {
      mountModule(moduleId, root);
      loading?.remove();
      handleDeepLink();
    } catch (error) {
      console.error(error);
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Module failed to load</p><p class="bos-empty__text">${error instanceof Error ? error.message : "Unknown error"}</p></div>`;
      showToast("Module failed to load");
      loading?.remove();
    }
  };

  if (loading) {
    requestAnimationFrame(() => {
      requestAnimationFrame(mount);
    });
  } else {
    mount();
  }
}

initShell();
initModule();
