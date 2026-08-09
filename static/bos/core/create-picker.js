/** Unified Create picker — consistent creation flow across modules. */

import { CREATE_PICKER_ITEMS } from "./shell-nav.js";
import { dispatchCreate } from "../platform/commands.js";
import { openDrawer, closeDrawer, showToast, apiPost } from "../services/api.js";
import { escapeHtml } from "../services/search.js";
import { setActiveWorkspace } from "../services/workspace-context.js";

export function openCreatePicker() {
  openDrawer("Create", `
    <p class="bos-empty__text" style="margin-bottom:12px">Choose what to create</p>
    <div class="bos-create-picker">
      ${CREATE_PICKER_ITEMS.map((item) =>
        `<button type="button" class="bos-create-picker__item" data-create-action="${item.action}"
          ${item.collection ? `data-collection="${item.collection}"` : ""}
          ${item.path ? `data-path="${item.path}"` : ""}
          ${item.href ? `data-href="${item.href}"` : ""}>
          ${escapeHtml(item.label)}
        </button>`
      ).join("")}
    </div>
  `);

  document.getElementById("bos-drawer-body")?.querySelectorAll(".bos-create-picker__item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.getAttribute("data-create-action");
      closeDrawer();
      if (action === "create") {
        dispatchCreate(btn.getAttribute("data-collection"));
        return;
      }
      if (action === "nav") {
        window.location.href = btn.getAttribute("data-href") || btn.getAttribute("data-path") || "/app/store";
        return;
      }
      if (action === "workspace-create") {
        const name = window.prompt("Workspace name");
        if (!name?.trim()) return;
        try {
          const ws = await apiPost("/api/workspaces", { name: name.trim() });
          await setActiveWorkspace(ws.id);
          window.dispatchEvent(new CustomEvent("bos:workspace-changed", { detail: { workspaceId: ws.id } }));
          showToast("Workspace created");
        } catch {
          showToast("Could not create workspace");
        }
      }
    });
  });
}
