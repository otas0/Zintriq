/** Business OS — Team Platform (multi-user collaboration foundation). */

import { StatusBadge, statusBadge, MemberCard, mountCardGrid, PageHeader, Skeleton, InviteMemberModal } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, renderActionBar } from "../services/api.js";
import { fetchJson, esc, wsQuery } from "../services/bos-api.js";
import { getActiveWorkspaceId } from "../services/workspace-context.js";
import { selection } from "../services/selection.js";
import { setActionMode } from "../core/continuity.js";
import { hasPermission, loadTeamContext } from "../services/permissions.js";
import { MVP_TEAM_ROLES } from "../product-focus.js";

const MVP_SECTIONS = [
  { id: "members", label: "Members" },
  { id: "invitations", label: "Invitations" },
];

const SECTIONS = [
  ...MVP_SECTIONS,
  { id: "roles", label: "Roles" },
  { id: "activity", label: "Activity" },
  { id: "settings", label: "Settings" },
];

const ROLES = ["owner", "administrator", "manager", "member", "viewer"];
const MVP_INVITE_ROLES = MVP_TEAM_ROLES.map((r) => r.db);

function mvpRoleLabel(role) {
  const map = { owner: "Owner", admin: "Admin", administrator: "Admin", member: "Member", manager: "Admin", viewer: "Member" };
  return map[String(role || "").toLowerCase()] || role || "Member";
}
const BULK = [
  { label: "Suspend", action: "suspend" },
  { label: "Change role…", action: "role" },
  { label: "Remove", action: "remove", variant: "danger" },
];

/** @type {{ section: string, wsId: number|null, members: object[], invitations: object[] }} */
const state = { section: "members", wsId: null, members: [], invitations: [] };

function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/);
  return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

function presenceDot(presence) {
  const cls = presence === "online" ? "bos-presence--online" : "bos-presence--offline";
  return `<span class="bos-presence ${cls}" title="${esc(presence)}"></span>`;
}

function renderSubNav(active) {
  return `<nav class="bos-subnav" aria-label="Team sections">
    ${MVP_SECTIONS.map((s) => `<button type="button" class="bos-subnav__item${s.id === active ? " is-active" : ""}" data-section="${s.id}">${s.label}</button>`).join("")}
  </nav>`;
}

function memberRow(m) {
  return `<tr data-id="${m.user_id}" class="bos-row-click">
    <td><input type="checkbox" data-select-id="${m.user_id}" onclick="event.stopPropagation()" ${m.role === "owner" ? "disabled" : ""}></td>
    <td><span class="cp-avatar">${initials(m.display_name)}</span> ${presenceDot(m.presence)} ${esc(m.display_name)}</td>
    <td>${esc(m.email)}</td>
    <td>${esc(m.role)}</td>
    <td>${statusBadge(m.status)}</td>
    <td>${esc((m.joined_at || "").slice(0, 10))}</td>
    <td>${esc((m.last_active_at || "").slice(0, 16).replace("T", " ")) || "—"}</td>
  </tr>`;
}

async function loadMembers(filters = {}) {
  const params = new URLSearchParams(wsQuery().replace("?", ""));
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  if (filters.role) params.set("role", filters.role);
  if (filters.sort) params.set("sort", filters.sort);
  const qs = params.toString();
  return fetchJson(`/api/team/members${qs ? `?${qs}` : ""}`);
}

