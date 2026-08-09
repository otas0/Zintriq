/** Business OS — Customer Platform (API-backed identity layer). */

import { statusBadge, tag } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, renderActionBar, apiPost } from "../services/api.js";
import { openTaskCreateDrawer } from "../services/tasks.js";
import { selection } from "../services/selection.js";
import { setActionMode } from "../core/continuity.js";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "customers", label: "Customers" },
  { id: "groups", label: "Groups" },
  { id: "tags", label: "Tags" },
  { id: "activity", label: "Activity" },
  { id: "settings", label: "Settings" },
];

const BULK = [
  { label: "Add tags", action: "add_tags" },
  { label: "Add to group", action: "add_groups" },
  { label: "Export", action: "export" },
  { label: "Archive", action: "archive" },
  { label: "Delete", action: "delete", variant: "danger" },
];

async function fetchJson(url, opts) {
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed (${res.status})`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/);
  return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

function renderSubNav(active) {
  return `<nav class="bos-subnav" aria-label="Customer sections">
    ${SECTIONS.map((s) => `<button type="button" class="bos-subnav__item${s.id === active ? " is-active" : ""}" data-section="${s.id}">${s.label}</button>`).join("")}
  </nav>`;
}

function statCards(data) {
  return `<section class="bos-dash-grid">
    <article class="bos-stat-card"><span class="bos-stat-val">${data.total}</span><span class="bos-stat-lbl">Total customers</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${data.active}</span><span class="bos-stat-lbl">Active</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${data.new_this_month}</span><span class="bos-stat-lbl">New this month</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${data.pending_followup}</span><span class="bos-stat-lbl">Needs follow-up</span></article>
  </section>`;
}

function customerRow(c) {
  const name = c.display_name || c.full_name || c.email || "Customer";
  return `<tr data-id="${c.id}" class="bos-row-click">
    <td><input type="checkbox" data-select-id="${c.id}" onclick="event.stopPropagation()"></td>
    <td><span class="cp-avatar">${initials(name)}</span> ${esc(name)}</td>
    <td>${esc(c.email || "—")}</td>
    <td>${esc(c.phone || "—")}</td>
    <td>${statusBadge(c.status)}</td>
    <td>${(c.tags || []).map((t) => tag(t.name, t.color)).join(" ")}</td>
    <td>${(c.last_activity_at || c.created_at || "").slice(0, 10)}</td>
  </tr>`;
}

function renderCustomersTable(container, customers, onOpen) {
  if (!customers.length) {
    container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No customers yet</p><p>Customers appear automatically from feedback, events, check-ins, and imports.</p></div>`;
    return;
  }
  container.innerHTML = `
    <div class="bos-table-wrap">
      <table class="bos-table">
        <thead><tr>
          <th style="width:36px"><input type="checkbox" id="cp-select-all"></th>
          <th>Name</th><th>Email</th><th>Phone</th><th>Status</th><th>Tags</th><th>Last activity</th>
        </tr></thead>
        <tbody>${customers.map(customerRow).join("")}</tbody>
      </table>
    </div>`;

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
  container.querySelector("#cp-select-all")?.addEventListener("change", (e) => {
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
    window.location.href = `/api/customers/export?ids=${ids.join(",")}`;
    showToast(`Exported ${ids.length} customer(s)`);
    return;
  }
  if (action === "delete" && !window.confirm(`Delete ${ids.length} customer(s)?`)) return;
  if (action === "archive" && !window.confirm(`Archive ${ids.length} customer(s)?`)) return;
  try {
    await apiPost("/api/customers/batch", { action, ids });
    showToast(`Updated ${ids.length} customer(s)`);
    selection.clear();
    window.dispatchEvent(new CustomEvent("cp:refresh"));
  } catch (err) {
    showToast(err.message);
  }
}

