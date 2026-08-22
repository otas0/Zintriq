/** Zintriq — Contact Platform (universal relationship management). */

import { statusBadge, tag } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, renderActionBar, apiPost } from "../services/api.js";
import { fetchJson, esc, wsQuery } from "../services/bos-api.js";
import { openTaskCreateDrawer } from "../services/tasks.js";
import { selection } from "../services/selection.js";
import { setActionMode } from "../core/continuity.js";

const SECTIONS = [
  { id: "all", label: "All Contacts" },
  { id: "people", label: "People" },
  { id: "organizations", label: "Organizations" },
  { id: "recent", label: "Recently Added" },
  { id: "archived", label: "Archived" },
  { id: "settings", label: "Settings" },
];

const CONTACT_TYPES = [
  "customer", "supplier", "vendor", "partner", "contractor",
  "distributor", "organization", "other",
];

const DRAWER_TABS = [
  "overview", "timeline", "relationships", "documents", "transactions",
  "feedback", "tasks", "notes", "activity",
];

const BULK = [
  { label: "Add tags", action: "add_tags" },
  { label: "Export", action: "export" },
  { label: "Archive", action: "archive" },
  { label: "Delete", action: "delete", variant: "danger" },
];

/** @type {{ section: string, q: string, status: string, type: string, _timer?: ReturnType<typeof setTimeout> }} */
const state = { section: "all", q: "", status: "", type: "" };

function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/);
  return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

function typeBadges(types = []) {
  return types.map((t) => `<span class="bos-badge bos-badge--muted">${esc(t)}</span>`).join(" ");
}

function categoryLabel(c) {
  return c === "organization" ? "Organization" : "Person";
}

function renderSubNav() {
  return `<nav class="bos-subnav" aria-label="Contact sections">
    ${SECTIONS.map((s) =>
      `<button type="button" class="bos-subnav__item${s.id === state.section ? " is-active" : ""}" data-section="${s.id}">${s.label}</button>`
    ).join("")}
  </nav>`;
}

function contactRow(c) {
  const name = c.display_name || c.full_name || c.email || "Contact";
  return `<tr data-id="${c.id}" class="bos-row-click">
    <td><input type="checkbox" data-select-id="${c.id}" onclick="event.stopPropagation()"></td>
    <td><span class="cp-avatar">${initials(name)}</span> ${esc(name)}</td>
    <td>${esc(categoryLabel(c.category))}</td>
    <td>${typeBadges(c.types)}</td>
    <td>${esc(c.email || "—")}</td>
    <td>${esc(c.company || "—")}</td>
    <td>${statusBadge(c.status)}</td>
    <td>${(c.tags || []).map((t) => tag(t.name, t.color)).join(" ")}</td>
    <td>${(c.last_activity_at || c.created_at || "").slice(0, 10)}</td>
  </tr>`;
}

function wireTable(container, onOpen) {
  container.querySelectorAll(".bos-row-click").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("input")) return;
      onOpen(Number(row.dataset.id));
    });
  });
  container.querySelectorAll("[data-select-id]").forEach((input) => {
    input.addEventListener("change", () => {
      const id = input.getAttribute("data-select-id");
      if (input.checked) selection.add(id);
      else selection.delete(id);
      syncSelection(container);
    });
  });
  container.querySelector("#ct-select-all")?.addEventListener("change", (e) => {
    container.querySelectorAll("[data-select-id]").forEach((input) => {
      input.checked = e.target.checked;
      const id = input.getAttribute("data-select-id");
      if (e.target.checked) selection.add(id);
      else selection.delete(id);
    });
    syncSelection(container);
  });
}

function syncSelection(container) {
  setActionMode(selection.size > 0);
  container?.querySelectorAll(".bos-row-click").forEach((row) => {
    row.classList.toggle("is-selected", selection.has(row.dataset.id));
  });
  renderActionBar(selection.size, BULK, handleBulk);
}

