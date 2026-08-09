/** Business OS — Organization (API-backed). */

import { showToast } from "../services/api.js";
import { fetchJson, esc } from "../services/bos-api.js";

export async function mountOrganizationsPage(root) {
  root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading…</p></div>`;
  try {
    const org = await fetchJson("/api/organizations/current");
    root.innerHTML = `
      <section class="bos-panel">
        <div class="bos-panel-head"><h2 class="bos-panel-title">Company profile</h2></div>
        <form id="org-form" class="bos-form">
          <label class="bos-field"><span>Name</span><input type="text" name="name" value="${esc(org.name)}" required></label>
          <label class="bos-field"><span>Status</span>
            <select name="status"><option value="active"${org.status === "active" ? " selected" : ""}>Active</option><option value="inactive"${org.status === "inactive" ? " selected" : ""}>Inactive</option></select>
          </label>
          <p class="bos-card__meta">${org.workspace_count ?? 0} workspace(s) · slug ${esc(org.slug)}</p>
          <button type="submit" class="bos-btn bos-btn-primary">Save changes</button>
        </form>
      </section>`;
    root.querySelector("#org-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await fetchJson(`/api/organizations/${org.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: fd.get("name"), status: fd.get("status") }),
        });
        showToast("Organization updated");
      } catch (err) {
        showToast(err instanceof Error ? err.message : "Save failed");
      }
    });
  } catch (err) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load organization</p><p>${esc(err instanceof Error ? err.message : "Error")}</p></div>`;
  }
}