function renderProfileDrawer(customer) {
  const name = customer.display_name || customer.full_name;
  const insights = customer.insights || {};
  openDrawer(name, `
    <div class="cp-profile">
      <div class="cp-profile__head">
        <span class="cp-avatar cp-avatar--lg">${initials(name)}</span>
        <div>
          <p class="cp-profile__id">${esc(customer.customer_code)}</p>
          <p>${statusBadge(customer.status)}</p>
        </div>
      </div>
      <div class="bos-form-actions" style="margin-bottom:12px">
        <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="cp-create-task">Create task</button>
      </div>
      <div class="bos-dash-grid cp-insights">
        <article class="bos-stat-card"><span class="bos-stat-val">${insights.total_visits ?? 0}</span><span class="bos-stat-lbl">Visits</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${insights.feedback_submitted ?? 0}</span><span class="bos-stat-lbl">Feedback</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${insights.average_rating ?? "—"}</span><span class="bos-stat-lbl">Avg rating</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${insights.events_attended ?? 0}</span><span class="bos-stat-lbl">Events</span></article>
      </div>
      <dl class="cp-meta">
        <dt>Email</dt><dd>${esc(customer.email || "—")}</dd>
        <dt>Phone</dt><dd>${esc(customer.phone || "—")}</dd>
        <dt>Company</dt><dd>${esc(customer.company || "—")}</dd>
        <dt>Tags</dt><dd>${(customer.tags || []).map((t) => tag(t.name, t.color)).join(" ") || "—"}</dd>
        <dt>Groups</dt><dd>${(customer.groups || []).map((g) => esc(g.name)).join(", ") || "—"}</dd>
        <dt>Stores</dt><dd>${(customer.stores || []).map((s) => esc(s.name)).join(", ") || "—"}</dd>
      </dl>
      <h4 class="bos-drawer-section">Timeline</h4>
      <ul class="bos-timeline">
        ${(customer.timeline || []).slice(0, 15).map((a) =>
          `<li><strong>${esc(a.title)}</strong><br><span class="cp-muted">${esc(a.activity_type)} · ${(a.created_at || "").slice(0, 16)}</span></li>`
        ).join("") || "<li>No activity yet</li>"}
      </ul>
      <h4 class="bos-drawer-section">Notes</h4>
      <div id="cp-notes">${(customer.notes || []).map((n) =>
        `<div class="cp-note${n.is_pinned ? " cp-note--pinned" : ""}"><p>${esc(n.body)}</p><span class="cp-muted">${(n.created_at || "").slice(0, 16)}</span></div>`
      ).join("") || "<p class='cp-muted'>No notes</p>"}</div>
      <div class="bos-field" style="margin-top:12px">
        <textarea class="bos-input" id="cp-note-input" rows="2" placeholder="Add internal note…"></textarea>
        <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="cp-note-save" style="margin-top:8px">Add note</button>
      </div>
      ${(customer.feedback || []).length ? `<h4 class="bos-drawer-section">Feedback</h4><ul class="bos-timeline">${customer.feedback.map((f) =>
        `<li>${"★".repeat(f.rating || 0)} ${esc((f.comment || "").slice(0, 80))} <span class="cp-muted">${esc(f.store_name)}</span></li>`
      ).join("")}</ul>` : ""}
    </div>
  `);

  window.dispatchEvent(new CustomEvent("bos:object-opened", {
    detail: { moduleId: "customers", objectLabel: name || "Customer" },
  }));

  document.getElementById("cp-create-task")?.addEventListener("click", () => {
    openTaskCreateDrawer({
      title: `Follow up: ${name}`,
      related_object_type: "customer",
      related_object_id: customer.id,
      related_label: name,
    });
  });

  document.getElementById("cp-note-save")?.addEventListener("click", async () => {
    const body = document.getElementById("cp-note-input")?.value?.trim();
    if (!body) return;
    await apiPost(`/api/customers/${customer.id}/notes`, { body });
    showToast("Note added");
    const updated = await fetchJson(`/api/customers/${customer.id}`);
    renderProfileDrawer(updated);
  });
}

