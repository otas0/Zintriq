/** Business OS — Tags (API-backed customer tags). */

import { showToast } from "../services/api.js";
import { fetchJson, esc } from "../services/bos-api.js";

async function loadTags() {
  return fetchJson("/api/tags");
}

export async function mountTagsPage(root) {
  const render = async () => {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading…</p></div>`;
    try {
      const tags = await loadTags();
      root.innerHTML = `
        <form id="tag-create" class="bos-form bos-form--inline" style="margin-bottom:16px">
          <input name="name" placeholder="New tag name" required>
          <input name="color" type="color" value="#6366f1">
          <button type="submit" class="bos-btn bos-btn-primary bos-btn-sm">Add tag</button>
        </form>
        ${tags.length ? `<div class="bos-table-wrap"><table class="bos-table"><thead><tr><th>Tag</th><th>Usage</th><th></th></tr></thead>
          <tbody>${tags.map((t) => `<tr><td><span class="bos-tag" style="background:${esc(t.color)}20;color:${esc(t.color)}">${esc(t.name)}</span></td>
            <td>${t.usage_count ?? 0}</td><td><button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-del="${t.id}">Delete</button></td></tr>`).join("")}</tbody></table></div>`
          : `<div class="bos-empty"><p class="bos-empty__title">No tags yet</p></div>`}`;
      root.querySelector("#tag-create")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          await fetchJson("/api/tags", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: fd.get("name"), color: fd.get("color") }) });
          showToast("Tag created");
          render();
        } catch (err) {
          showToast(err instanceof Error ? err.message : "Failed");
        }
      });
      root.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-del");
          if (!id || !confirm("Delete this tag?")) return;
          try {
            await fetchJson(`/api/tags/${id}`, { method: "DELETE" });
            showToast("Tag deleted");
            render();
          } catch (err) {
            showToast(err instanceof Error ? err.message : "Delete failed");
          }
        });
      });
    } catch (err) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load tags</p></div>`;
    }
  };
  await render();
}
