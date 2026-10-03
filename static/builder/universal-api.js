export const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

function studioBearer() {
  return window.__ZINTRIQ_STUDIO_TOKEN__ || localStorage.getItem("zintriq_studio_token") || "";
}

export async function request(url, options = {}) {
  const method = options.method || "GET";
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const bearer = studioBearer();
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  let body = options.body;
  if (body && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({ ...body, csrf_token: csrf() });
  }
  if (method !== "GET" && !bearer) headers["X-CSRF-Token"] = csrf();
  const response = await fetch(url, { ...options, method, headers, body, credentials: "same-origin" });
  const type = response.headers.get("content-type") || "";
  const data = type.includes("json") ? await response.json() : await response.text();
  if (!response.ok) { const error = new Error(data?.error || data?.message || `Request failed (${response.status})`); error.status = response.status; error.payload = data; throw error; }
  return data;
}

export const api = {
  projects: () => request("/api/builder-core/projects"),
  createProject: (body) => request("/api/builder-core/projects", { method: "POST", body }),
  templates: () => request("/api/community/templates"),
  packages: () => request("/api/builder-core/packages"),
  marketplacePackages: (query = "") => request(`/api/marketplace/packages${query ? `?${query}` : ""}`),
  marketplacePackage: (packageId) => request(`/api/marketplace/packages/${encodeURIComponent(packageId)}`),
  creatorProfile: (body) => request("/api/marketplace/creator-profile", { method: "POST", body }),
  publishComponent: (id, definitionId, body) => request(`/api/marketplace/projects/${id}/components/${definitionId}/publish`, { method: "POST", body }),
  installPreview: (id, packageId, body = {}) => request(`/api/marketplace/projects/${id}/packages/${encodeURIComponent(packageId)}/preview-install`, { method: "POST", body }),
  marketplaceInstall: (id, packageId, body = {}) => request(`/api/marketplace/projects/${id}/packages/${encodeURIComponent(packageId)}/install`, { method: "POST", body }),
  installedPackages: (id) => request(`/api/marketplace/projects/${id}/installed`),
  updatePackage: (id, packageId, body = {}) => request(`/api/marketplace/projects/${id}/packages/${encodeURIComponent(packageId)}/update`, { method: "POST", body }),
  removePackage: (id, packageId, body) => request(`/api/marketplace/projects/${id}/packages/${encodeURIComponent(packageId)}`, { method: "DELETE", ...(body ? { body } : {}) }),
  reportPackage: (packageId, body = {}) => request(`/api/marketplace/packages/${encodeURIComponent(packageId)}/report`, { method: "POST", body }),
  savePackage: (packageId) => request(`/api/marketplace/packages/${encodeURIComponent(packageId)}/save`, { method: "POST", body: {} }),
  followCreator: (creatorId) => request(`/api/marketplace/creators/${encodeURIComponent(creatorId)}/follow`, { method: "POST", body: {} }),
  remixPackage: (packageId, body = {}) => request(`/api/marketplace/packages/${encodeURIComponent(packageId)}/remix`, { method: "POST", body }),
  forkPackage: (id, packageId, body = {}) => request(`/api/marketplace/projects/${id}/packages/${encodeURIComponent(packageId)}/fork`, { method: "POST", body }),
  bootstrap: (id, documentId) => request(`/api/builder-core/projects/${id}/bootstrap${documentId ? `?document_id=${documentId}` : ""}`),
  updateProject: (id, body) => request(`/api/builder-core/projects/${id}`, { method: "PATCH", body }),
  createSurface: (id, body) => request(`/api/builder-core/projects/${id}/surfaces`, { method: "POST", body }),
  updateSurface: (id, surfaceId, body) => request(`/api/builder-core/projects/${id}/surfaces/${surfaceId}`, { method: "PATCH", body }),
  createDocument: (id, body) => request(`/api/builder-core/projects/${id}/documents`, { method: "POST", body }),
  updateDocument: (id, documentId, body) => request(`/api/builder-core/projects/${id}/documents/${documentId}`, { method: "PATCH", body }),
  duplicateDocument: (id, documentId) => request(`/api/builder-core/projects/${id}/documents/${documentId}/duplicate`, { method: "POST", body: {} }),
  deleteDocument: (id, documentId) => request(`/api/builder-core/projects/${id}/documents/${documentId}`, { method: "DELETE" }),
  createNode: (id, body) => request(`/api/builder-core/projects/${id}/nodes`, { method: "POST", body }),
  updateNode: (id, key, body) => request(`/api/builder-core/projects/${id}/nodes/${encodeURIComponent(key)}`, { method: "PATCH", body }),
  deleteNode: (id, key) => request(`/api/builder-core/projects/${id}/nodes/${encodeURIComponent(key)}`, { method: "DELETE" }),
  duplicateNode: (id, key) => request(`/api/builder-core/projects/${id}/nodes/${encodeURIComponent(key)}/duplicate`, { method: "POST", body: {} }),
  createComponent: (id, body) => request(`/api/builder-core/projects/${id}/components/from-node`, { method: "POST", body }),
  updateComponent: (id, definitionId, body) => request(`/api/builder-core/projects/${id}/components/${definitionId}`, { method: "PATCH", body }),
  deleteComponent: (id, definitionId) => request(`/api/builder-core/projects/${id}/components/${definitionId}`, { method: "DELETE" }),
  componentUsage: (id, definitionId) => request(`/api/builder-core/projects/${id}/components/${definitionId}/usage`),
  createInstance: (id, definitionId, body) => request(`/api/builder-core/projects/${id}/components/${definitionId}/instances`, { method: "POST", body }),
  updateInstance: (id, key, body) => request(`/api/builder-core/projects/${id}/instances/${encodeURIComponent(key)}`, { method: "PATCH", body }),
  detachInstance: (id, key) => request(`/api/builder-core/projects/${id}/instances/${encodeURIComponent(key)}/detach`, { method: "POST", body: {} }),
  saveToken: (id, body) => request(`/api/builder-core/projects/${id}/design-tokens`, { method: "POST", body }),
  deleteToken: (id, key) => request(`/api/builder-core/projects/${id}/design-tokens/${encodeURIComponent(key)}`, { method: "DELETE" }),
  saveVariable: (id, body) => request(`/api/builder-core/projects/${id}/variables`, { method: "POST", body }),
  saveInteraction: (id, body) => request(`/api/builder-core/projects/${id}/interactions`, { method: "POST", body }),
  saveBinding: (id, body) => request(`/api/builder-core/projects/${id}/bindings`, { method: "POST", body }),
  deleteBinding: (id, bindingId) => request(`/api/builder-core/projects/${id}/bindings/${bindingId}`, { method: "DELETE" }),
  saveAction: (id, body) => request(`/api/builder-core/projects/${id}/actions`, { method: "POST", body }),
  deleteAction: (id, actionId) => request(`/api/builder-core/projects/${id}/actions/${actionId}`, { method: "DELETE" }),
  saveCondition: (id, body) => request(`/api/builder-core/projects/${id}/conditions`, { method: "POST", body }),
  createModel: (id, body) => request(`/api/builder-core/projects/${id}/data-models`, { method: "POST", body }),
  updateModel: (id, key, body) => request(`/api/builder-core/projects/${id}/data-models/${encodeURIComponent(key)}`, { method: "PATCH", body }),
  deleteModel: (id, key) => request(`/api/builder-core/projects/${id}/data-models/${encodeURIComponent(key)}`, { method: "DELETE" }),
  records: (id, key) => request(`/api/builder-core/projects/${id}/data-models/${encodeURIComponent(key)}/records`),
  domainData: (id, sourceId) => request(`/api/builder-core/projects/${id}/domain-data/${encodeURIComponent(sourceId)}`),
  createRecord: (id, key, body) => request(`/api/builder-core/projects/${id}/data-models/${encodeURIComponent(key)}/records`, { method: "POST", body }),
  updateRecord: (id, model, key, body) => request(`/api/builder-core/projects/${id}/data-models/${encodeURIComponent(model)}/records/${encodeURIComponent(key)}`, { method: "PATCH", body }),
  deleteRecord: (id, model, key) => request(`/api/builder-core/projects/${id}/data-models/${encodeURIComponent(model)}/records/${encodeURIComponent(key)}`, { method: "DELETE" }),
  revision: (id, note) => request(`/api/builder-core/projects/${id}/revisions`, { method: "POST", body: { note } }),
  revisions: (id) => request(`/api/builder-core/projects/${id}/revisions`),
  rollback: (id, revisionId) => request(`/api/builder-core/projects/${id}/revisions/${revisionId}/rollback`, { method: "POST", body: {} }),
  restore: (id, revisionId) => request(`/api/builder-core/projects/${id}/revisions/${revisionId}/restore`, { method: "POST", body: {} }),
  publish: (id, note) => request(`/api/builder-core/projects/${id}/publish`, { method: "POST", body: { note } }),
  install: (id, packageId) => request(`/api/marketplace/projects/${id}/packages/${encodeURIComponent(packageId)}/install`, { method: "POST", body: {} }),
};

export function toast(message, type = "info") {
  const el = document.getElementById("ub-toast");
  if (!el) return;
  const localize = (typeof globalThis.t === "function") ? globalThis.t : (s) => s;
  el.textContent = localize(String(message || ""));
  el.dataset.type = type;
  el.classList.add("is-visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("is-visible"), 2600);
}
