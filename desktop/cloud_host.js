/**
 * Talk to the public Flask account origin. Never send this token to 127.0.0.1.
 */

async function cloudFetch(origin, token, method, path, body) {
  const base = String(origin || "").replace(/\/$/, "");
  if (!base || !token) return { ok: false, status: 0, data: { error: "not signed in" } };
  const res = await fetch(`${base}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body == null ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

async function pushDraft(origin, token, draft) {
  const slug = encodeURIComponent(String((draft && draft.slug) || ""));
  if (!slug) return { ok: false, status: 400, data: { error: "missing slug" } };
  const body = {
    code: draft.code,
    events: draft.events || "",
    title: draft.title || draft.slug,
    updated_at: draft.updated_at,
  };
  if (draft.base_revision != null && draft.base_revision !== "") {
    body.base_revision = Number(draft.base_revision);
  }
  return cloudFetch(origin, token, "PUT", `/api/desktop/cloud/drafts/${slug}`, body);
}

async function deleteDraft(origin, token, slug) {
  const key = encodeURIComponent(String(slug || ""));
  if (!key) return { ok: false, status: 400, data: { error: "missing slug" } };
  return cloudFetch(origin, token, "DELETE", `/api/desktop/cloud/drafts/${key}`);
}

async function putShareAsset(origin, token, publicId, name, bytes, contentType) {
  const base = String(origin || "").replace(/\/$/, "");
  const id = encodeURIComponent(String(publicId || ""));
  const file = encodeURIComponent(String(name || ""));
  if (!base || !token || !id || !file) return { ok: false, status: 0, data: { error: "bad request" } };
  const res = await fetch(`${base}/api/desktop/cloud/shares/${id}/assets/${file}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": contentType || "application/octet-stream",
    },
    body: bytes,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

async function listDrafts(origin, token) {
  return cloudFetch(origin, token, "GET", "/api/desktop/cloud/drafts");
}

async function getDraft(origin, token, slug) {
  const key = encodeURIComponent(String(slug || ""));
  if (!key) return { ok: false, status: 400, data: { error: "missing slug" } };
  return cloudFetch(origin, token, "GET", `/api/desktop/cloud/drafts/${key}`);
}

async function getCollab(origin, token, slug) {
  return cloudFetch(origin, token, "GET", `/api/desktop/cloud/collab/${encodeURIComponent(slug)}`);
}

async function pushCollab(origin, token, slug, payload) {
  return cloudFetch(origin, token, "PUT", `/api/desktop/cloud/collab/${encodeURIComponent(slug)}`, payload || {});
}

async function publishDraft(origin, token, slug, title) {
  return cloudFetch(origin, token, "POST", "/api/desktop/cloud/publish", { slug, title });
}

async function publishPlugin(origin, token, pack) {
  return cloudFetch(origin, token, "POST", "/api/desktop/cloud/publish-plugin", { pack: pack || {} });
}

async function unpublishShare(origin, token, id) {
  return cloudFetch(origin, token, "POST", "/api/desktop/cloud/unpublish", { id });
}

async function getShare(origin, id) {
  const base = String(origin || "").replace(/\/$/, "");
  const res = await fetch(`${base}/api/desktop/cloud/shares/${encodeURIComponent(id)}`, {
    headers: { Accept: "application/json" },
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

async function listCatalog(origin, query) {
  const base = String(origin || "").replace(/\/$/, "");
  if (!base) return { ok: false, status: 0, data: { packages: [] } };
  const params = new URLSearchParams();
  if (query && query.q) params.set("q", query.q);
  if (query && query.type) params.set("type", query.type);
  const suffix = params.toString() ? `?${params}` : "";
  const res = await fetch(`${base}/api/desktop/cloud/catalog${suffix}`, {
    headers: { Accept: "application/json" },
  });
  const data = await res.json().catch(() => ({ packages: [] }));
  return { ok: res.ok, status: res.status, data };
}

async function listMine(origin, token) {
  return cloudFetch(origin, token, "GET", "/api/desktop/cloud/mine");
}

async function getUpdates(origin) {
  const base = String(origin || "").replace(/\/$/, "");
  if (!base) return { ok: false, status: 0, data: {} };
  const res = await fetch(`${base}/api/desktop/updates`, { headers: { Accept: "application/json" } });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

async function entitlement(origin, token) {
  return cloudFetch(origin, token, "GET", "/api/desktop/cloud/entitlement");
}

async function verifySession(origin, token) {
  const base = String(origin || "").replace(/\/$/, "");
  if (!base || !token) return { ok: false, status: 0, data: { error: "not signed in" } };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4000);
  try {
    const res = await fetch(`${base}/api/desktop/session`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  } catch {
    return { ok: false, status: 0, data: { error: "offline" } };
  } finally {
    clearTimeout(timer);
  }
}

module.exports = {
  cloudFetch,
  pushDraft,
  deleteDraft,
  putShareAsset,
  listDrafts,
  getDraft,
  getCollab,
  pushCollab,
  publishDraft,
  publishPlugin,
  unpublishShare,
  getShare,
  listCatalog,
  listMine,
  getUpdates,
  entitlement,
  verifySession,
};
