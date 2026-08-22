/** Zintriq — Booking Platform Foundation. */

import { statusBadge } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, apiPost } from "../services/api.js";
import { fetchJson, esc, wsQuery } from "../services/bos-api.js";

const VIEWS = [
  { id: "today", label: "Today" },
  { id: "upcoming", label: "Upcoming" },
  { id: "all", label: "All" },
];

const STATUSES = [
  { id: "", label: "All statuses" },
  { id: "pending", label: "Pending" },
  { id: "confirmed", label: "Confirmed" },
  { id: "checked_in", label: "Checked in" },
  { id: "completed", label: "Completed" },
  { id: "cancelled", label: "Cancelled" },
  { id: "no_show", label: "No show" },
];

/** @type {{ view: string, status: string, q: string, assigned: string }} */
const state = { view: "today", status: "", q: "", assigned: "" };

function formatTime(iso) {
  if (!iso) return "—";
  return iso.slice(0, 16).replace("T", " ");
}

function bookingRow(b) {
  const customer = b.customer?.name || b.customer_name || b.title;
  const staff = b.assignee?.name || "—";
  return `<tr data-id="${b.id}" class="bos-row-click">
    <td>${esc(customer)}</td>
    <td>${esc(b.title || "—")}</td>
    <td>${formatTime(b.starts_at)}</td>
    <td>${esc(staff)}</td>
    <td>${statusBadge(b.status)}</td>
  </tr>`;
}

async function loadMembers() {
  try {
    const params = new URLSearchParams(wsQuery().replace("?", ""));
    return await fetchJson(`/api/team/members?${params}`);
  } catch {
    return [];
  }
}

async function loadContacts(q = "") {
  try {
    const params = new URLSearchParams(wsQuery().replace("?", ""));
    if (q) params.set("q", q);
    params.set("view", "all");
    return await fetchJson(`/api/contacts?${params}`);
  } catch {
    return [];
  }
}

async function openBookingDrawer(id, onDone) {
  const [b, activity, members] = await Promise.all([
    fetchJson(`/api/bookings/${id}${wsQuery()}`),
    fetchJson(`/api/bookings/${id}/activity${wsQuery()}`).catch(() => []),
    loadMembers(),
  ]);

  const activityHtml = activity.length
    ? `<ul class="bk-activity">${activity.map((a) =>
        `<li><strong>${esc(a.title)}</strong><br><span class="cp-muted">${esc((a.created_at || "").slice(0, 16))}</span></li>`
      ).join("")}</ul>`
    : `<p class="cp-muted">No activity yet.</p>`;

  const memberOptions = members.map((m) =>
    `<option value="${m.user_id}"${b.assigned_member_id === m.user_id ? " selected" : ""}>${esc(m.display_name || m.email)}</option>`
  ).join("");

  openDrawer(b.customer?.name || b.title, `
    <dl class="cp-meta">
      <dt>Booking ID</dt><dd>#${b.id}</dd>
      <dt>Service</dt><dd>${esc(b.title)}</dd>
      <dt>Time</dt><dd>${esc(formatTime(b.starts_at))}${b.ends_at ? ` – ${esc(formatTime(b.ends_at))}` : ""}</dd>
      <dt>Status</dt><dd>${statusBadge(b.status)}</dd>
      <dt>Location</dt><dd>${esc(b.location || "—")}</dd>
      <dt>Customer</dt><dd>${esc(b.customer?.name || "—")}</dd>
      <dt>Email</dt><dd>${esc(b.customer?.email || "—")}</dd>
      <dt>Phone</dt><dd>${esc(b.customer?.phone || "—")}</dd>
      <dt>Assigned staff</dt><dd>${esc(b.assignee?.name || "—")}</dd>
      ${b.calendar_event_id ? `<dt>Calendar</dt><dd><a href="/app/calendar">Event #${b.calendar_event_id}</a></dd>` : ""}
      <dt>Notes</dt><dd>${esc(b.notes || "—")}</dd>
    </dl>
    <h4 class="bos-drawer-section">Reschedule</h4>
    <form id="bk-edit-form" class="bos-drawer-form">
      <div class="bos-field"><label class="bos-label">Start</label><input class="bos-input" name="starts_at" type="datetime-local" value="${(b.starts_at || "").slice(0, 16).replace(" ", "T")}"></div>
      <div class="bos-field"><label class="bos-label">Location</label><input class="bos-input" name="location" value="${esc(b.location || "")}"></div>
      <div class="bos-field"><label class="bos-label">Assign staff</label>
        <select class="bos-input" name="assigned_member_id">
          <option value="">Unassigned</option>
          ${memberOptions}
        </select>
      </div>
      <button type="submit" class="bos-btn bos-btn-primary bos-btn-sm">Save changes</button>
    </form>
    <h4 class="bos-drawer-section">Activity</h4>
    ${activityHtml}
    <div class="bos-form-actions" style="margin-top:16px">
      ${b.status !== "cancelled" ? `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="bk-cancel">Cancel booking</button>` : ""}
    </div>
  `);

  document.getElementById("bk-edit-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      starts_at: fd.get("starts_at"),
      location: fd.get("location"),
    };
    const assignee = fd.get("assigned_member_id");
    if (assignee) body.assigned_member_id = Number(assignee);
    else body.assigned_member_id = null;
    await fetch(`/api/bookings/${id}${wsQuery()}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "",
      },
      body: JSON.stringify(body),
    });
    showToast("Booking updated");
    closeDrawer();
    onDone?.();
  });

  document.getElementById("bk-cancel")?.addEventListener("click", async () => {
    await apiPost(`/api/bookings/${id}/cancel`, {});
    showToast("Booking cancelled");
    closeDrawer();
    onDone?.();
  });
}

