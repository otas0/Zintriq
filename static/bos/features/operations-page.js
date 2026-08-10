/** Operations hub — bookings, check-ins, calendar from QR Experiences. */

import { escapeHtml } from "../services/search.js";
import { fetchJson, wsQuery } from "../services/bos-api.js";
import { loadingState, sectionHeader, button } from "../components/index.js";

/** @param {HTMLElement} root */
export async function mountOperationsPage(root) {
  root.innerHTML = loadingState();
  let data = { today_bookings: 0, today_checkins: 0, pending_bookings: 0, bookings: [], checkins: [] };
  try {
    data = await fetchJson(`/api/home/summary${wsQuery()}`);
  } catch { /* ignore */ }

  root.innerHTML = `
    <section class="bos-panel" style="margin-bottom:20px">
      ${sectionHeader({ title: "Today" })}
      <div class="bos-today-grid">
        <p><strong>${data.today_bookings ?? 0}</strong> booking${data.today_bookings === 1 ? "" : "s"} scheduled</p>
        <p><strong>${data.today_checkins ?? 0}</strong> check-in${data.today_checkins === 1 ? "" : "s"}</p>
        ${data.pending_bookings ? `<p><strong>${data.pending_bookings}</strong> pending to review</p>` : ""}
      </div>
    </section>

    <section class="bos-dash-grid" style="margin-bottom:20px">
      <a href="/app/booking" class="bos-action-card">
        <div class="bos-action-card__body">
          <strong>Bookings</strong>
          <p class="cp-muted" style="margin:4px 0 0;font-size:13px">${data.pending_bookings ? `${data.pending_bookings} pending` : "Manage reservations"}</p>
        </div>
        <span class="bos-btn bos-btn-sm bos-btn-primary">Open</span>
      </a>
      <a href="/app/check-in" class="bos-action-card">
        <div class="bos-action-card__body">
          <strong>Check-in</strong>
          <p class="cp-muted" style="margin:4px 0 0;font-size:13px">${data.today_checkins ? `${data.today_checkins} today` : "Customer arrivals"}</p>
        </div>
        <span class="bos-btn bos-btn-sm bos-btn-primary">Open</span>
      </a>
      <a href="/app/calendar" class="bos-action-card">
        <div class="bos-action-card__body">
          <strong>Calendar</strong>
          <p class="cp-muted" style="margin:4px 0 0;font-size:13px">Upcoming activities</p>
        </div>
        <span class="bos-btn bos-btn-sm bos-btn-ghost">View</span>
      </a>
      <a href="/app/store#experiences" class="bos-action-card">
        <div class="bos-action-card__body">
          <strong>Customer QR</strong>
          <p class="cp-muted" style="margin:4px 0 0;font-size:13px">Shop codes and landing pages</p>
        </div>
        <span class="bos-btn bos-btn-sm bos-btn-ghost">Manage</span>
      </a>
    </section>

    ${(data.bookings || []).length ? `
    <section class="bos-panel">
      ${sectionHeader({
        title: "Upcoming today",
        actionsHtml: button({ variant: "ghost", label: "All bookings", tag: "a", href: "/app/booking", sm: true }),
      })}
      <ul class="bos-action-list">
        ${data.bookings.slice(0, 5).map((b) => `
          <li class="bos-action-item">
            <div>
              <strong>${escapeHtml(b.customer_name || b.title || "Booking")}</strong>
              <span class="cp-muted" style="display:block;font-size:13px">${escapeHtml((b.starts_at || "").slice(0, 16))}</span>
            </div>
            <a class="bos-btn bos-btn-sm bos-btn-ghost" href="/app/booking">Manage</a>
          </li>`).join("")}
      </ul>
    </section>` : ""}
  `;
}
