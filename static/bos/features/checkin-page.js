/** Zintriq — Check-in Platform Foundation. */

import { statusBadge } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, apiPost } from "../services/api.js";
import { fetchJson, esc, wsQuery } from "../services/bos-api.js";

const VIEWS = [
  { id: "today", label: "Today" },
  { id: "live", label: "Live" },
  { id: "all", label: "All" },
];

const STATUSES = [
  { id: "", label: "All statuses" },
  { id: "waiting", label: "Waiting" },
  { id: "checked_in", label: "Checked in" },
  { id: "in_progress", label: "In progress" },
  { id: "completed", label: "Completed" },
  { id: "cancelled", label: "Cancelled" },
  { id: "no_show", label: "No show" },
];

const SOURCES = [
  { id: "", label: "All sources" },
  { id: "booking", label: "Booking" },
  { id: "qr", label: "QR" },
  { id: "manual", label: "Manual" },
  { id: "walk_in", label: "Walk-in" },
  { id: "event", label: "Event" },
];

/** @type {{ view: string, status: string, source: string, q: string }} */
const state = { view: "today", status: "", source: "", q: "" };

function formatTime(iso) {
  if (!iso) return "—";
  return iso.slice(11, 16);
}

function checkinRow(c) {
  const customer = c.customer?.name || c.customer_name || "Guest";
  const staff = c.staff?.name || "—";
  return `<tr class="bos-row-click" data-id="${c.id}">
    <td>${esc(customer)}</td>
    <td>${formatTime(c.checked_in_at)}</td>
    <td>${esc(c.source || c.method)}</td>
    <td>${statusBadge(c.status)}</td>
    <td>${esc(staff)}</td>
  </tr>`;
}

async function loadContacts(q = "") {
  try {
    const params = new URLSearchParams(wsQuery().replace("?", ""));
    if (q) params.set("q", q);
    return await fetchJson(`/api/contacts?${params}`);
  } catch {
    return [];
  }
}

async function loadBookings() {
  try {
    const params = new URLSearchParams(wsQuery().replace("?", ""));
    params.set("view", "upcoming");
    return await fetchJson(`/api/bookings?${params}`);
  } catch {
    return [];
  }
}

async function openCheckinDetail(id, onDone) {
  const [c, activity] = await Promise.all([
    fetchJson(`/api/check-ins/${id}${wsQuery()}`),
    fetchJson(`/api/check-ins/${id}/activity${wsQuery()}`).catch(() => []),
  ]);

  const activityHtml = activity.length
    ? `<ul class="ci-activity">${activity.map((a) =>
        `<li><strong>${esc(a.title)}</strong><br><span class="cp-muted">${esc((a.created_at || "").slice(0, 16))}</span></li>`
      ).join("")}</ul>`
    : `<p class="cp-muted">No activity yet.</p>`;

  openDrawer(c.customer?.name || c.customer_name || "Check-in", `
    <dl class="cp-meta">
      <dt>Check-in ID</dt><dd>#${c.id}</dd>
      <dt>Status</dt><dd>${statusBadge(c.status)}</dd>
      <dt>Source</dt><dd>${esc(c.source || c.method)}</dd>
      <dt>Arrival</dt><dd>${esc((c.checked_in_at || "").slice(0, 16))}</dd>
      ${c.check_out_time ? `<dt>Check-out</dt><dd>${esc(c.check_out_time.slice(0, 16))}</dd>` : ""}
      <dt>Staff</dt><dd>${esc(c.staff?.name || "—")}</dd>
      <dt>Customer</dt><dd>${esc(c.customer?.name || c.customer_name || "—")}</dd>
      ${c.booking ? `<dt>Booking</dt><dd><a href="/app/booking">#${c.booking.id} — ${esc(c.booking.title)}</a></dd>` : ""}
      <dt>Notes</dt><dd>${esc(c.notes || "—")}</dd>
    </dl>
    <h4 class="bos-drawer-section">Activity</h4>
    ${activityHtml}
    <div class="bos-form-actions" style="margin-top:16px">
      ${c.status === "checked_in" ? `<button type="button" class="bos-btn bos-btn-sm bos-btn-primary" id="ci-start">Start service</button>` : ""}
      ${["checked_in", "in_progress"].includes(c.status) ? `<button type="button" class="bos-btn bos-btn-sm bos-btn-primary" id="ci-complete">Complete</button>` : ""}
    </div>
  `);

  document.getElementById("ci-start")?.addEventListener("click", async () => {
    await fetch(`/api/check-ins/${id}${wsQuery()}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "",
      },
      body: JSON.stringify({ status: "in_progress" }),
    });
    showToast("Service started");
    closeDrawer();
    onDone?.();
  });

  document.getElementById("ci-complete")?.addEventListener("click", async () => {
    await apiPost(`/api/check-ins/${id}/complete`, {});
    showToast("Check-in completed");
    closeDrawer();
    onDone?.();
  });
}

