/** Business OS — Interactions (unified customer activity from QR). */

import { statusBadge } from "../components/index.js";
import { escapeHtml } from "../services/search.js";
import { fetchJson, wsQuery } from "../services/bos-api.js";

function stars(rating) {
  if (!rating) return "—";
  return "★".repeat(Math.min(5, rating)) + "☆".repeat(Math.max(0, 5 - rating));
}

/** @param {HTMLElement} root */
export async function mountInteractionsPage(root) {
  root.innerHTML = `<div class="bos-loading">Loading interactions…</div>`;
  try {
    const data = await fetchJson(`/api/interactions/summary${wsQuery()}`);
    const { feedback = [], bookings = [], checkins = [], counts = {} } = data;

    root.innerHTML = `
      <p class="cp-muted" style="margin:0 0 20px">Customer activity from your QR Experiences — feedback, bookings, and check-ins in one place.</p>

      <section class="bos-dash-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr));margin-bottom:24px">
        <a href="#feedback" class="bos-stat-card bos-stat-card--link">
          <span class="bos-stat-val">${counts.new_feedback ?? 0}</span>
          <span class="bos-stat-lbl">New feedback</span>
        </a>
        <a href="#bookings" class="bos-stat-card bos-stat-card--link">
          <span class="bos-stat-val">${counts.pending_bookings ?? 0}</span>
          <span class="bos-stat-lbl">Pending bookings</span>
        </a>
        <a href="#checkins" class="bos-stat-card bos-stat-card--link">
          <span class="bos-stat-val">${counts.today_checkins ?? 0}</span>
          <span class="bos-stat-lbl">Check-ins today</span>
        </a>
        <a href="/app/qr" class="bos-stat-card bos-stat-card--link">
          <span class="bos-stat-val">${counts.active_qr ?? 0}</span>
          <span class="bos-stat-lbl">Active QR</span>
        </a>
      </section>

      <section class="bos-panel" id="feedback" style="margin-bottom:20px">
        <div class="bos-panel-head">
          <h2 class="bos-panel-title">Feedback &amp; surveys</h2>
          ${counts.new_feedback ? `<span class="bos-badge">${counts.new_feedback} new</span>` : ""}
        </div>
        ${feedback.length ? `
          <ul class="bos-action-list">
            ${feedback.map((f) => `
              <li class="bos-action-item">
                <div>
                  <strong>${stars(f.rating)}</strong>
                  <span class="cp-muted" style="margin-left:8px;font-size:13px">${escapeHtml((f.comment || "").slice(0, 100))}</span>
                </div>
                <a class="bos-btn bos-btn-sm bos-btn-primary" href="/app/feedback">View response</a>
              </li>`).join("")}
          </ul>` : `<p class="cp-muted">No new feedback — publish a QR Experience with a survey to collect responses.</p>`}
      </section>

      <section class="bos-panel" id="bookings" style="margin-bottom:20px">
        <div class="bos-panel-head">
          <h2 class="bos-panel-title">Bookings</h2>
          <a class="bos-btn bos-btn-ghost bos-btn-sm" href="/app/booking">Open bookings</a>
        </div>
        ${bookings.length ? `
          <ul class="bos-action-list">
            ${bookings.map((b) => `
              <li class="bos-action-item">
                <div>
                  <strong>${escapeHtml(b.customer_name || b.title || "Booking")}</strong>
                  <span class="cp-muted" style="display:block;font-size:13px">${escapeHtml((b.starts_at || "").slice(0, 16))} · ${escapeHtml(b.status || "")}</span>
                </div>
                <a class="bos-btn bos-btn-sm bos-btn-ghost" href="/app/booking">Manage</a>
              </li>`).join("")}
          </ul>` : `<p class="cp-muted">No bookings today.</p>`}
      </section>

      <section class="bos-panel" id="checkins">
        <div class="bos-panel-head">
          <h2 class="bos-panel-title">Check-ins</h2>
          <a class="bos-btn bos-btn-ghost bos-btn-sm" href="/app/check-in">Open check-ins</a>
        </div>
        ${checkins.length ? `
          <ul class="bos-action-list">
            ${checkins.map((c) => `
              <li class="bos-action-item">
                <div>
                  <strong>${escapeHtml(c.customer_name || "Guest")}</strong>
                  <span class="cp-muted" style="display:block;font-size:13px">${escapeHtml((c.checked_in_at || "").slice(0, 16))}</span>
                </div>
                ${statusBadge("completed")}
              </li>`).join("")}
          </ul>` : `<p class="cp-muted">No check-ins today.</p>`}
      </section>`;
  } catch (err) {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load interactions</p><p>${escapeHtml(err.message)}</p></div>`;
  }
}
