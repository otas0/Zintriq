/** Business OS — Workspace Platform (API-backed operating environment). */

import { renderIntegrationsSection } from "./integrations-section.js";
import { statusBadge, pageHeader, settingsNav, loadingState } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, apiPost, renderActionBar } from "../services/api.js";
import { getCurrentWorkspace, loadWorkspaceList, setActiveWorkspace } from "../services/workspace-context.js";
import { selection } from "../services/selection.js";
import { setActionMode } from "../core/continuity.js";
import { PRODUCT_FLAGS } from "../product-focus.js";

const SECTIONS = [
  { id: "business", label: "Business", hint: "Name, timezone, region" },
  { id: "branding", label: "Branding", hint: "Logo and colors" },
  { id: "team", label: "Team", hint: "Members and roles" },
  { id: "account", label: "Account", hint: "Your login profile" },
  ...(PRODUCT_FLAGS.connectedApps || PRODUCT_FLAGS.integrationsPlaceholder
    ? [{ id: "integrations", label: "Integrations", hint: "Connected apps" }]
    : []),
];

const MODULE_LABELS = {
  qr: "QR Experiences", feedback: "Feedback & Surveys", checkin: "Check-in",
  booking: "Booking", calendar: "Calendar", team: "Team", operations: "Operations",
};

const ROLES = ["owner", "administrator", "manager", "member", "viewer"];

async function fetchJson(url, opts) {
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `Failed (${res.status})`);
  return res.json();
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
}

function renderSubNav(active) {
  return `<nav class="bos-subnav">${SECTIONS.map((s) =>
    `<button type="button" class="bos-subnav__item${s.id === active ? " is-active" : ""}" data-section="${s.id}">${s.label}</button>`
  ).join("")}</nav>`;
}

function statGrid(overview) {
  const o = overview || {};
  return `<section class="bos-dash-grid" style="grid-template-columns:repeat(3,1fr)">
    <article class="bos-stat-card"><span class="bos-stat-val">${o.qr_assets ?? o.qr_experiences ?? 0}</span><span class="bos-stat-lbl">QR Experiences</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${o.feedback ?? o.responses ?? 0}</span><span class="bos-stat-lbl">Responses</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${o.members ?? 0}</span><span class="bos-stat-lbl">Team members</span></article>
  </section>`;
}

async function renderBusiness(container, ws, wsId) {
  const settings = await fetchJson(`/api/workspaces/${wsId}/settings`);
  container.innerHTML = `
    ${statGrid(ws.overview)}
    <section class="bos-panel" style="margin-top:20px">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Business settings</h2></div>
      <form id="ws-settings-form" class="bos-form" style="max-width:520px">
        <div class="bos-field"><label class="bos-label">Business name</label><input class="bos-input" name="name" value="${esc(settings.name)}"></div>
        <div class="bos-grid-2">
          <div class="bos-field"><label class="bos-label">Time zone</label><input class="bos-input" name="timezone" value="${esc(settings.timezone || "Asia/Singapore")}"></div>
          <div class="bos-field"><label class="bos-label">Language</label><input class="bos-input" name="language" value="${esc(settings.language || "en")}"></div>
        </div>
        <div class="bos-grid-2">
          <div class="bos-field"><label class="bos-label">Region</label><input class="bos-input" name="region" value="${esc(settings.region || "")}"></div>
          <div class="bos-field"><label class="bos-label">Currency</label><input class="bos-input" name="currency" value="${esc(settings.currency || "USD")}"></div>
        </div>
        <button type="submit" class="bos-btn bos-btn-primary" style="margin-top:16px">Save</button>
      </form>
    </section>`;
  container.querySelector("#ws-settings-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await apiPost(`/api/workspaces/${wsId}/settings`, Object.fromEntries(fd));
    showToast("Settings saved");
  });
}

async function renderAccount(container) {
  container.innerHTML = `
    <section class="bos-panel" style="max-width:520px">
      <h2 class="bos-panel-title">Account</h2>
      <p class="cp-muted">Manage your login, password, and personal profile.</p>
      <a class="bos-btn bos-btn-primary" href="/account" style="margin-top:12px">Open account settings</a>
    </section>`;
}

