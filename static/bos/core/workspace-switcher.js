/** Workspace switcher — sidebar top, soft switch without full reload */

import { showToast, apiPost } from "../services/api.js";
import { getActiveWorkspaceId, setActiveWorkspace, loadWorkspaceList } from "../services/workspace-context.js";

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

function updateWorkspaceLabels(name) {
  document.querySelectorAll(".ws-switcher__label").forEach((el) => {
    el.textContent = name;
  });
}

function renderSwitcherPanel(workspaces, activeId, recentIds) {
  const favs = workspaces.filter((w) => w.is_favorite);
  const recent = recentIds.map((id) => workspaces.find((w) => w.id === id)).filter(Boolean);
  const row = (w) => `
    <button type="button" class="ws-switcher__item${w.id === activeId ? " is-active" : ""}" data-ws-id="${w.id}">
      <span class="ws-switcher__name">${esc(w.name)}</span>
      <span class="ws-switcher__meta">${w.experience_count || 0} experiences · ${esc(w.role || "")}</span>
      ${w.is_favorite ? '<span class="ws-switcher__star">★</span>' : ""}
    </button>`;

  return `
    <div class="ws-switcher__panel material-panel">
      <input type="search" class="bos-input bos-input-sm ws-switcher__search" placeholder="Search workspaces…" id="ws-switcher-search">
      ${favs.length ? `<p class="ws-switcher__section">Favorites</p><div class="ws-switcher__list">${favs.map(row).join("")}</div>` : ""}
      ${recent.length ? `<p class="ws-switcher__section">Recent</p><div class="ws-switcher__list">${recent.map(row).join("")}</div>` : ""}
      <p class="ws-switcher__section">All workspaces</p>
      <div class="ws-switcher__list" id="ws-switcher-all">${workspaces.map(row).join("")}</div>
      <div class="ws-switcher__footer">
        <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="ws-switcher-create">Create workspace</button>
        <a class="bos-btn bos-btn-ghost bos-btn-sm" href="/app/workspaces">Manage</a>
      </div>
    </div>`;
}

export async function initWorkspaceSwitcher() {
  const mount = document.getElementById("bos-topbar-workspace-switcher")
    || document.getElementById("bos-workspace-switcher");
  if (!mount) return;

  let data = await loadWorkspaceList();
  const activeId = getActiveWorkspaceId() || data.active_id;
  const active = data.workspaces.find((w) => w.id === activeId) || data.workspaces[0];
  updateWorkspaceLabels(active?.name || "Workspace");

  mount.innerHTML = `
    <button type="button" class="ws-switcher__trigger" id="ws-switcher-trigger" aria-haspopup="true">
      <span class="ws-switcher__label">${esc(active?.name || "Workspace")}</span>
      <span class="ws-switcher__chev">▾</span>
    </button>
    <div class="ws-switcher__dropdown hidden" id="ws-switcher-dropdown"></div>`;

  const dropdown = document.getElementById("ws-switcher-dropdown");

  const bindPanelEvents = () => {
    dropdown.querySelectorAll("[data-ws-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.wsId);
        const ws = data.workspaces.find((w) => w.id === id);
        await setActiveWorkspace(id);
        updateWorkspaceLabels(ws?.name || "Workspace");
        showToast("Workspace switched");
        dropdown.classList.add("hidden");
        window.dispatchEvent(new CustomEvent("bos:workspace-changed", { detail: { workspaceId: id } }));
      });
    });
    dropdown.querySelector("#ws-switcher-search")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      dropdown.querySelectorAll("#ws-switcher-all [data-ws-id]").forEach((el) => {
        const name = el.querySelector(".ws-switcher__name")?.textContent?.toLowerCase() || "";
        el.classList.toggle("hidden", q && !name.includes(q));
      });
    });
    dropdown.querySelector("#ws-switcher-create")?.addEventListener("click", async () => {
      const name = window.prompt("Workspace name");
      if (!name?.trim()) return;
      try {
        const ws = await apiPost("/api/workspaces", { name: name.trim() });
        await setActiveWorkspace(ws.id);
        data = await loadWorkspaceList();
        updateWorkspaceLabels(ws.name);
        dropdown.classList.add("hidden");
        window.dispatchEvent(new CustomEvent("bos:workspace-changed", { detail: { workspaceId: ws.id } }));
        showToast("Workspace created");
      } catch {
        showToast("Could not create workspace");
      }
    });
  };

  const refreshPanel = () => {
    dropdown.innerHTML = renderSwitcherPanel(data.workspaces, getActiveWorkspaceId() || data.active_id, data.recent_ids || []);
    bindPanelEvents();
  };

  document.getElementById("ws-switcher-trigger")?.addEventListener("click", () => {
    refreshPanel();
    dropdown.classList.toggle("hidden");
  });

  document.addEventListener("click", (e) => {
    if (!mount.contains(e.target)) dropdown?.classList.add("hidden");
  });
}
