/** Zintriq — Documents (API-backed customer files). */

import { fetchJson, esc, wsQuery } from "../services/bos-api.js";

export async function mountDocumentsPage(root) {
  root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading documents…</p></div>`;
  try {
    const docs = await fetchJson(`/api/documents${wsQuery()}`);
    if (!docs.length) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No documents yet</p><p>Files uploaded to contact profiles appear here.</p><a class="bos-btn bos-btn-primary bos-btn-sm" href="/app/contacts">View contacts</a></div>`;
      return;
    }
    root.innerHTML = `
      <div class="bos-table-wrap">
        <table class="bos-table">
          <thead><tr><th>File</th><th>Customer</th><th>Type</th><th>Uploaded</th></tr></thead>
          <tbody>${docs.map((d) => `<tr>
            <td>${d.file_path ? `<a href="/${esc(d.file_path)}" target="_blank" rel="noopener">${esc(d.filename || d.file_path)}</a>` : esc(d.filename || "—")}</td>
            <td>${esc(d.customer_name || "—")}</td>
            <td>${esc(d.file_type || "—")}</td>
            <td>${esc((d.created_at || "").slice(0, 10))}</td>
          </tr>`).join("")}</tbody>
        </table>
      </div>`;
  } catch (err) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load documents</p><p>${esc(err instanceof Error ? err.message : "Error")}</p></div>`;
  }
}
