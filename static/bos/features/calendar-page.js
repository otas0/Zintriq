/** Zintriq — Calendar (operational support for bookings and events). */

import { statusBadge } from "../components/index.js";
import { showToast, openDrawer, closeDrawer, apiPost } from "../services/api.js";
import { fetchJson, esc, wsQuery } from "../services/bos-api.js";

const VIEWS = [
  { id: "day", label: "Day" },
  { id: "week", label: "Week" },
  { id: "month", label: "Month" },
];

const EVENT_TYPE_LABELS = {
  booking: "Booking",
  meeting: "Meeting",
  appointment: "Appointment",
  check_in: "Check-in",
  business_event: "Event",
  reminder: "Reminder",
};

const SOURCE_LABELS = {
  business_os: "Zintriq",
  microsoft_calendar: "Microsoft Calendar",
};

/** @type {{ view: string, date: string }} */
const state = { view: "day", date: todayIso() };

function todayIso() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function formatTime(iso) {
  if (!iso) return "—";
  const s = iso.replace(" ", "T");
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 16);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateLabel(iso) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

function weekDates(iso) {
  const d = new Date(iso + "T12:00:00");
  const day = d.getDay();
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((day + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const x = new Date(monday);
    x.setDate(monday.getDate() + i);
    return x.toISOString().slice(0, 10);
  });
}

function monthGrid(iso) {
  const d = new Date(iso + "T12:00:00");
  const first = new Date(d.getFullYear(), d.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7));
  const cells = [];
  for (let i = 0; i < 42; i++) {
    const c = new Date(start);
    c.setDate(start.getDate() + i);
    cells.push(c.toISOString().slice(0, 10));
  }
  return { month: d.getMonth(), year: d.getFullYear(), cells };
}

const OPERATIONAL_LABELS = {
  scheduled: "Scheduled",
  checked_in: "Checked in",
  completed: "Completed",
};

function operationalBadge(ev) {
  const op = ev.operational_status;
  if (!op || op === "scheduled") return "";
  const label = OPERATIONAL_LABELS[op] || op;
  const cls = op === "completed" ? "bos-badge--active" : "bos-badge--muted";
  return `<span class="bos-badge ${cls}">${esc(label)}</span>`;
}

function sourceBadge(ev) {
  const label = SOURCE_LABELS[ev.source] || ev.source;
  const cls = ev.source === "business_os" ? "bos-badge--active" : "bos-badge--muted";
  return `<span class="bos-badge ${cls}">${esc(label)}</span>`;
}

function eventCard(ev, compact = false) {
  const related = ev.related
    ? `<span class="cp-muted">${esc(EVENT_TYPE_LABELS[ev.event_type] || ev.event_type)} · #${ev.related.id}</span>`
    : `<span class="cp-muted">${esc(EVENT_TYPE_LABELS[ev.event_type] || ev.event_type)}</span>`;
  const participants = ev.participants?.length
    ? `<span class="cp-muted">${ev.participants.length} participant${ev.participants.length > 1 ? "s" : ""}</span>`
    : "";
  if (compact) {
    return `<button type="button" class="cal-event-chip" data-id="${ev.id}" title="${esc(ev.title)}">
      <span class="cal-event-chip__time">${formatTime(ev.start_time)}</span>
      <span class="cal-event-chip__title">${esc(ev.title)}</span>
    </button>`;
  }
  return `<article class="cal-event-row" data-id="${ev.id}">
    <div class="cal-event-row__time">${formatTime(ev.start_time)}${ev.end_time ? ` – ${formatTime(ev.end_time)}` : ""}</div>
    <div class="cal-event-row__body">
      <strong>${esc(ev.title)}</strong>
      <div class="cal-event-row__meta">${related} ${participants} ${sourceBadge(ev)} ${operationalBadge(ev)} ${ev.status !== "confirmed" ? statusBadge(ev.status) : ""}</div>
    </div>
  </article>`;
}