async function renderOverview(container) {
  const data = await fetchJson("/api/customers/summary");
  container.innerHTML = `
    ${statCards(data)}
    <section class="bos-panel">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Recent customers</h2></div>
      <div class="bos-table-wrap"><table class="bos-table"><tbody>
        ${(data.recent || []).map((c) => `<tr class="bos-row-click" data-id="${c.id}"><td>${esc(c.display_name)}</td><td>${esc(c.email || "—")}</td><td>${statusBadge(c.status)}</td><td>${(c.created_at || "").slice(0, 10)}</td></tr>`).join("") || "<tr><td colspan='4'>No customers yet</td></tr>"}
      </tbody></table></div>
    </section>
    <section class="bos-panel">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Recent activity</h2></div>
      <ul class="bos-timeline">
        ${(data.recent_activity || []).map((a) =>
          `<li><strong>${esc(a.full_name || a.customer_code)}</strong> — ${esc(a.title)} <span class="cp-muted">${(a.created_at || "").slice(0, 16)}</span></li>`
        ).join("") || "<li>No activity yet</li>"}
      </ul>
    </section>`;
  container.querySelectorAll(".bos-row-click[data-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      const c = await fetchJson(`/api/customers/${row.dataset.id}`);
      renderProfileDrawer(c);
    });
  });
}

async function renderCustomersList(container, state) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.status) params.set("status", state.status);
  const customers = await fetchJson(`/api/customers?${params}`);
  container.innerHTML = `
    <div class="bos-panel-head" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
      <input type="search" class="bos-input bos-input-sm" id="cp-search" placeholder="Search name, email, phone…" value="${esc(state.q)}" style="max-width:260px">
      <select class="bos-input bos-input-sm" id="cp-status-filter" style="max-width:140px">
        <option value="">All statuses</option>
        ${["active", "inactive", "blocked", "archived"].map((s) =>
          `<option value="${s}"${state.status === s ? " selected" : ""}>${s}</option>`
        ).join("")}
      </select>
      <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="cp-new-customer">New customer</button>
      <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="cp-import-btn">Import CSV</button>
    </div>
    <div id="cp-customers-table"></div>`;

  const tableEl = container.querySelector("#cp-customers-table");
  renderCustomersTable(tableEl, customers, async (id) => {
    const c = await fetchJson(`/api/customers/${id}`);
    renderProfileDrawer(c);
  });

  container.querySelector("#cp-search")?.addEventListener("input", (e) => {
    state.q = e.target.value;
    clearTimeout(state._timer);
    state._timer = setTimeout(() => renderCustomersList(container, state), 250);
  });
  container.querySelector("#cp-status-filter")?.addEventListener("change", (e) => {
    state.status = e.target.value;
    renderCustomersList(container, state);
  });
  container.querySelector("#cp-new-customer")?.addEventListener("click", () => openCreateCustomer(() => renderCustomersList(container, state)));
  container.querySelector("#cp-import-btn")?.addEventListener("click", () => openImportDialog(() => renderCustomersList(container, state)));
}

function openCreateCustomer(onDone) {
  openDrawer("New customer", `
    <form id="cp-create-form" class="bos-drawer-form">
      <div class="bos-field"><label class="bos-label">Full name</label><input class="bos-input" name="full_name" required></div>
      <div class="bos-field"><label class="bos-label">Email</label><input class="bos-input" name="email" type="email"></div>
      <div class="bos-field"><label class="bos-label">Phone</label><input class="bos-input" name="phone"></div>
      <div class="bos-field"><label class="bos-label">Company</label><input class="bos-input" name="company"></div>
      <div class="bos-drawer-form__actions">
        <button type="submit" class="bos-btn bos-btn-primary">Create</button>
        <button type="button" class="bos-btn bos-btn-ghost" id="cp-create-cancel">Cancel</button>
      </div>
    </form>
  `);
  document.getElementById("cp-create-cancel")?.addEventListener("click", closeDrawer);
  document.getElementById("cp-create-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await apiPost("/api/customers", Object.fromEntries(fd));
    showToast("Customer created");
    closeDrawer();
    onDone?.();
  });
}