async function handleBulk(action) {
  const ids = [...selection.selected];
  if (!ids.length) return;
  if (action === "export") {
    window.location.href = `/api/contacts/export?ids=${ids.join(",")}`;
    showToast(`Exported ${ids.length} contact(s)`);
    return;
  }
  if (action === "delete" && !window.confirm(`Delete ${ids.length} contact(s)?`)) return;
  if (action === "archive" && !window.confirm(`Archive ${ids.length} contact(s)?`)) return;
  try {
    await apiPost("/api/contacts/batch", { action, ids });
    showToast(`Updated ${ids.length} contact(s)`);
    selection.clear();
    window.dispatchEvent(new CustomEvent("contacts:refresh"));
  } catch (err) {
    showToast(err.message);
  }
}

function listParams() {
  const params = new URLSearchParams(wsQuery().replace("?", ""));
  if (state.q) params.set("q", state.q);
  if (state.status) params.set("status", state.status);
  if (state.type) params.set("type", state.type);
  if (state.section === "people") params.set("category", "person");
  else if (state.section === "organizations") params.set("category", "organization");
  else if (state.section === "recent") params.set("view", "recent");
  else if (state.section === "archived") params.set("view", "archived");
  return params;
}

async function loadContacts() {
  return fetchJson(`/api/contacts?${listParams()}`);
}