function openCreateBooking(onDone) {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const defaultStart = now.toISOString().slice(0, 16);

  openDrawer("New booking", `
    <form id="bk-create-form" class="bos-drawer-form">
      <div class="bos-field"><label class="bos-label">Customer</label>
        <input class="bos-input" name="contact_search" id="bk-contact-search" placeholder="Search contacts…" autocomplete="off">
        <input type="hidden" name="contact_id" id="bk-contact-id">
        <div id="bk-contact-results" class="bk-contact-results"></div>
      </div>
      <div class="bos-field"><label class="bos-label">Service / title</label><input class="bos-input" name="title" required></div>
      <div class="bos-field"><label class="bos-label">Start</label><input class="bos-input" name="starts_at" type="datetime-local" value="${defaultStart}" required></div>
      <div class="bos-field"><label class="bos-label">Location</label><input class="bos-input" name="location"></div>
      <div class="bos-field"><label class="bos-label">Assign staff</label><select class="bos-input" name="assigned_member_id" id="bk-assign-select"><option value="">Loading…</option></select></div>
      <div class="bos-field"><label class="bos-label">Notes</label><textarea class="bos-input" name="notes" rows="2"></textarea></div>
      <div class="bos-drawer-form__actions">
        <button type="submit" class="bos-btn bos-btn-primary">Create booking</button>
        <button type="button" class="bos-btn bos-btn-ghost" id="bk-create-cancel">Cancel</button>
      </div>
    </form>
  `);

  loadMembers().then((members) => {
    const sel = document.getElementById("bk-assign-select");
    if (!sel) return;
    sel.innerHTML = `<option value="">Unassigned</option>${members.map((m) =>
      `<option value="${m.user_id}">${esc(m.display_name || m.email)}</option>`
    ).join("")}`;
  });

  let contactTimer;
  document.getElementById("bk-contact-search")?.addEventListener("input", (e) => {
    clearTimeout(contactTimer);
    const q = e.target.value.trim();
    contactTimer = setTimeout(async () => {
      const box = document.getElementById("bk-contact-results");
      if (!box || q.length < 1) { box.innerHTML = ""; return; }
      const contacts = await loadContacts(q);
      box.innerHTML = contacts.slice(0, 8).map((c) =>
        `<button type="button" class="bk-contact-pick" data-id="${c.id}" data-name="${esc(c.name || c.full_name || "")}">${esc(c.name || c.full_name || c.email)}</button>`
      ).join("") || `<span class="cp-muted">No contacts found</span>`;
      box.querySelectorAll(".bk-contact-pick").forEach((btn) => {
        btn.addEventListener("click", () => {
          document.getElementById("bk-contact-id").value = btn.dataset.id;
          document.getElementById("bk-contact-search").value = btn.dataset.name;
          box.innerHTML = "";
        });
      });
    }, 250);
  });

  document.getElementById("bk-create-cancel")?.addEventListener("click", closeDrawer);
  document.getElementById("bk-create-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const contactId = fd.get("contact_id");
    if (!contactId) {
      showToast("Select a customer from contacts");
      return;
    }
    const body = {
      contact_id: Number(contactId),
      title: fd.get("title"),
      starts_at: fd.get("starts_at"),
      location: fd.get("location"),
      notes: fd.get("notes"),
    };
    const assignee = fd.get("assigned_member_id");
    if (assignee) body.assigned_member_id = Number(assignee);
    await apiPost("/api/bookings", body);
    showToast("Booking created");
    closeDrawer();
    onDone?.();
  });
}