function openCheckinForm(onDone) {
  openDrawer("Check in customer", `
    <form id="ci-create-form" class="bos-drawer-form">
      <div class="bos-field"><label class="bos-label">Customer</label>
        <input class="bos-input" id="ci-contact-search" placeholder="Search contacts…" autocomplete="off">
        <input type="hidden" name="contact_id" id="ci-contact-id">
        <div id="ci-contact-results" class="bk-contact-results"></div>
      </div>
      <div class="bos-field"><label class="bos-label">Or guest name (walk-in)</label>
        <input class="bos-input" name="customer_name" placeholder="Walk-in guest name">
      </div>
      <div class="bos-field"><label class="bos-label">Source</label>
        <select class="bos-input" name="source">
          ${SOURCES.filter((s) => s.id).map((s) => `<option value="${s.id}">${s.label}</option>`).join("")}
        </select>
      </div>
      <div class="bos-field"><label class="bos-label">Booking (optional)</label>
        <select class="bos-input" name="booking_id" id="ci-booking-select"><option value="">None</option></select>
      </div>
      <div class="bos-field"><label class="bos-label">Notes</label><textarea class="bos-input" name="notes" rows="2"></textarea></div>
      <div class="bos-drawer-form__actions">
        <button type="submit" class="bos-btn bos-btn-primary">Check in</button>
        <button type="button" class="bos-btn bos-btn-ghost" id="ci-create-cancel">Cancel</button>
      </div>
    </form>
  `);

  loadBookings().then((bookings) => {
    const sel = document.getElementById("ci-booking-select");
    if (!sel) return;
    sel.innerHTML = `<option value="">None</option>${bookings.map((b) =>
      `<option value="${b.id}">#${b.id} — ${esc(b.customer?.name || b.customer_name || b.title)}</option>`
    ).join("")}`;
  });

  let timer;
  document.getElementById("ci-contact-search")?.addEventListener("input", (e) => {
    clearTimeout(timer);
    const q = e.target.value.trim();
    timer = setTimeout(async () => {
      const box = document.getElementById("ci-contact-results");
      if (!box || q.length < 1) { box.innerHTML = ""; return; }
      const contacts = await loadContacts(q);
      box.innerHTML = contacts.slice(0, 8).map((c) =>
        `<button type="button" class="bk-contact-pick" data-id="${c.id}" data-name="${esc(c.name || "")}">${esc(c.name || c.email)}</button>`
      ).join("") || `<span class="cp-muted">No contacts</span>`;
      box.querySelectorAll(".bk-contact-pick").forEach((btn) => {
        btn.addEventListener("click", () => {
          document.getElementById("ci-contact-id").value = btn.dataset.id;
          document.getElementById("ci-contact-search").value = btn.dataset.name;
          box.innerHTML = "";
        });
      });
    }, 250);
  });

  document.getElementById("ci-create-cancel")?.addEventListener("click", closeDrawer);
  document.getElementById("ci-create-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const contactId = fd.get("contact_id");
    const guestName = fd.get("customer_name");
    if (!contactId && !guestName) {
      showToast("Select a customer or enter a guest name");
      return;
    }
    const body = {
      source: fd.get("source") || "manual",
      notes: fd.get("notes"),
    };
    if (contactId) body.contact_id = Number(contactId);
    else {
      body.customer_name = guestName;
      body.source = "walk_in";
    }
    const bookingId = fd.get("booking_id");
    if (bookingId) body.booking_id = Number(bookingId);
    try {
      await apiPost("/api/check-ins", body);
      showToast("Customer checked in");
      closeDrawer();
      onDone?.();
    } catch (err) {
      showToast(err.message || "Check-in failed");
    }
  });
}

/** @param {HTMLElement} root */
export async function mountCheckinPage(root) {
  const render = async () => {
    root.innerHTML = `<div class="bos-loading">Loading check-ins…</div>`;
    try {
      const summary = await fetchJson(`/api/check-ins/summary${wsQuery()}`);
      const params = new URLSearchParams(wsQuery().replace("?", ""));
      params.set("view", state.view);
      if (state.status) params.set("status", state.status);
      if (state.source) params.set("source", state.source);
      if (state.q) params.set("q", state.q);
      const checkins = await fetchJson(`/api/check-ins?${params}`);

      root.innerHTML = `
        <section class="bos-dash-grid" style="margin-bottom:16px">
          <article class="bos-stat-card"><span class="bos-stat-val">${summary.today}</span><span class="bos-stat-lbl">Today</span></article>
          <article class="bos-stat-card"><span class="bos-stat-val">${summary.live}</span><span class="bos-stat-lbl">Live (2h)</span></article>
        </section>
        <nav class="bos-subnav" aria-label="Check-in views">
          ${VIEWS.map((v) =>
            `<button type="button" class="bos-subnav__item${v.id === state.view ? " is-active" : ""}" data-view="${v.id}">${v.label}</button>`
          ).join("")}
        </nav>
        <div class="bk-toolbar">
          <input class="bos-input bk-search" type="search" placeholder="Search customer or booking ID…" value="${esc(state.q)}" id="ci-search">
          <select class="bos-input" id="ci-status-filter">
            ${STATUSES.map((s) => `<option value="${s.id}"${s.id === state.status ? " selected" : ""}>${s.label}</option>`).join("")}
          </select>
          <select class="bos-input" id="ci-source-filter">
            ${SOURCES.map((s) => `<option value="${s.id}"${s.id === state.source ? " selected" : ""}>${s.label}</option>`).join("")}
          </select>
          <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="ci-new">Check in</button>
        </div>
        <div class="bos-table-wrap">
          <table class="bos-table">
            <thead><tr><th>Customer</th><th>Time</th><th>Source</th><th>Status</th><th>Staff</th></tr></thead>
            <tbody>${checkins.map(checkinRow).join("") || "<tr><td colspan='5' class='cp-muted'>No check-ins yet</td></tr>"}</tbody>
          </table>
        </div>`;

      root.querySelectorAll("[data-view]").forEach((btn) => {
        btn.addEventListener("click", () => { state.view = btn.dataset.view; render(); });
      });
      root.querySelector("#ci-search")?.addEventListener("change", (e) => { state.q = e.target.value.trim(); render(); });
      root.querySelector("#ci-status-filter")?.addEventListener("change", (e) => { state.status = e.target.value; render(); });
      root.querySelector("#ci-source-filter")?.addEventListener("change", (e) => { state.source = e.target.value; render(); });
      root.querySelectorAll(".bos-row-click").forEach((row) => {
        row.addEventListener("click", () => openCheckinDetail(Number(row.dataset.id), render));
      });
      root.querySelector("#ci-new")?.addEventListener("click", () => openCheckinForm(render));
    } catch (err) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load check-ins</p><p>${esc(err.message)}</p></div>`;
    }
  };
  window.addEventListener("checkin:refresh", render);
  await render();
}
