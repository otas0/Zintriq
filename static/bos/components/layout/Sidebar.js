/** Sidebar — MVP navigation items (server shell renders HTML; this is the source of truth). */

import { visibleNav } from "../../product-focus.js";

/** @returns {readonly { id: string, label: string, icon: string, path: string }[]} */
export function sidebarNavItems() {
  return visibleNav();
}

export function isNavActive(moduleId, itemId) {
  if (itemId === "responses") {
    return ["responses", "customers", "interactions", "feedback"].includes(moduleId);
  }
  if (itemId === "settings") {
    return ["settings", "workspaces"].includes(moduleId);
  }
  return moduleId === itemId;
}
