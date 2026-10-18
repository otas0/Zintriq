import { initShellKeyboard, initShellEvents, initShellContext } from "./core/shell.js";
import { loadWorkspaceList } from "./services/workspace-context.js";
import { initSearchShortcut } from "./core/search-ui.js";
import { closeDrawer, showToast, initToastUndo } from "./services/api.js";
import { clearPageActions } from "./components/index.js";
import { selection } from "./services/selection.js";
import { initQuickActions } from "./core/quick-actions.js";
import { isSidebarCollapsed, toggleSidebarCollapsed } from "./core/ui-state.js";
import { initEventBus } from "./platform/event-bus.js";
import { getActiveWorkspaceId } from "./services/workspace-context.js";
import { initNavigation } from "./core/nav.js";
import { initGlobalSearchUi } from "./core/search-ui.js";
import { initMobileShell } from "./mobile-shell.js";

/** Lazy-load feature modules — only fetch JS for the active page. */
const MODULE_LOADERS = {
  store: () => Promise.resolve(),
  team: () => import("./features/team-page.js").then((m) => m.mountTeamPage),
  settings: () => import("./features/workspaces-page.js").then((m) => m.mountWorkspacesPage),
  workspaces: () => import("./features/workspaces-page.js").then((m) => m.mountWorkspacesPage),
  customers: () => import("./features/responses-page.js").then((m) => m.mountResponsesPage),
  interactions: () => import("./features/responses-page.js").then((m) => m.mountResponsesPage),
  feedback: () => import("./features/responses-page.js").then((m) => m.mountResponsesPage),
};

/** @type {Promise<void>|null} */
let commandPaletteReady = null;

function ensureCommandPalette() {
  if (!commandPaletteReady) {
    commandPaletteReady = import("./core/command-palette.js").then((m) => m.initCommandPalette());
  }
  return commandPaletteReady;
}

window.addEventListener("bos:open-command-palette", (e) => {
  if (commandPaletteReady) return;
  e.stopImmediatePropagation();
  ensureCommandPalette().then(() => {
    window.dispatchEvent(new CustomEvent("bos:open-command-palette"));
  });
}, true);

/** @param {string} moduleId @param {HTMLElement} root */
export async function mountModule(moduleId, root) {
  selection.clear();
  clearPageActions();
  document.getElementById("bos-filter-row")?.classList.add("hidden");
  document.getElementById("bos-create-btn")?.remove();

  const loader = MODULE_LOADERS[moduleId];
  if (!loader) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Module not found</p><p class="bos-empty__text">This platform is not part of Zintriq V1.</p></div>`;
    return;
  }

  try {
    const mount = await loader();
    const result = mount(root);
    if (result && typeof result.then === "function") {
      await result;
    }
  } catch (err) {
    console.error(err);
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Module failed to load</p><p class="bos-empty__text">${err instanceof Error ? err.message : "Unknown error"}</p></div>`;
    showToast("Module failed to load");
  }
}

export function closeDrawerFully() {
  document.getElementById("bos-drawer")?.classList.add("hidden");
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

  initSearchShortcut();
  initToastUndo();
  initQuickActions();

  // Command palette loads on first ⌘K / Ctrl+K (not idle-prefetched).
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      ensureCommandPalette();
    }
  }, { once: false, capture: true });

  const workspaceReady = loadWorkspaceList().catch(() => {});
  initShellKeyboard();
  initShellEvents();
  initShellContext();

  workspaceReady.then(() => {
    initEventBus(getActiveWorkspaceId);
  });

  window.addEventListener("bos:remount-module", () => {
    const root = document.getElementById("bos-module-root");
    const moduleId = window.BOS_MODULE || document.body.dataset.module;
    if (root && moduleId) {
      mountModule(moduleId, root);
      initNavigation(moduleId);
    }
  });

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

  const theme = localStorage.getItem("bos-theme");
  if (theme) document.documentElement.setAttribute("data-theme", theme);
}

export function initModule() {
  const root = document.getElementById("bos-module-root");
  const loading = document.getElementById("bos-module-loading");
  const moduleId = window.BOS_MODULE || root?.dataset.module;
  if (!root || !moduleId) return;

  loading?.remove();
  mountModule(moduleId, root).catch((err) => {
    console.error(err);
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Module failed to load</p><p class="bos-empty__text">${err instanceof Error ? err.message : "Unknown error"}</p></div>`;
  });
}

initMobileShell();

const hasSpaSurface = Boolean(
  document.getElementById("bos-module-root") ||
  document.getElementById("bos-store-hub") ||
  (document.body.dataset.module || "").trim()
);

if (hasSpaSurface) {
  initModule();
  initShell();
} else {
  // Account / help / 2FA use the BOS layout chrome without the SPA runtime.
  const sidebar = document.getElementById("bos-sidebar");
  const backdrop = document.getElementById("bos-sidebar-backdrop");
  const menuBtn = document.getElementById("bos-menu-btn");
  const closeBtn = document.getElementById("bos-sidebar-close");
  const openSidebar = () => { sidebar?.classList.add("is-open"); backdrop?.classList.remove("hidden"); };
  const closeSidebar = () => { sidebar?.classList.remove("is-open"); backdrop?.classList.add("hidden"); };
  menuBtn?.addEventListener("click", openSidebar);
  closeBtn?.addEventListener("click", closeSidebar);
  backdrop?.addEventListener("click", closeSidebar);
}
