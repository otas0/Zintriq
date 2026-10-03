/** Network boundary for the visual builder. */

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `Request failed (${response.status})`);
  }
  return response.json();
}

export function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  return { "Content-Type": "application/json", "X-CSRF-Token": token };
}

export function saveDraftRevision(experienceId, note = "Saved from Builder") {
  return fetchJson(`/api/qr-experiences/${experienceId}/revisions`, {
    method: "POST",
    headers: csrfHeaders(),
    body: JSON.stringify({ note }),
  });
}

export function listRevisions(experienceId) {
  return fetchJson(`/api/qr-experiences/${experienceId}/revisions`);
}

export function rollbackRevision(experienceId, revisionId) {
  return fetchJson(`/api/qr-experiences/${experienceId}/revisions/${revisionId}/rollback`, {
    method: "POST",
    headers: csrfHeaders(),
    body: "{}",
  });
}