async function openEventDrawer(id) {
  const ev = await fetchJson(`/api/calendar/${id}${wsQuery()}`);
  const relatedLink = ev.related?.type === "booking"
    ? `<p><a href="/app/booking">Booking #${ev.related.id}</a></p>`
    : ev.related?.type === "check_in"
      ? `<p><a href="/app/check-in">Check-in #${ev.related.id}</a></p>`
      : "";
  const participantList = ev.participants?.length
    ? `<ul>${ev.participants.map((p) => `<li>${esc(p.name || p.email || `User ${p.user_id || ""}`)}</li>`).join("")}</ul>`
    : "<p class=\"cp-muted\">None</p>";

  openDrawer(ev.title, `
    <dl class="cp-meta">
      <dt>Time</dt><dd>${esc((ev.start_time || "").slice(0, 16))}${ev.end_time ? ` – ${esc((ev.end_time || "").slice(0, 16))}` : ""}</dd>
      <dt>Type</dt><dd>${esc(EVENT_TYPE_LABELS[ev.event_type] || ev.event_type)}</dd>
      <dt>Source</dt><dd>${sourceBadge(ev)}</dd>
      <dt>Status</dt><dd>${statusBadge(ev.status)} ${operationalBadge(ev)}</dd>
      <dt>Location</dt><dd>${esc(ev.location || "—")}</dd>
      <dt>Visibility</dt><dd>${esc(ev.visibility)}</dd>
    </dl>
    ${ev.description ? `<p>${esc(ev.description)}</p>` : ""}
    ${relatedLink}
    <h4 class="bos-drawer-section">Participants</h4>
    ${participantList}
    ${ev.source === "business_os" && !ev.related ? `
      <div class="bos-form-actions">
        ${ev.status === "confirmed" ? `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="cal-cancel">Cancel event</button>` : ""}
        <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm bos-btn-danger" id="cal-delete">Archive</button>
      </div>` : ""}
  `);

  document.getElementById("cal-cancel")?.addEventListener("click", async () => {
    await apiPost(`/api/calendar/${id}/cancel`, {});
    showToast("Event cancelled");
    closeDrawer();
    window.dispatchEvent(new CustomEvent("calendar:refresh"));
  });
  document.getElementById("cal-delete")?.addEventListener("click", async () => {
    await fetch(`/api/calendar/${id}${wsQuery()}`, {
      method: "DELETE",
      headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "" },
    });
    showToast("Event archived");
    closeDrawer();
    window.dispatchEvent(new CustomEvent("calendar:refresh"));
  });
}

function openCreateEvent(onDone) {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  const defaultStart = `${state.date}T${now.toISOString().slice(11, 16)}`;
  openDrawer("New event", `
    <form id="cal-create-form" class="bos-drawer-form">
      <div class="bos-field"><label class="bos-label">Title</label><input class="bos-input" name="title" required></div>
      <div class="bos-field"><label class="bos-label">Type</label>
        <select class="bos-input" name="event_type">
          <option value="meeting">Meeting</option>
          <option value="appointment">Appointment</option>
          <option value="business_event">Business event</option>
          <option value="reminder">Reminder</option>
        </select>
      </div>
      <div class="bos-field"><label class="bos-label">Start</label><input class="bos-input" name="start_time" type="datetime-local" value="${defaultStart}" required></div>
      <div class="bos-field"><label class="bos-label">Location</label><input class="bos-input" name="location"></div>
      <div class="bos-field"><label class="bos-label">Description</label><textarea class="bos-input" name="description" rows="2"></textarea></div>
      <div class="bos-field"><label class="bos-label">Visibility</label>
        <select class="bos-input" name="visibility">
          <option value="workspace">Workspace</option>
          <option value="team">Team</option>
          <option value="private">Private</option>
        </select>
      </div>
      <div class="bos-drawer-form__actions">
        <button type="submit" class="bos-btn bos-btn-primary">Create event</button>
        <button type="button" class="bos-btn bos-btn-ghost" id="cal-create-cancel">Cancel</button>
      </div>
    </form>
  `);
  document.getElementById("cal-create-cancel")?.addEventListener("click", closeDrawer);
  document.getElementById("cal-create-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await apiPost("/api/calendar", {
      title: fd.get("title"),
      event_type: fd.get("event_type"),
      start_time: fd.get("start_time"),
      location: fd.get("location"),
      description: fd.get("description"),
      visibility: fd.get("visibility"),
    });
    const startVal = String(fd.get("start_time") || "");
    if (startVal) state.date = startVal.slice(0, 10);
    showToast("Event created");
    closeDrawer();
    onDone?.();
  });
}

function renderDayView(events) {
  const active = events.filter((e) => e.status === "confirmed" || e.status === "cancelled");
  if (!active.length) {
    return `<div class="bos-empty"><p class="bos-empty__title">No events</p><p class="cp-muted">Nothing scheduled for this day.</p></div>`;
  }
  return `<div class="cal-day-list">${active.map((e) => eventCard(e)).join("")}</div>`;
}