/** @param {HTMLElement} root */
export async function mountBookingPage(root) {
  const members = await loadMembers();

  const render = async () => {
    root.innerHTML = `<div class="bos-loading">Loading bookings…</div>`;
    try {
      const params = new URLSearchParams(wsQuery().replace("?", ""));
      params.set("view", state.view);
      if (state.status) params.set("status", state.status);
      if (state.q) params.set("q", state.q);
      if (state.assigned) params.set("assigned_member_id", state.assigned);
      const bookings = await fetchJson(`/api/bookings?${params}`);

      root.innerHTML = `
        <nav class="bos-subnav" aria-label="Booking views">
          ${VIEWS.map((v) =>
            `<button type="button" class="bos-subnav__item${v.id === state.view ? " is-active" : ""}" data-view="${v.id}">${v.label}</button>`
          ).join("")}
        </nav>
        <div class="bk-toolbar">
          <input class="bos-input bk-search" type="search" placeholder="Search customer or booking ID…" value="${esc(state.q)}" id="bk-search">
          <select class="bos-input" id="bk-status-filter">
            ${STATUSES.map((s) => `<option value="${s.id}"${s.id === state.status ? " selected" : ""}>${s.label}</option>`).join("")}
          </select>
          <select class="bos-input" id="bk-staff-filter">
            <option value="">All staff</option>
            ${members.map((m) => `<option value="${m.user_id}"${String(m.user_id) === state.assigned ? " selected" : ""}>${esc(m.display_name || m.email)}</option>`).join("")}
          </select>
          <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="bk-new">New booking</button>
        </div>
        <div class="bos-table-wrap">
          <table class="bos-table">
            <thead><tr><th>Customer</th><th>Service</th><th>Time</th><th>Staff</th><th>Status</th></tr></thead>
            <tbody>${bookings.map(bookingRow).join("") || "<tr><td colspan='5' class='cp-muted'>No bookings yet</td></tr>"}</tbody>
          </table>
        </div>`;

      root.querySelectorAll("[data-view]").forEach((btn) => {
        btn.addEventListener("click", () => { state.view = btn.dataset.view; render(); });
      });
      root.querySelector("#bk-search")?.addEventListener("change", (e) => { state.q = e.target.value.trim(); render(); });
      root.querySelector("#bk-status-filter")?.addEventListener("change", (e) => { state.status = e.target.value; render(); });
      root.querySelector("#bk-staff-filter")?.addEventListener("change", (e) => { state.assigned = e.target.value; render(); });
      root.querySelectorAll(".bos-row-click").forEach((row) => {
        row.addEventListener("click", () => openBookingDrawer(Number(row.dataset.id), render));
      });
      root.querySelector("#bk-new")?.addEventListener("click", () => openCreateBooking(render));
    } catch (err) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load bookings</p><p>${esc(err.message)}</p></div>`;
    }
  };

  window.addEventListener("booking:refresh", render);
  await render();
}
