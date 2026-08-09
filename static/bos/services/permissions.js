/** Permission helpers — permission-driven UI, never role names in business logic. */

/** @type {Set<string>} */
let _permissions = new Set();
/** @type {string|null} */
let _role = null;
/** @type {number|null} */
let _workspaceId = null;

export function setTeamContext(ctx) {
  _permissions = new Set(ctx?.permissions || []);
  _role = ctx?.role || null;
  _workspaceId = ctx?.workspace_id ?? null;
}

export function hasPermission(key) {
  return _permissions.has(key);
}

export function getTeamRole() {
  return _role;
}

export function getTeamWorkspaceId() {
  return _workspaceId;
}

export async function loadTeamContext(workspaceId) {
  const q = workspaceId ? `?workspace_id=${workspaceId}` : "";
  const res = await fetch(`/api/team/context${q}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error("Could not load team context");
  const ctx = await res.json();
  setTeamContext(ctx);
  return ctx;
}