function renderWeekView(events) {
  const dates = weekDates(state.date);
  const byDate = Object.fromEntries(dates.map((d) => [d, []]));
  events.forEach((ev) => {
    const d = (ev.start_time || "").slice(0, 10);
    if (byDate[d]) byDate[d].push(ev);
  });
  return `<div class="cal-week-grid">${dates.map((d) => `
    <section class="cal-week-col${d === state.date ? " is-today" : ""}">
      <header class="cal-week-col__head">
        <button type="button" class="cal-week-col__date" data-goto="${d}">${new Date(d + "T12:00:00").toLocaleDateString([], { weekday: "short", day: "numeric" })}</button>
      </header>
      <div class="cal-week-col__body">${(byDate[d] || []).map((e) => eventCard(e, true)).join("") || `<span class="cp-muted">—</span>`}</div>
    </section>`).join("")}</div>`;
}

function renderMonthView(events) {
  const { month, year, cells } = monthGrid(state.date);
  const byDate = {};
  events.forEach((ev) => {
    const d = (ev.start_time || "").slice(0, 10);
    if (!byDate[d]) byDate[d] = [];
    byDate[d].push(ev);
  });
  const monthLabel = new Date(year, month, 1).toLocaleDateString([], { month: "long", year: "numeric" });
  return `
    <p class="cal-month-label">${esc(monthLabel)}</p>
    <div class="cal-month-grid">
      ${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => `<div class="cal-month-dow">${d}</div>`).join("")}
      ${cells.map((d) => {
        const inMonth = new Date(d + "T12:00:00").getMonth() === month;
        const count = (byDate[d] || []).length;
        return `<button type="button" class="cal-month-cell${inMonth ? "" : " is-other"}${d === todayIso() ? " is-today" : ""}" data-goto="${d}">
          <span class="cal-month-cell__day">${parseInt(d.slice(8), 10)}</span>
          ${count ? `<span class="cal-month-cell__count">${count} event${count > 1 ? "s" : ""}</span>` : ""}
        </button>`;
      }).join("")}
    </div>`;
}

function bindEventClicks(root) {
  root.querySelectorAll("[data-id]").forEach((el) => {
    el.addEventListener("click", () => openEventDrawer(Number(el.dataset.id)));
  });
  root.querySelectorAll("[data-goto]").forEach((el) => {
    el.addEventListener("click", () => {
      state.date = el.dataset.goto;
      state.view = "day";
      window.dispatchEvent(new CustomEvent("calendar:refresh"));
    });
  });
}

/** @param {HTMLElement} root */
export async function mountCalendarPage(root) {
  const render = async () => {
    root.innerHTML = `<div class="bos-loading">Loading calendar…</div>`;
    try {
      const params = new URLSearchParams(wsQuery().replace("?", ""));
      params.set("view", state.view);
      params.set("date", state.date);
      const events = await fetchJson(`/api/calendar?${params}`);

      let body = "";
      if (state.view === "week") body = renderWeekView(events);
      else if (state.view === "month") body = renderMonthView(events);
      else body = renderDayView(events);

      root.innerHTML = `
        <nav class="bos-subnav" aria-label="Calendar views">
          ${VIEWS.map((v) =>
            `<button type="button" class="bos-subnav__item${v.id === state.view ? " is-active" : ""}" data-view="${v.id}">${v.label}</button>`
          ).join("")}
        </nav>
        <div class="cal-toolbar">
          <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="cal-prev">←</button>
          <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="cal-today">Today</button>
          <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="cal-next">→</button>
          <span class="cal-toolbar__label">${esc(formatDateLabel(state.date))}</span>
          <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="cal-new" style="margin-left:auto">New event</button>
        </div>
        ${body}`;

      root.querySelectorAll("[data-view]").forEach((btn) => {
        btn.addEventListener("click", () => { state.view = btn.dataset.view; render(); });
      });
      root.querySelector("#cal-prev")?.addEventListener("click", () => {
        const step = state.view === "month" ? 30 : state.view === "week" ? 7 : 1;
        state.date = addDays(state.date, -step);
        render();
      });
      root.querySelector("#cal-next")?.addEventListener("click", () => {
        const step = state.view === "month" ? 30 : state.view === "week" ? 7 : 1;
        state.date = addDays(state.date, step);
        render();
      });
      root.querySelector("#cal-today")?.addEventListener("click", () => { state.date = todayIso(); render(); });
      root.querySelector("#cal-new")?.addEventListener("click", () => openCreateEvent(render));
      bindEventClicks(root);
    } catch (err) {
      root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load calendar</p><p>${esc(err.message)}</p></div>`;
    }
  };

  window.addEventListener("calendar:refresh", render);
  await render();
}
