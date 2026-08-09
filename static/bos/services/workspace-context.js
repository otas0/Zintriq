/** Shared workspace session context for BOS modules */

import { getCsrf } from "./api.js";

let _cache = null;
/** @type {Promise<object>|null} */
let _loadPromise = null;

function applyBootstrap() {
  const boot = typeof window !== "undefined" ? window.BOS_BOOTSTRAP : null;
  if (!boot?.activeWorkspaceId || _cache) return;
  _cache = {
    active_id: boot.activeWorkspaceId,
    workspaces: [{ id: boot.activeWorkspaceId, name: boot.activeWorkspaceName || "Workspace" }],
    recent_ids: [],
  };
}

applyBootstrap();

export function getActiveWorkspaceId() {
  return _cache?.active_id ?? null;
}

export function getCachedWorkspaceList() {
  return _cache;
}

export async function loadWorkspaceList(force = false) {
  if (!force && _cache) return _cache;
  if (!force && _loadPromise) return _loadPromise;
  _loadPromise = fetch("/api/workspaces", { credentials: "same-origin" })
    .then(async (res) => {
      if (!res.ok) throw new Error("Failed to load workspaces");
      _cache = await res.json();
      return _cache;
    })
    .finally(() => {
      _loadPromise = null;
    });
  return _loadPromise;
}

export async function setActiveWorkspace(workspaceId) {
  const res = await fetch("/api/workspaces/switch", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": getCsrf(),
    },
    body: JSON.stringify({ workspace_id: workspaceId, csrf_token: getCsrf() }),
  });
  if (!res.ok) throw new Error("Switch failed");
  const ws = await res.json();
  if (_cache) {
    _cache.active_id = workspaceId;
    const idx = _cache.workspaces?.findIndex((w) => w.id === workspaceId);
    if (idx >= 0) _cache.workspaces[idx] = { ..._cache.workspaces[idx], ...ws };
  }
  return ws;
}

export async function getCurrentWorkspace() {
  const data = await loadWorkspaceList();
  const activeId = data.active_id;
  const cached = data.workspaces?.find((w) => w.id === activeId);
  if (cached) return cached;
  const res = await fetch("/api/workspaces/current", { credentials: "same-origin" });
  if (!res.ok) throw new Error("No active workspace");
  return res.json();
}

export async function workspaceFetch(path, opts = {}) {
  const wsId = getActiveWorkspaceId();
  const sep = path.includes("?") ? "&" : "?";
  const url = wsId && !path.startsWith("/api/workspaces/")
    ? `${path}${sep}workspace_id=${wsId}`
    : path;
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}
