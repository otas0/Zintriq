/** Global search — workspace-scoped API only. */

import { getActiveWorkspaceId } from "../services/workspace-context.js";

/**
 * @param {string} q
 * @returns {Promise<Array<{ type: string, id: number|string, label: string, href: string }>>}
 */
export async function searchWorkspaceApi(q) {
  const wsId = getActiveWorkspaceId();
  if (!wsId || q.trim().length < 2) return [];
  try {
    const res = await fetch(
      `/api/workspaces/${wsId}/search?q=${encodeURIComponent(q.trim())}`,
      { credentials: "same-origin" },
    );
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

/**
 * @param {string} q
 * @returns {Promise<{ api: object[], local: object[] }>}
 */
export async function globalSearchGrouped(q) {
  const trimmed = q.trim();
  if (!trimmed) return { api: [], local: [] };
  const api = await searchWorkspaceApi(trimmed);
  return { api, local: [] };
}