function openImportDialog(onDone) {
  openDrawer("Import customers", `
    <p class="cp-muted">Paste CSV with columns: full_name, email, phone, company</p>
    <textarea class="bos-input" id="cp-import-csv" rows="8" placeholder="full_name,email,phone&#10;Jane Doe,jane@example.com,+1234567890"></textarea>
    <button type="button" class="bos-btn bos-btn-primary" id="cp-import-run" style="margin-top:12px">Import</button>
  `);
  document.getElementById("cp-import-run")?.addEventListener("click", async () => {
    const text = document.getElementById("cp-import-csv")?.value?.trim();
    if (!text) return;
    const lines = text.split("\n").filter(Boolean);
    const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
    const rows = lines.slice(1).map((line) => {
      const vals = line.split(",");
      const row = {};
      headers.forEach((h, i) => { row[h] = (vals[i] || "").trim(); });
      return row;
    });
    const result = await apiPost("/api/customers/import", { rows });
    showToast(`Imported ${result.created} new, ${result.merged} duplicates skipped`);
    closeDrawer();
    onDone?.();
  });
}

async function renderGroups(container) {
  const groups = await fetchJson("/api/customers/groups");
  container.innerHTML = `
    <div class="bos-panel-head"><h2 class="bos-panel-title">Customer groups</h2>
      <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="cp-new-group">New group</button>
    </div>
    <div class="bos-table-wrap"><table class="bos-table">
      <thead><tr><th>Name</th><th>Members</th><th>Status</th><th></th></tr></thead>
      <tbody>${groups.map((g) => `<tr><td>${esc(g.name)}</td><td>${g.member_count || 0}</td><td>${statusBadge(g.status)}</td>
        <td><button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-delete-group="${g.id}">Delete</button></td></tr>`).join("") || "<tr><td colspan='4'>No groups yet</td></tr>"}
      </tbody>
    </table></div>`;
  container.querySelector("#cp-new-group")?.addEventListener("click", async () => {
    const name = window.prompt("Group name");
    if (!name?.trim()) return;
    await apiPost("/api/customers/groups", { name: name.trim() });
    showToast("Group created");
    renderGroups(container);
  });
  container.querySelectorAll("[data-delete-group]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.confirm("Delete this group?")) return;
      await fetch(`/api/customers/groups/${btn.dataset.deleteGroup}`, { method: "DELETE", credentials: "same-origin" });
      showToast("Group deleted");
      renderGroups(container);
    });
  });
}

async function renderTags(container) {
  const tags = await fetchJson("/api/customers/tags");
  container.innerHTML = `
    <div class="bos-panel-head"><h2 class="bos-panel-title">Customer tags</h2>
      <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="cp-new-tag">New tag</button>
    </div>
    <div class="cp-tag-grid">${tags.map((t) =>
      `<article class="cp-tag-card"><span>${tag(t.name, t.color)}</span><span class="cp-muted">${t.usage_count || 0} customers</span>
        <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-delete-tag="${t.id}">Delete</button></article>`
    ).join("") || "<p class='cp-muted'>No tags yet</p>"}</div>`;
  container.querySelector("#cp-new-tag")?.addEventListener("click", async () => {
    const name = window.prompt("Tag name");
    if (!name?.trim()) return;
    await apiPost("/api/customers/tags", { name: name.trim() });
    showToast("Tag created");
    renderTags(container);
  });
  container.querySelectorAll("[data-delete-tag]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!window.confirm("Delete this tag?")) return;
      await fetch(`/api/customers/tags/${btn.dataset.deleteTag}`, { method: "DELETE", credentials: "same-origin" });
      showToast("Tag deleted");
      renderTags(container);
    });
  });
}

