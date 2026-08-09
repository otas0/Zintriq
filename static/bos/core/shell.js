/** Application Shell — persistent OS layer orchestration. */

import { loadWorkspaceList } from "../services/workspace-context.js";
import { openCreatePicker } from "./create-picker.js";
import { showToast } from "../services/api.js";

let _workspaceName = "Workspace";

export function getShellWorkspaceName() {
  return _workspaceName;
}

export async function refreshShellContext() {
  try {
    const data = await loadWorkspaceList();
    const activeId = data.active_id;
    const ws = data.workspaces?.find((w) => w.id === activeId) || data.workspaces?.[0];
    _workspaceName = ws?.name || "Workspace";
    const el = document.getElementById("bos-topbar-workspace");
    if (el) el.textContent = _workspaceName;
  } catch { /* ignore */ }
}

export function remountCurrentModule() {
  window.dispatchEvent(new CustomEvent("bos:remount-module"));
}

export function initShellKeyboard() {
  document.addEventListener("keydown", (e) => {
    if (!(e.metaKey || e.ctrlKey)) return;
    const key = e.key.toLowerCase();
    if (key === "n") {
      e.preventDefault();
      openCreatePicker();
    }
    if (key === "s") {
      const saveBtn = document.querySelector("[data-shell-save], .bos-drawer-form [type=submit], #fb-reply-save");
      if (saveBtn && !document.getElementById("bos-drawer")?.classList.contains("hidden")) {
        e.preventDefault();
        saveBtn.click();
      }
    }
  });

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "/") {
      e.preventDefault();
      showToast("⌘K search · ⌘N create · Esc close · / focus search");
    }
  });
}

export function initShellEvents() {
  window.addEventListener("bos:workspace-changed", async () => {
    await refreshShellContext();
    remountCurrentModule();
  });

  window.addEventListener("bos:object-opened", () => {
    /* Breadcrumbs removed */
  });
}

export async function initShellContext() {
  await loadWorkspaceList().catch(() => {});
  await refreshShellContext();
}