async function renderPermissions(container) {
  container.innerHTML = `
    <section class="bos-panel">
      <h2 class="bos-panel-title">Permissions</h2>
      <p class="cp-muted">Role-based access is managed in Team. Each role defines what staff can do with QR Experiences, interactions, and settings.</p>
      <a class="bos-btn bos-btn-primary" href="/app/team" style="margin-top:12px">Manage team &amp; permissions</a>
    </section>`;
}

async function renderBranding(container, wsId) {
  const settings = await fetchJson(`/api/workspaces/${wsId}/settings`);
  const brand = settings.branding || {};
  container.innerHTML = `
    <section class="bos-panel" style="max-width:520px">
      <h2 class="bos-panel-title">Default branding</h2>
      <p class="cp-muted" style="margin-bottom:16px">Applied to new QR Experiences. Each experience can override these.</p>
      <form id="ws-brand-form" class="bos-form">
        <div class="bos-field"><label class="bos-label">Business name</label>
          <input class="bos-input" name="business_name" value="${esc(brand.business_name || settings.name || "")}"></div>
        <div class="bos-field" style="margin-top:12px"><label class="bos-label">Logo URL</label>
          <input class="bos-input" name="logo_url" value="${esc(brand.logo_url || "")}" placeholder="https://…"></div>
        <div class="bos-field" style="margin-top:12px"><label class="bos-label">Background</label>
          <input class="bos-input" name="background" value="${esc(brand.background || "")}" placeholder="#ffffff"></div>
        <button type="submit" class="bos-btn bos-btn-primary" style="margin-top:16px">Save branding</button>
      </form>
    </section>`;
  container.querySelector("#ws-brand-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const branding = Object.fromEntries(fd);
    await apiPost(`/api/workspaces/${wsId}/settings`, {
      name: settings.name,
      logo_url: settings.logo_url,
      timezone: settings.timezone,
      language: settings.language,
      region: settings.region,
      currency: settings.currency,
      branding: JSON.stringify(branding),
    });
    showToast("Branding saved");
  });
}

async function renderStores(container, wsId) {
  const stores = await fetchJson(`/api/workspaces/${wsId}/stores`);
  container.innerHTML = `
    <div class="bos-panel-head" style="margin-bottom:16px">
      <input type="search" class="bos-input bos-input-sm" id="ws-store-search" placeholder="Search stores…" style="max-width:220px">
      <a class="bos-btn bos-btn-primary bos-btn-sm" href="/create">New store</a>
    </div>
    <div class="bos-table-wrap"><table class="bos-table">
      <thead><tr><th>Name</th><th>Slug</th><th>Status</th><th></th></tr></thead>
      <tbody id="ws-stores-body">${stores.map((s) =>
        `<tr><td>${esc(s.name)}</td><td>${esc(s.slug)}</td><td>${statusBadge(s.status || "active")}</td>
          <td><a class="bos-btn bos-btn-ghost bos-btn-sm" href="/manage/${esc(s.slug)}">Open</a></td></tr>`
      ).join("") || "<tr><td colspan='4'>No stores in this workspace</td></tr>"}
      </tbody>
    </table></div>`;
}

