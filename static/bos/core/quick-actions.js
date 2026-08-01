import { MODULE_REGISTRY } from "../features/registry.js";
import { dispatchCreate } from "../platform/commands.js";
import { selection } from "../services/selection.js";

const QUICK_BY_MODULE = {
  home: [
    { label: "Go to Catalog", action: "nav", path: "/app/catalog" },
    { label: "Go to Customers", action: "nav", path: "/app/customers" },
    { label: "Command palette", action: "palette" },
  ],
};

function moduleActions(moduleId) {
  const config = MODULE_REGISTRY[moduleId];
  if (!config) return QUICK_BY_MODULE.home || [];
  return [
    { label: config.createLabel || "Create", action: "create", collection: config.collection },
    { label: "Select all", action: "select-all" },
    { label: "Clear selection", action: "clear-selection" },
    { label: "Command palette ⌘K", action: "palette" },
  ];
}

export function initQuickActions() {
  const fab = document.getElementById("bos-quick-fab");
  const menu = document.getElementById("bos-quick-menu");
  if (!fab || !menu) return;

  const renderMenu = () => {
    const moduleId = document.body.dataset.module || "home";
    const hasSelection = selection.size > 0;
    const actions = hasSelection
      ? [
          { label: `Batch actions (${selection.size})`, action: "focus-action-bar" },
          { label: "Clear selection", action: "clear-selection" },
          { label: "Archive selected", action: "batch-archive" },
          { label: "Export selected", action: "batch-export" },
        ]
      : moduleActions(moduleId);

    menu.innerHTML = actions.map((a) => `<button type="button" class="bos-quick-menu__item" data-quick="${a.action}"${a.collection ? ` data-collection="${a.collection}"` : ""}${a.path ? ` data-path="${a.path}"` : ""}>${a.label}</button>`).join("");
  };

  fab.addEventListener("click", () => {
    renderMenu();
    menu.classList.toggle("hidden");
  });

  menu.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-quick]");
    if (!btn) return;
    const action = btn.getAttribute("data-quick");
    if (action === "create") dispatchCreate(btn.getAttribute("data-collection"));
    if (action === "nav") window.location.href = btn.getAttribute("data-path") || "/app";
    if (action === "palette") document.getElementById("bos-command-input")?.focus() || document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
    if (action === "select-all") window.dispatchEvent(new CustomEvent("bos:select-all"));
    if (action === "clear-selection") { selection.clear(); menu.classList.add("hidden"); return; }
    if (action === "focus-action-bar") document.getElementById("bos-action-bar")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (action === "batch-archive") window.dispatchEvent(new CustomEvent("bos:batch-action", { detail: { action: "archive" } }));
    if (action === "batch-export") window.dispatchEvent(new CustomEvent("bos:batch-action", { detail: { action: "export" } }));
    menu.classList.add("hidden");
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("#bos-quick-fab") || e.target.closest("#bos-quick-menu")) return;
    menu.classList.add("hidden");
  });

  selection.subscribe(() => {
    fab.classList.toggle("bos-quick-fab--active", selection.size > 0);
    fab.setAttribute("aria-label", selection.size > 0 ? `${selection.size} selected — quick actions` : "Quick actions");
  });
}