function renderContactsTable(container, contacts, onOpen) {
  if (!contacts.length) {
    container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No contacts yet</p><p>Contacts appear from feedback, imports, and manual creation.</p></div>`;
    return;
  }
  container.innerHTML = `
    <div class="bos-table-wrap">
      <table class="bos-table">
        <thead><tr>
          <th style="width:36px"><input type="checkbox" id="ct-select-all"></th>
          <th>Name</th><th>Category</th><th>Types</th><th>Email</th><th>Company</th>
          <th>Status</th><th>Tags</th><th>Last activity</th>
        </tr></thead>
        <tbody>${contacts.map(contactRow).join("")}</tbody>
      </table>
    </div>`;
  wireTable(container, onOpen);
}

function tabContent(contact, tab) {
  const insights = contact.insights || {};
  if (tab === "overview") {
    return `
      <div class="cp-profile__head">
        <span class="cp-avatar cp-avatar--lg">${initials(contact.display_name)}</span>
        <div>
          <p class="cp-profile__id">${esc(contact.contact_id)}</p>
          <p>${statusBadge(contact.status)} ${typeBadges(contact.types)}</p>
        </div>
      </div>
      <div class="bos-dash-grid cp-insights">
        <article class="bos-stat-card"><span class="bos-stat-val">${insights.feedback_count ?? 0}</span><span class="bos-stat-lbl">Feedback</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${insights.average_rating ?? "—"}</span><span class="bos-stat-lbl">Avg rating</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${(contact.tasks || []).length}</span><span class="bos-stat-lbl">Tasks</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${(contact.transactions || []).length}</span><span class="bos-stat-lbl">Transactions</span></article>
      </div>
      <dl class="cp-meta">
        <dt>Category</dt><dd>${esc(categoryLabel(contact.category))}</dd>
        <dt>Email</dt><dd>${esc(contact.email || "—")}</dd>
        <dt>Phone</dt><dd>${esc(contact.phone || "—")}</dd>
        <dt>Website</dt><dd>${esc(contact.website || "—")}</dd>
        <dt>Company</dt><dd>${esc(contact.company || "—")}</dd>
        <dt>Position</dt><dd>${esc(contact.position || "—")}</dd>
        <dt>Organization</dt><dd>${esc(contact.organization_name || "—")}</dd>
        <dt>Address</dt><dd>${esc(contact.address || "—")}</dd>
        <dt>Tags</dt><dd>${(contact.tags || []).map((t) => tag(t.name, t.color)).join(" ") || "—"}</dd>
      </dl>
      ${contact.category === "organization" && (contact.people || []).length ? `
        <h4 class="bos-drawer-section">People</h4>
        <ul>${contact.people.map((p) => `<li>${esc(p.display_name)}</li>`).join("")}</ul>` : ""}`;
  }
  if (tab === "timeline" || tab === "activity") {
    const items = contact.timeline || [];
    return `<ul class="bos-timeline">${items.map((a) =>
      `<li><strong>${esc(a.title)}</strong><br><span class="cp-muted">${esc(a.activity_type)} · ${(a.created_at || "").slice(0, 16)}</span></li>`
    ).join("") || "<li>No activity yet</li>"}</ul>`;
  }
  if (tab === "relationships") {
    const rels = contact.relationships || [];
    return `
      <ul class="bos-timeline">${rels.map((r) =>
        `<li><strong>${esc(r.relationship_type)}</strong> → ${esc(r.to_name)}</li>`
      ).join("") || "<li>No relationships yet</li>"}</ul>
      <div class="bos-field" style="margin-top:12px">
        <label class="bos-label">Add relationship (contact ID)</label>
        <input class="bos-input bos-input-sm" id="ct-rel-to" placeholder="Contact ID">
        <input class="bos-input bos-input-sm" id="ct-rel-type" placeholder="Type (e.g. manager)" style="margin-top:8px">
        <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="ct-rel-add" style="margin-top:8px">Add</button>
      </div>`;
  }
  if (tab === "documents") {
    const docs = contact.documents || [];
    return `<ul class="bos-timeline">${docs.map((d) =>
      `<li><strong>${esc(d.filename || d.file_name || "Document")}</strong> <span class="cp-muted">${(d.created_at || "").slice(0, 10)}</span></li>`
    ).join("") || "<li>No documents yet</li>"}</ul>`;
  }
  if (tab === "transactions") {
    const tx = contact.transactions || [];
    return `<div class="bos-table-wrap"><table class="bos-table"><thead><tr><th>Reference</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead>
      <tbody>${tx.map((o) =>
        `<tr><td>${esc(o.reference || o.id)}</td><td>${esc(o.amount ?? "—")}</td><td>${statusBadge(o.status)}</td><td>${(o.created_at || "").slice(0, 10)}</td></tr>`
      ).join("") || "<tr><td colspan='4'>No transactions</td></tr>"}</tbody></table></div>`;
  }
  if (tab === "feedback") {
    const fb = contact.feedback || [];
    return `<ul class="bos-timeline">${fb.map((f) =>
      `<li>${"★".repeat(f.rating || 0)} ${esc((f.comment || "").slice(0, 120))} <span class="cp-muted">${esc(f.store_name)} · ${(f.created_at || "").slice(0, 10)}</span></li>`
    ).join("") || "<li>No feedback yet</li>"}</ul>`;
  }
  if (tab === "tasks") {
    const tasks = contact.tasks || [];
    return `<ul class="bos-timeline">${tasks.map((t) =>
      `<li><strong>${esc(t.title)}</strong> — ${statusBadge(t.status)} <span class="cp-muted">${t.due_date ? t.due_date.slice(0, 10) : ""}</span></li>`
    ).join("") || "<li>No tasks yet</li>"}</ul>`;
  }
  if (tab === "notes") {
    return `
      <div id="ct-notes">${(contact.notes || []).map((n) =>
        `<div class="cp-note${n.is_pinned ? " cp-note--pinned" : ""}"><p>${esc(n.body)}</p><span class="cp-muted">${(n.created_at || "").slice(0, 16)}</span></div>`
      ).join("") || "<p class='cp-muted'>No notes</p>"}</div>
      <div class="bos-field" style="margin-top:12px">
        <textarea class="bos-input" id="ct-note-input" rows="2" placeholder="Add internal note…"></textarea>
        <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="ct-note-save" style="margin-top:8px">Add note</button>
      </div>`;
  }
  return "";
}

async function openContactDrawer(contactId, initialTab = "overview") {
  let contact = await fetchJson(`/api/contacts/${contactId}${wsQuery()}`);
  let tab = initialTab;

  const render = () => {
    const name = contact.display_name || contact.full_name || "Contact";
    openDrawer(name, `
      <div class="cp-profile">
        <div class="bos-form-actions" style="margin-bottom:12px">
          <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="ct-create-task">Create task</button>
          ${contact.status === "archived"
            ? `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="ct-restore">Restore</button>`
            : `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="ct-archive">Archive</button>`}
        </div>
        <nav class="bos-tabs bos-tabs--sm" id="ct-drawer-tabs">
          ${DRAWER_TABS.map((t) =>
            `<button type="button" class="bos-tabs__item${t === tab ? " is-active" : ""}" data-tab="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</button>`
          ).join("")}
        </nav>
        <div id="ct-tab-body" style="margin-top:12px">${tabContent(contact, tab)}</div>
      </div>`);

    window.dispatchEvent(new CustomEvent("bos:object-opened", {
      detail: { moduleId: "contacts", objectLabel: name },
    }));

    document.getElementById("ct-create-task")?.addEventListener("click", () => {
      openTaskCreateDrawer({
        title: `Follow up: ${name}`,
        related_object_type: "contact",
        related_object_id: contact.id,
        related_label: name,
      });
    });

    document.getElementById("ct-archive")?.addEventListener("click", async () => {
      await apiPost(`/api/contacts/${contact.id}/archive`, {});
      showToast("Contact archived");
      contact = await fetchJson(`/api/contacts/${contact.id}${wsQuery()}`);
      render();
    });

    document.getElementById("ct-restore")?.addEventListener("click", async () => {
      await apiPost(`/api/contacts/${contact.id}/restore`, {});
      showToast("Contact restored");
      contact = await fetchJson(`/api/contacts/${contact.id}${wsQuery()}`);
      render();
    });

    document.querySelectorAll("#ct-drawer-tabs [data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => { tab = btn.dataset.tab; render(); });
    });

    document.getElementById("ct-note-save")?.addEventListener("click", async () => {
      const body = document.getElementById("ct-note-input")?.value?.trim();
      if (!body) return;
      await apiPost(`/api/contacts/${contact.id}/notes`, { body });
      showToast("Note added");
      contact = await fetchJson(`/api/contacts/${contact.id}${wsQuery()}`);
      tab = "notes";
      render();
    });

    document.getElementById("ct-rel-add")?.addEventListener("click", async () => {
      const toId = Number(document.getElementById("ct-rel-to")?.value);
      const relType = document.getElementById("ct-rel-type")?.value?.trim() || "related";
      if (!toId) return;
      await apiPost(`/api/contacts/${contact.id}/relationships`, {
        to_contact_id: toId, relationship_type: relType,
      });
      showToast("Relationship added");
      contact = await fetchJson(`/api/contacts/${contact.id}${wsQuery()}`);
      render();
    });
  };

  render();
}

async function renderListSection(container) {
  const contacts = await loadContacts();
  container.innerHTML = `
    <div class="bos-panel-head" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
      <input type="search" class="bos-input bos-input-sm" id="ct-search" placeholder="Search name, email, company…" value="${esc(state.q)}" style="max-width:260px">
      <select class="bos-input bos-input-sm" id="ct-status-filter" style="max-width:140px">
        <option value="">All statuses</option>
        ${["active", "inactive", "archived"].map((s) =>
          `<option value="${s}"${state.status === s ? " selected" : ""}>${s}</option>`
        ).join("")}
      </select>
      <select class="bos-input bos-input-sm" id="ct-type-filter" style="max-width:160px">
        <option value="">All types</option>
        ${CONTACT_TYPES.map((t) =>
          `<option value="${t}"${state.type === t ? " selected" : ""}>${t}</option>`
        ).join("")}
      </select>
      <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="ct-new">New contact</button>
      <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="ct-import">Import CSV</button>
    </div>
    <div id="ct-table"></div>`;

  const tableEl = container.querySelector("#ct-table");
  renderContactsTable(tableEl, contacts, openContactDrawer);

  container.querySelector("#ct-search")?.addEventListener("input", (e) => {
    state.q = e.target.value;
    clearTimeout(state._timer);
    state._timer = setTimeout(() => renderListSection(container), 250);
  });
  container.querySelector("#ct-status-filter")?.addEventListener("change", (e) => {
    state.status = e.target.value;
    renderListSection(container);
  });
  container.querySelector("#ct-type-filter")?.addEventListener("change", (e) => {
    state.type = e.target.value;
    renderListSection(container);
  });
  container.querySelector("#ct-new")?.addEventListener("click", () => openCreateContact(() => renderListSection(container)));
  container.querySelector("#ct-import")?.addEventListener("click", () => openImportDialog(() => renderListSection(container)));
}

async function renderOverview(container) {
  const data = await fetchJson(`/api/contacts/summary${wsQuery()}`);
  container.innerHTML = `
    <section class="bos-dash-grid">
      <article class="bos-stat-card"><span class="bos-stat-val">${data.total}</span><span class="bos-stat-lbl">All contacts</span></article>
      <article class="bos-stat-card"><span class="bos-stat-val">${data.people}</span><span class="bos-stat-lbl">People</span></article>
      <article class="bos-stat-card"><span class="bos-stat-val">${data.organizations}</span><span class="bos-stat-lbl">Organizations</span></article>
    </section>
    <section class="bos-panel">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Recently added</h2></div>
      <div class="bos-table-wrap"><table class="bos-table"><tbody>
        ${(data.recent || []).map((c) =>
          `<tr class="bos-row-click" data-id="${c.id}"><td>${esc(c.display_name)}</td><td>${esc(categoryLabel(c.category))}</td><td>${typeBadges(c.types)}</td><td>${(c.created_at || "").slice(0, 10)}</td></tr>`
        ).join("") || "<tr><td colspan='4'>No contacts yet</td></tr>"}
      </tbody></table></div>
    </section>`;
  container.querySelectorAll(".bos-row-click[data-id]").forEach((row) => {
    row.addEventListener("click", () => openContactDrawer(Number(row.dataset.id)));
  });
}

function openCreateContact(onDone) {
  openDrawer("New contact", `
    <form id="ct-create-form" class="bos-drawer-form">
      <div class="bos-field"><label class="bos-label">Category</label>
        <select class="bos-input" name="category"><option value="person">Person</option><option value="organization">Organization</option></select>
      </div>
      <div class="bos-field"><label class="bos-label">Full name</label><input class="bos-input" name="full_name" required></div>
      <div class="bos-field"><label class="bos-label">Email</label><input class="bos-input" name="email" type="email"></div>
      <div class="bos-field"><label class="bos-label">Phone</label><input class="bos-input" name="phone"></div>
      <div class="bos-field"><label class="bos-label">Company</label><input class="bos-input" name="company"></div>
      <div class="bos-field"><label class="bos-label">Types</label>
        <select class="bos-input" name="types" multiple size="4">
          ${CONTACT_TYPES.map((t) => `<option value="${t}"${t === "customer" ? " selected" : ""}>${t}</option>`).join("")}
        </select>
      </div>
      <div class="bos-drawer-form__actions">
        <button type="submit" class="bos-btn bos-btn-primary">Create</button>
        <button type="button" class="bos-btn bos-btn-ghost" id="ct-create-cancel">Cancel</button>
      </div>
    </form>
  `);
  document.getElementById("ct-create-cancel")?.addEventListener("click", closeDrawer);
  document.getElementById("ct-create-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const types = fd.getAll("types");
    await apiPost("/api/contacts", {
      full_name: fd.get("full_name"),
      email: fd.get("email"),
      phone: fd.get("phone"),
      company: fd.get("company"),
      category: fd.get("category"),
      types,
    });
    showToast("Contact created");
    closeDrawer();
    onDone?.();
  });
}

function openImportDialog(onDone) {
  openDrawer("Import contacts", `
    <p class="cp-muted">Paste CSV: full_name, email, phone, company, category, types</p>
    <textarea class="bos-input" id="ct-import-csv" rows="8" placeholder="full_name,email,phone,category&#10;Jane Doe,jane@example.com,+123, person"></textarea>
    <button type="button" class="bos-btn bos-btn-primary" id="ct-import-run" style="margin-top:12px">Import</button>
  `);
  document.getElementById("ct-import-run")?.addEventListener("click", async () => {
    const text = document.getElementById("ct-import-csv")?.value?.trim();
    if (!text) return;
    const lines = text.split("\n").filter(Boolean);
    const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
    const rows = lines.slice(1).map((line) => {
      const vals = line.split(",");
      const row = {};
      headers.forEach((h, i) => { row[h] = (vals[i] || "").trim(); });
      return row;
    });
    const result = await apiPost("/api/contacts/import", { rows });
    showToast(`Imported ${result.created}, skipped ${result.skipped} duplicates`);
    closeDrawer();
    onDone?.();
  });
}

async function renderSettings(container) {
  const dupes = await fetchJson(`/api/contacts/duplicates${wsQuery()}`);
  container.innerHTML = `
    <section class="bos-panel">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Possible duplicates</h2></div>
      <p class="cp-muted">Review and merge duplicates manually — never merged automatically.</p>
      <div class="bos-table-wrap"><table class="bos-table">
        <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Company</th><th></th></tr></thead>
        <tbody>${dupes.map((c) =>
          `<tr><td>${esc(c.display_name)}</td><td>${esc(c.email || "—")}</td><td>${esc(c.phone || "—")}</td><td>${esc(c.company || "—")}</td>
          <td><button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-open="${c.id}">View</button></td></tr>`
        ).join("") || "<tr><td colspan='5'>No duplicates detected</td></tr>"}
      </tbody></table></div>
    </section>
    <section class="bos-panel" style="margin-top:16px">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Merge contacts</h2></div>
      <p class="cp-muted">Primary contact keeps all data; secondary is removed.</p>
      <div class="bos-field"><label class="bos-label">Primary contact ID</label><input class="bos-input" id="ct-merge-primary"></div>
      <div class="bos-field"><label class="bos-label">Secondary contact ID (will be merged in)</label><input class="bos-input" id="ct-merge-secondary"></div>
      <button type="button" class="bos-btn bos-btn-primary" id="ct-merge-run">Merge</button>
    </section>
    <section class="bos-panel" style="margin-top:16px">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Export</h2></div>
      <button type="button" class="bos-btn bos-btn-ghost" id="ct-export-all">Export all contacts (CSV)</button>
    </section>`;

  container.querySelectorAll("[data-open]").forEach((btn) => {
    btn.addEventListener("click", () => openContactDrawer(Number(btn.dataset.open)));
  });
  container.querySelector("#ct-merge-run")?.addEventListener("click", async () => {
    const primary_id = Number(document.getElementById("ct-merge-primary")?.value);
    const secondary_id = Number(document.getElementById("ct-merge-secondary")?.value);
    if (!primary_id || !secondary_id) return;
    if (!window.confirm(`Merge contact #${secondary_id} into #${primary_id}?`)) return;
    await apiPost("/api/contacts/merge", { primary_id, secondary_id });
    showToast("Contacts merged");
    window.dispatchEvent(new CustomEvent("contacts:refresh"));
  });
  container.querySelector("#ct-export-all")?.addEventListener("click", () => {
    window.location.href = `/api/contacts/export${wsQuery()}`;
  });
}