async function renderMembers(container, wsId) {
  const members = await fetchJson(`/api/workspaces/${wsId}/members`);
  container.innerHTML = `
    <div class="bos-panel-head" style="margin-bottom:16px">
      <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="ws-invite-btn">Invite member</button>
    </div>
    <div class="bos-table-wrap"><table class="bos-table">
      <thead><tr><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
      <tbody>${members.map((m) =>
        `<tr><td>${esc(m.email)}</td><td>${esc(m.role)}</td><td>${statusBadge(m.status)}</td>
          <td>${m.role !== "owner" ? `<select class="bos-input bos-input-sm ws-role-select" data-user-id="${m.user_id}">${ROLES.map((r) =>
            `<option value="${r}"${r === m.role ? " selected" : ""}>${r}</option>`).join("")}</select>` : "—"}</td></tr>`
      ).join("")}</tbody>
    </table></div>`;
  container.querySelector("#ws-invite-btn")?.addEventListener("click", async () => {
    const email = window.prompt("Member email (must have an account)");
    if (!email?.trim()) return;
    const role = window.prompt("Role: owner, administrator, manager, staff, viewer", "staff") || "staff";
    try {
      await apiPost(`/api/workspaces/${wsId}/members`, { email: email.trim(), role });
      showToast("Member invited");
      renderMembers(container, wsId);
    } catch (e) { showToast(e.message); }
  });
  container.querySelectorAll(".ws-role-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      await fetch(`/api/workspaces/${wsId}/members/${sel.dataset.userId}`, {
        method: "PATCH", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: sel.value }),
      });
      showToast("Role updated");
    });
  });
}

async function renderModules(container, wsId, modules) {
  const mods = modules || await fetchJson(`/api/workspaces/${wsId}/modules`);
  container.innerHTML = `
    <p class="cp-muted" style="margin-bottom:16px">Disable modules to hide them from navigation. Data is preserved.</p>
    <div class="ws-module-grid">${Object.entries(MODULE_LABELS).map(([id, label]) =>
      `<label class="ws-module-card"><input type="checkbox" data-mod="${id}" ${mods[id] !== false ? "checked" : ""}>
        <span>${esc(label)}</span></label>`
    ).join("")}</div>
    <button type="button" class="bos-btn bos-btn-primary" id="ws-modules-save" style="margin-top:16px">Save modules</button>`;
  container.querySelector("#ws-modules-save")?.addEventListener("click", async () => {
    const payload = {};
    container.querySelectorAll("[data-mod]").forEach((cb) => { payload[cb.dataset.mod] = cb.checked; });
    await apiPost(`/api/workspaces/${wsId}/modules`, { modules: payload });
    showToast("Modules updated");
  });
}

async function renderActivity(container, wsId) {
  const activity = await fetchJson(`/api/workspaces/${wsId}/activity?limit=100`);
  container.innerHTML = `
    <ul class="bos-timeline bos-timeline--full">${activity.map((a) =>
      `<li><strong>${esc(a.title)}</strong><br><span class="cp-muted">${esc(a.object_type || "")} · ${esc(a.action)} · ${(a.created_at || "").slice(0, 16)}</span></li>`
    ).join("") || "<li>No workspace activity yet</li>"}</ul>`;
}

function confirmDeleteWorkspace(wsName, onConfirm) {
  openDrawer("Delete workspace?", `
    <p>Delete <strong>${esc(wsName)}</strong> permanently?</p>
    <p class="cp-muted">Stores and customers will move to another workspace. This cannot be undone.</p>
    <div class="ws-delete-actions">
      <button type="button" class="bos-btn bos-btn-danger" id="ws-delete-confirm">Delete</button>
      <button type="button" class="bos-btn bos-btn-ghost" id="ws-delete-cancel">Cancel</button>
    </div>
  `);
  document.getElementById("ws-delete-cancel")?.addEventListener("click", () => closeDrawer());
  document.getElementById("ws-delete-confirm")?.addEventListener("click", async () => {
    closeDrawer();
    await onConfirm();
  });
}