async function openMemberDrawer(userId) {
  const m = await fetchJson(`/api/team/members/${userId}${wsQuery()}`);
  const canUpdate = hasPermission("member.update");
  const canRemove = hasPermission("member.remove");
  const canSuspend = hasPermission("member.suspend");
  openDrawer(m.display_name || m.email, `
    <div class="bos-obj-overview">
      <div class="bos-obj-overview__head">
        <span class="cp-avatar cp-avatar--lg">${initials(m.display_name)}</span>
        ${statusBadge(m.status)} ${presenceDot(m.presence)}
      </div>
      <dl class="bos-prop-list bos-prop-list--compact">
        <div class="bos-prop-row"><dt>Email</dt><dd>${esc(m.email)}</dd></div>
        <div class="bos-prop-row"><dt>Role</dt><dd>${canUpdate && m.role !== "owner" ? `<select id="tm-role">${MVP_INVITE_ROLES.map((r) => `<option value="${r}"${r === m.role ? " selected" : ""}>${mvpRoleLabel(r)}</option>`).join("")}</select>` : esc(mvpRoleLabel(m.mvp_role || m.role))}</dd></div>
        <div class="bos-prop-row"><dt>Joined</dt><dd>${esc((m.joined_at || "").slice(0, 10))}</dd></div>
        <div class="bos-prop-row"><dt>Last active</dt><dd>${esc((m.last_active_at || "—").slice(0, 16).replace("T", " "))}</dd></div>
      </dl>
      ${canUpdate || canRemove || canSuspend ? `<div class="bos-form-actions">
        ${canSuspend && m.status === "active" && m.role !== "owner" ? `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="tm-suspend">Suspend</button>` : ""}
        ${canUpdate && m.status === "suspended" ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="tm-reactivate">Reactivate</button>` : ""}
        ${canRemove && m.role !== "owner" ? `<button type="button" class="bos-btn bos-btn-danger bos-btn-sm" id="tm-remove">Remove</button>` : ""}
        ${canUpdate && m.role !== "owner" ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="tm-save">Save role</button>` : ""}
      </div>` : ""}
      <h4 class="bos-section-title">Activity</h4>
      <ul class="bos-timeline">${(m.activity || []).map((a) => `<li class="bos-timeline__item"><span class="bos-timeline__msg">${esc(a.title)}</span><span class="bos-timeline__meta">${esc((a.created_at || "").slice(0, 10))}</span></li>`).join("") || `<li class="bos-empty__text">No activity yet</li>`}</ul>
    </div>`);

  document.getElementById("tm-save")?.addEventListener("click", async () => {
    const role = document.getElementById("tm-role")?.value;
    try {
      await fetchJson(`/api/team/members/${userId}${wsQuery()}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) });
      showToast("Role updated");
      closeDrawer();
      renderSection(state.section);
    } catch (e) { showToast(e instanceof Error ? e.message : "Failed"); }
  });
  document.getElementById("tm-suspend")?.addEventListener("click", () => patchMember(userId, { status: "suspended" }));
  document.getElementById("tm-reactivate")?.addEventListener("click", () => patchMember(userId, { status: "active" }));
  document.getElementById("tm-remove")?.addEventListener("click", () => {
    if (confirm("Remove this member from the workspace? History will be preserved.")) {
      patchMember(userId, { status: "removed" });
    }
  });
}

async function patchMember(userId, body) {
  try {
    await fetchJson(`/api/team/members/${userId}${wsQuery()}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    showToast("Member updated");
    closeDrawer();
    renderSection(state.section);
  } catch (e) { showToast(e instanceof Error ? e.message : "Failed"); }
}

function bindMemberTable(container) {
  container.querySelectorAll(".bos-row-click").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("input")) return;
      openMemberDrawer(Number(row.dataset.id));
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
  container.querySelector("#tm-select-all")?.addEventListener("change", (e) => {
    container.querySelectorAll("[data-select-id]:not(:disabled)").forEach((input) => {
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
  const bulk = BULK.filter((b) => {
    if (b.action === "remove") return hasPermission("member.remove");
    if (b.action === "suspend") return hasPermission("member.suspend");
    if (b.action === "role") return hasPermission("member.update");
    return true;
  });
  renderActionBar(selection.size, bulk, handleBulk);
}

async function handleBulk(action) {
  const ids = [...selection];
  if (!ids.length) return;
  if (action === "role") {
    const role = prompt("New role:", "member");
    if (!role || !ROLES.includes(role) || role === "owner") return;
    await batchMembers("role", ids, { role });
    return;
  }
  if (action === "remove" && !confirm(`Remove ${ids.length} member(s)?`)) return;
  const map = { suspend: "suspend", remove: "remove" };
  await batchMembers(map[action] || action, ids);
}

async function batchMembers(action, userIds, extra = {}) {
  try {
    const data = await fetchJson("/api/team/members/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_id: state.wsId, action, user_ids: userIds, ...extra }),
    });
    showToast(`Updated ${data.count} member(s)`);
    selection.clear();
    setActionMode(false);
    renderSection("members");
  } catch (e) { showToast(e instanceof Error ? e.message : "Batch failed"); }
}

async function renderMembers(container, root) {
  const filters = {
    q: root.querySelector("#tm-search")?.value || "",
    status: root.querySelector("#tm-filter-status")?.value || "",
    role: root.querySelector("#tm-filter-role")?.value || "",
    sort: root.querySelector("#tm-sort")?.value || "name",
  };
  container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Loading members…</p></div>`;
  const members = await loadMembers(filters);
  state.members = members;

  const inviteBtn = hasPermission("member.invite")
    ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="tm-invite">Invite member</button>` : "";

  container.innerHTML = `
    <div class="bos-filter-bar" style="margin-bottom:16px">
      ${inviteBtn}
      <input type="search" class="bos-input" id="tm-search" placeholder="Search name or email…" value="${esc(filters.q)}">
      <select id="tm-filter-role"><option value="">All roles</option>${["owner", ...MVP_INVITE_ROLES].map((r) => `<option value="${r}"${filters.role === r ? " selected" : ""}>${mvpRoleLabel(r)}</option>`).join("")}</select>
    </div>
    <div id="tm-member-grid"></div>`;

  const grid = container.querySelector("#tm-member-grid");
  if (!members.length) {
    grid.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No team members yet</p><p>Invite collaborators to work together in this workspace.</p></div>`;
  } else {
    mountCardGrid(grid, members, MemberCard);
    grid.querySelectorAll(".merchant-member-card").forEach((card) => {
      card.addEventListener("click", () => openMemberDrawer(Number(card.dataset.id)));
    });
  }

  ["tm-search", "tm-filter-role"].forEach((id) => {
    container.querySelector(`#${id}`)?.addEventListener("change", () => renderMembers(container, root));
    container.querySelector(`#${id}`)?.addEventListener("input", () => {
      if (id === "tm-search") renderMembers(container, root);
    });
  });
  container.querySelector("#tm-invite")?.addEventListener("click", () => openInviteDrawer());
}

function openInviteDrawer() {
  InviteMemberModal({
    roles: MVP_INVITE_ROLES,
    onSubmit: async ({ email, role }) => {
      const inv = await fetchJson("/api/team/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: state.wsId, email, role }),
      });
      showToast("Invitation sent");
      if (inv.accept_url) {
        navigator.clipboard?.writeText(window.location.origin + inv.accept_url);
        showToast("Invite link copied to clipboard");
      }
      const body = document.getElementById("team-body");
      const root = document.getElementById("team-root");
      if (body && root) await renderMembers(body, root);
    },
  });
}

async function renderInvitations(container) {
  container.innerHTML = `<div class="bos-empty"><p>Loading…</p></div>`;
  const rows = await fetchJson(`/api/team/invitations${wsQuery()}`);
  state.invitations = rows;
  const canInvite = hasPermission("member.invite");
  container.innerHTML = `
    ${canInvite ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="tm-invite" style="margin-bottom:12px">Invite member</button>` : ""}
    ${rows.length ? `<div class="bos-table-wrap"><table class="bos-table"><thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Expires</th><th></th></tr></thead>
    <tbody>${rows.map((i) => `<tr>
      <td>${esc(i.email)}</td><td>${esc(i.role)}</td><td>${statusBadge(i.status)}</td>
      <td>${esc((i.expires_at || "").slice(0, 10))}</td>
      <td>${i.status === "pending" && canInvite ? `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-resend="${i.id}">Resend</button>
        <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-cancel="${i.id}">Cancel</button>` : ""}</td>
    </tr>`).join("")}</tbody></table></div>`
      : `<div class="bos-empty"><p class="bos-empty__title">No invitations</p></div>`}`;
  container.querySelector("#tm-invite")?.addEventListener("click", openInviteDrawer);
  container.querySelectorAll("[data-resend]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const data = await fetchJson(`/api/team/invitations/${btn.getAttribute("data-resend")}/resend`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace_id: state.wsId }),
        });
        if (data.accept_url) navigator.clipboard?.writeText(window.location.origin + data.accept_url);
        showToast("Invitation resent — link copied");
      } catch (e) { showToast(e instanceof Error ? e.message : "Failed"); }
    });
  });
  container.querySelectorAll("[data-cancel]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await fetchJson(`/api/team/invitations/${btn.getAttribute("data-cancel")}/cancel`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ workspace_id: state.wsId }),
        });
        showToast("Invitation cancelled");
        renderInvitations(container);
      } catch (e) { showToast(e instanceof Error ? e.message : "Failed"); }
    });
  });
}

async function renderRoles(container) {
  const roles = await fetchJson(`/api/team/roles${wsQuery()}`);
  container.innerHTML = roles.map((r) => `
    <section class="bos-panel" style="margin-bottom:12px">
      <div class="bos-panel-head"><h2 class="bos-panel-title">${esc(r.label)}</h2></div>
      <ul class="bos-tag-list">${r.permissions.map((p) => `<li><code>${esc(p)}</code></li>`).join("")}</ul>
    </section>`).join("");
}

async function renderActivity(container) {
  const rows = await fetchJson(`/api/team/activity${wsQuery()}`);
  container.innerHTML = `<ul class="bos-timeline">${rows.map((a) => `
    <li class="bos-timeline__item">
      <span class="bos-timeline__action">${esc(a.event_type || "")}</span>
      <span class="bos-timeline__msg">${esc(a.title || "")}</span>
      <span class="bos-timeline__meta">${esc(a.actor_email || a.actor_name || "system")} · ${esc((a.created_at || "").slice(0, 10))}</span>
    </li>`).join("") || `<li class="bos-empty__text">No team activity yet</li>`}</ul>`;
}

async function renderSettings(container) {
  const summary = await fetchJson(`/api/team/summary${wsQuery()}`);
  const canTransfer = hasPermission("workspace.transfer_ownership");
  const members = state.members.length ? state.members : await loadMembers();
  container.innerHTML = `
    <section class="bos-panel">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Team overview</h2></div>
      <div class="bos-dash-grid">
        <article class="bos-stat-card"><span class="bos-stat-val">${summary.active}</span><span class="bos-stat-lbl">Active</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${summary.online}</span><span class="bos-stat-lbl">Online</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${summary.pending_invitations}</span><span class="bos-stat-lbl">Pending invites</span></article>
      </div>
    </section>
    ${canTransfer ? `<section class="bos-panel bos-panel--danger">
      <div class="bos-panel-head"><h2 class="bos-panel-title">Transfer ownership</h2></div>
      <label class="bos-field"><span>New owner</span>
        <select id="tm-new-owner">${members.filter((m) => m.status === "active" && m.role !== "owner").map((m) => `<option value="${m.user_id}">${esc(m.display_name)} (${esc(m.email)})</option>`).join("")}</select>
      </label>
      <button type="button" class="bos-btn bos-btn-danger bos-btn-sm" id="tm-transfer">Transfer ownership</button>
    </section>` : ""}`;

  container.querySelector("#tm-transfer")?.addEventListener("click", async () => {
    const newOwnerId = Number(document.getElementById("tm-new-owner")?.value);
    if (!newOwnerId || !confirm("Transfer workspace ownership? You will become an administrator.")) return;
    try {
      await fetchJson("/api/team/transfer-ownership", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: state.wsId, new_owner_id: newOwnerId }),
      });
      showToast("Ownership transferred");
      await loadTeamContext(state.wsId);
      renderSection("settings");
    } catch (e) { showToast(e instanceof Error ? e.message : "Failed"); }
  });
}

async function renderSection(section) {
  const root = document.getElementById("team-root");
  const body = document.getElementById("team-body");
  if (!root || !body) return;
  state.section = section;
  selection.clear();
  setActionMode(false);
  root.querySelectorAll(".bos-subnav__item").forEach((btn) => {
    btn.classList.toggle("is-active", btn.getAttribute("data-section") === section);
  });
  if (section === "members") await renderMembers(body, root);
  else if (section === "invitations") await renderInvitations(body);
  else if (section === "roles") await renderRoles(body);
  else if (section === "activity") await renderActivity(body);
  else if (section === "settings") await renderSettings(body);
}

export async function mountTeamPage(root) {
  state.wsId = getActiveWorkspaceId();
  root.innerHTML = Skeleton("page");
  try {
    await loadTeamContext(state.wsId);
    root.innerHTML = `<div class="merchant-page" id="team-root">
      ${PageHeader({ title: "Team", subtitle: "People who can access this workspace" })}
      ${renderSubNav("members")}
      <div id="team-body"></div>
    </div>`;
    root.querySelectorAll(".bos-subnav__item").forEach((btn) => {
      btn.addEventListener("click", () => renderSection(btn.getAttribute("data-section") || "members"));
    });
    await renderMembers(document.getElementById("team-body"), root);
  } catch (err) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load team</p><p>${esc(err instanceof Error ? err.message : "Error")}</p></div>`;
  }
}