/** @param {HTMLElement} root */
export async function mountContactsPage(root) {
  selection.clear();
  setActionMode(false);

  root.innerHTML = `<div id="ct-subnav"></div><div id="ct-content"><div class="bos-loading">Loading contacts…</div></div>`;
  const subnav = root.querySelector("#ct-subnav");
  const content = root.querySelector("#ct-content");

  const render = async () => {
    subnav.innerHTML = renderSubNav();
    subnav.querySelectorAll("[data-section]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.section = btn.dataset.section;
        render();
      });
    });
    content.innerHTML = `<div class="bos-loading">Loading…</div>`;
    try {
      if (state.section === "all") {
        const data = await fetchJson(`/api/contacts/summary${wsQuery()}`);
        content.innerHTML = `
          <section class="bos-dash-grid" style="margin-bottom:16px">
            <article class="bos-stat-card"><span class="bos-stat-val">${data.total}</span><span class="bos-stat-lbl">All contacts</span></article>
            <article class="bos-stat-card"><span class="bos-stat-val">${data.people}</span><span class="bos-stat-lbl">People</span></article>
            <article class="bos-stat-card"><span class="bos-stat-val">${data.organizations}</span><span class="bos-stat-lbl">Organizations</span></article>
          </section>
          <div id="ct-list-wrap"></div>`;
        await renderListSection(content.querySelector("#ct-list-wrap"));
      } else if (state.section === "settings") await renderSettings(content);
      else await renderListSection(content);
    } catch (err) {
      content.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load</p><p>${esc(err.message)}</p></div>`;
    }
  };

  const hash = window.location.hash.match(/^#contact\/(\d+)/);
  if (hash) openContactDrawer(Number(hash[1]));

  window.addEventListener("contacts:refresh", render);
  await render();
}

/** Legacy alias */
export const mountCustomersPage = mountContactsPage;