async function renderActivity(container) {
  const activity = await fetchJson("/api/customers/activity?limit=100");
  container.innerHTML = `
    <section class="bos-panel">
      <div class="bos-panel-head"><h2 class="bos-panel-title">All customer activity</h2></div>
      <ul class="bos-timeline bos-timeline--full">
        ${activity.map((a) =>
          `<li class="cp-activity-item" data-customer-id="${a.customer_id}">
            <strong>${esc(a.full_name || a.customer_code)}</strong> — ${esc(a.title)}
            <span class="cp-muted">${esc(a.activity_type)} · ${esc(a.store_name || "")} · ${(a.created_at || "").slice(0, 16)}</span>
          </li>`
        ).join("") || "<li>No activity yet</li>"}
      </ul>
    </section>`;
  container.querySelectorAll("[data-customer-id]").forEach((el) => {
    el.addEventListener("click", async () => {
      const c = await fetchJson(`/api/customers/${el.dataset.customerId}`);
      renderProfileDrawer(c);
    });
  });
}

async function renderSettings(container) {
  const settings = await fetchJson("/api/customers/settings");
  container.innerHTML = `
    <form id="cp-settings-form" class="bos-form" style="max-width:480px">
      <div class="bos-field"><label class="bos-label">Default status for new customers</label>
        <select class="bos-input" name="default_status">
          ${["active", "inactive"].map((s) => `<option value="${s}"${settings.default_status === s ? " selected" : ""}>${s}</option>`).join("")}
        </select>
      </div>
      <label class="bos-check"><input type="checkbox" name="notify_birthday" ${settings.notify_birthday ? "checked" : ""}> Birthday notifications</label>
      <label class="bos-check"><input type="checkbox" name="notify_new_customer" ${settings.notify_new_customer ? "checked" : ""}> New customer notifications</label>
      <label class="bos-check"><input type="checkbox" name="dedupe_by_email" ${settings.dedupe_by_email ? "checked" : ""}> Dedupe by email on import</label>
      <label class="bos-check"><input type="checkbox" name="dedupe_by_phone" ${settings.dedupe_by_phone ? "checked" : ""}> Dedupe by phone on import</label>
      <button type="submit" class="bos-btn bos-btn-primary" style="margin-top:16px">Save settings</button>
    </form>`;
  container.querySelector("#cp-settings-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await apiPost("/api/customers/settings", {
      default_status: fd.get("default_status"),
      notify_birthday: fd.has("notify_birthday"),
      notify_new_customer: fd.has("notify_new_customer"),
      dedupe_by_email: fd.has("dedupe_by_email"),
      dedupe_by_phone: fd.has("dedupe_by_phone"),
    });
    showToast("Settings saved");
  });
}

/** @param {HTMLElement} root */
export async function mountCustomersPage(root) {
  selection.clear();
  setActionMode(false);
  let section = "overview";
  const state = { q: "", status: "" };

  root.innerHTML = `<div id="cp-subnav"></div><div id="cp-content"><div class="bos-loading">Loading customers…</div></div>`;
  const subnav = root.querySelector("#cp-subnav");
  const content = root.querySelector("#cp-content");

  const render = async () => {
    subnav.innerHTML = renderSubNav(section);
    subnav.querySelectorAll("[data-section]").forEach((btn) => {
      btn.addEventListener("click", () => { section = btn.dataset.section; render(); });
    });
    content.innerHTML = `<div class="bos-loading">Loading…</div>`;
    try {
      if (section === "overview") await renderOverview(content);
      else if (section === "customers") await renderCustomersList(content, state);
      else if (section === "groups") await renderGroups(content);
      else if (section === "tags") await renderTags(content);
      else if (section === "activity") await renderActivity(content);
      else if (section === "settings") await renderSettings(content);
    } catch (err) {
      content.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load</p><p>${esc(err.message)}</p></div>`;
    }
  };

  window.addEventListener("cp:refresh", render);
  await render();
}