async function renderSettings(container, wsId) {
  const settings = await fetchJson(`/api/workspaces/${wsId}/settings`);
  const canDelete = settings.can_delete;
  container.innerHTML = `
    <form id="ws-settings-form" class="bos-form" style="max-width:520px">
      <div class="bos-field"><label class="bos-label">Workspace name</label><input class="bos-input" name="name" value="${esc(settings.name)}"></div>
      <div class="bos-grid-2">
        <div class="bos-field"><label class="bos-label">Time zone</label><input class="bos-input" name="timezone" value="${esc(settings.timezone || "Asia/Singapore")}"></div>
        <div class="bos-field"><label class="bos-label">Language</label><input class="bos-input" name="language" value="${esc(settings.language || "en")}"></div>
      </div>
      <div class="bos-grid-2">
        <div class="bos-field"><label class="bos-label">Region</label><input class="bos-input" name="region" value="${esc(settings.region || "")}"></div>
        <div class="bos-field"><label class="bos-label">Currency</label><input class="bos-input" name="currency" value="${esc(settings.currency || "USD")}"></div>
      </div>
      <button type="submit" class="bos-btn bos-btn-primary" style="margin-top:16px">Save settings</button>
    </form>
    <section class="bos-panel" style="margin-top:32px;max-width:520px;border-color:var(--color-border)">
      <h3 class="bos-panel-title" style="margin:0 0 8px">Danger zone</h3>
      <p class="cp-muted" style="margin:0 0 16px">Archive hides this workspace. Delete permanently removes it and moves stores and customers to another workspace.</p>
      <button type="button" class="bos-btn bos-btn-ghost bos-btn-danger" id="ws-archive-btn">Archive workspace</button>
      ${canDelete
        ? `<button type="button" class="bos-btn bos-btn-danger" id="ws-delete-btn" style="margin-left:8px">Delete workspace</button>`
        : `<p class="cp-muted" style="margin:12px 0 0">You need at least two workspaces before you can delete one.</p>`}
    </section>`;
  container.querySelector("#ws-settings-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await apiPost(`/api/workspaces/${wsId}/settings`, Object.fromEntries(fd));
    showToast("Settings saved");
  });
  container.querySelector("#ws-archive-btn")?.addEventListener("click", async () => {
    if (!window.confirm("Archive this workspace? You can restore it later.")) return;
    await apiPost(`/api/workspaces/${wsId}/archive`, {});
    showToast("Workspace archived");
  });
  container.querySelector("#ws-delete-btn")?.addEventListener("click", () => {
    confirmDeleteWorkspace(settings.name, async () => {
      try {
        const result = await apiPost(`/api/workspaces/${wsId}/delete`, {});
        await setActiveWorkspace(result.next_workspace_id);
        await loadWorkspaceList();
        showToast("Workspace deleted");
        window.location.reload();
      } catch (e) {
        showToast(e.message);
      }
    });
  });
}

/** @param {HTMLElement} root */
export async function mountWorkspacesPage(root) {
  selection.clear();
  setActionMode(false);
  let section = "business";
  const urlParams = new URLSearchParams(window.location.search);
  if ((urlParams.get("integration") || urlParams.get("integration_error")) && PRODUCT_FLAGS.connectedApps) {
    section = "integrations";
  }
  let ws = await getCurrentWorkspace();

  root.innerHTML = `<div class="merchant-page">
    ${pageHeader({ title: "Settings", subtitle: esc(ws.name) })}
    <div class="merchant-settings">
      <div id="ws-subnav"></div>
      <div id="ws-content"><div class="bos-module-loading" role="status"><div class="bos-skeleton bos-skeleton--card"></div></div></div>
    </div>
  </div>`;

  const subnav = root.querySelector("#ws-subnav");
  const content = root.querySelector("#ws-content");

  const render = async () => {
    subnav.innerHTML = settingsNav(SECTIONS, section);
    subnav.querySelectorAll("[data-section]").forEach((btn) => {
      btn.addEventListener("click", () => { section = btn.dataset.section; render(); });
    });
    content.innerHTML = loadingState("inline");
    try {
      ws = await getCurrentWorkspace();
      if (section === "business") await renderBusiness(content, ws, ws.id);
      else if (section === "branding") await renderBranding(content, ws.id);
      else if (section === "account") await renderAccount(content);
      else if (section === "team") await renderMembers(content, ws.id);
      else if (section === "integrations" && (PRODUCT_FLAGS.connectedApps || PRODUCT_FLAGS.integrationsPlaceholder)) {
        await renderIntegrationsSection(content, ws.id);
      }
    } catch (err) {
      content.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load</p><p>${esc(err.message)}</p></div>`;
    }
  };

  await render();
}
