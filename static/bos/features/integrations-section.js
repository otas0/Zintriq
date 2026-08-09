/** Connected Apps — integration marketplace (Settings). */

import { showToast, openDrawer, closeDrawer, apiPost } from "../services/api.js";
import { fetchJson, esc } from "../services/bos-api.js";
import { PRODUCT_FLAGS } from "../product-focus.js";

const STATUS_LABELS = {
  not_connected: "Not Connected",
  connected: "Connected",
  active: "Active",
  disconnected: "Disconnected",
  error: "Error",
  syncing: "Syncing",
};

function statusBadgeClass(status) {
  if (status === "active" || status === "connected") return "bos-badge--active";
  if (status === "error") return "bos-badge--danger";
  if (status === "syncing") return "bos-badge--muted";
  return "bos-badge--muted";
}

function pluginStatus(plugin) {
  if (!plugin.connection) return "not_connected";
  return plugin.connection.status || "connected";
}

function integrationCard(plugin) {
  const status = pluginStatus(plugin);
  const canConnect = plugin.slug === "google_calendar";
  return `<article class="bos-panel ws-integration-card" data-slug="${esc(plugin.slug)}">
    <div class="ws-integration-card__head">
      <span class="ws-integration-card__logo" aria-hidden="true">${plugin.slug === "google_calendar" ? "📅" : plugin.slug === "stripe" ? "💳" : "📄"}</span>
      <div>
        <h3 class="bos-panel-title" style="margin:0">${esc(plugin.name)}</h3>
        <p class="cp-muted" style="margin:4px 0 0">${esc(plugin.description)}</p>
      </div>
    </div>
    <p style="margin:12px 0"><span class="bos-badge ${statusBadgeClass(status)}">${esc(STATUS_LABELS[status] || status)}</span></p>
    <div class="ws-integration-card__actions">
      ${canConnect
        ? (status === "not_connected" || status === "disconnected"
          ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" data-connect="${esc(plugin.slug)}">Connect</button>`
          : `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-manage="${esc(plugin.slug)}">Manage</button>`)
        : `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" disabled>Coming soon</button>`}
    </div>
  </article>`;
}

export async function renderIntegrationsPlaceholder(container) {
  container.innerHTML = `
    <section class="bos-panel">
      <h2 class="bos-panel-title">Integrations</h2>
      <p class="cp-muted" style="margin-bottom:20px">Connect external tools when you're ready. Experiences work without any integrations.</p>
      <div class="merchant-grid" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr))">
        <article class="bos-panel ws-integration-card" style="opacity:.85">
          <h3 class="bos-panel-title" style="margin:0;font-size:15px">Google Calendar</h3>
          <p class="cp-muted" style="margin:8px 0 12px;font-size:13px">Sync bookings and events</p>
          <span class="bos-badge bos-badge--muted">Coming soon</span>
        </article>
        <article class="bos-panel ws-integration-card" style="opacity:.85">
          <h3 class="bos-panel-title" style="margin:0;font-size:15px">Stripe</h3>
          <p class="cp-muted" style="margin:8px 0 12px;font-size:13px">Accept payments</p>
          <span class="bos-badge bos-badge--muted">Coming soon</span>
        </article>
        <article class="bos-panel ws-integration-card" style="opacity:.85">
          <h3 class="bos-panel-title" style="margin:0;font-size:15px">Email notifications</h3>
          <p class="cp-muted" style="margin:8px 0 12px;font-size:13px">Alert your team on new responses</p>
          <span class="bos-badge bos-badge--muted">Coming soon</span>
        </article>
      </div>
    </section>`;
}

async function connectGoogleCalendar() {
  const res = await fetchJson("/api/integrations/google-calendar/oauth/start");
  if (res.auth_url) {
    window.location.href = res.auth_url;
  }
}

async function openGoogleCalendarDrawer() {
  const status = await fetchJson("/api/integrations/google-calendar/status");
  let calendars = [];
  if (status.connected) {
    try {
      calendars = await fetchJson("/api/integrations/google-calendar/calendars");
    } catch {
      calendars = [];
    }
  }

  const cal = status.calendar;
  openDrawer("Google Calendar", `
    <div class="cp-profile">
      <p><span class="bos-badge ${statusBadgeClass(status.status || "not_connected")}">${esc(STATUS_LABELS[status.status] || status.status || "Not Connected")}</span></p>
      ${status.external_account_email ? `<p class="cp-muted">Google account: ${esc(status.external_account_email)}</p>` : ""}
      ${status.signed_in_as ? `<p class="cp-muted">Signed in as: ${esc(status.signed_in_as)}</p>` : ""}
      ${status.pending_sync ? `<p>${status.pending_sync} event(s) waiting to sync — click below.</p>` : ""}
      ${cal?.name ? `<p>Calendar: <strong>${esc(cal.name)}</strong></p>` : ""}
      ${status.connected ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="gc-sync-now" style="margin-top:8px">Sync events now</button>` : ""}
      ${status.connected && calendars.length ? `
        <div class="bos-field" style="margin-top:16px">
          <label class="bos-label">Choose calendar</label>
          <select class="bos-input" id="gc-cal-select">
            ${calendars.map((c) =>
              `<option value="${esc(c.id)}" data-name="${esc(c.name)}"${cal?.id === c.id ? " selected" : ""}>${esc(c.name)}</option>`
            ).join("")}
          </select>
          <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="gc-save-cal" style="margin-top:8px">Save calendar</button>
        </div>` : ""}
      ${status.recent_logs?.length ? `
        <h4 class="bos-drawer-section">Sync history</h4>
        <ul class="bos-timeline">${status.recent_logs.slice(0, 8).map((l) =>
          `<li>${esc(l.event_type)} — ${esc(l.status)} ${l.error_message ? `<span class="cp-muted">${esc(l.error_message)}</span>` : ""}</li>`
        ).join("")}</ul>` : ""}
      ${status.connected ? `<button type="button" class="bos-btn bos-btn-danger bos-btn-sm" id="gc-disconnect" style="margin-top:16px">Disconnect</button>` : ""}
    </div>
  `);

  document.getElementById("gc-sync-now")?.addEventListener("click", async () => {
    const result = await apiPost("/api/integrations/google-calendar/sync", {});
    const out = result.outbound?.synced ?? 0;
    const imp = result.inbound?.imported ?? 0;
    const upd = result.inbound?.updated ?? 0;
    const skip = result.outbound?.skipped || result.inbound?.skipped;
    if (skip) {
      showToast(`Sync skipped: ${skip}. Connect Google and select a calendar first.`);
    } else {
      showToast(`Synced ${out} to Google · imported ${imp}, updated ${upd} from Google`);
    }
    closeDrawer();
  });

  document.getElementById("gc-save-cal")?.addEventListener("click", async () => {
    const sel = document.getElementById("gc-cal-select");
    const opt = sel?.selectedOptions?.[0];
    if (!opt) return;
    const result = await apiPost("/api/integrations/google-calendar/calendar", {
      google_calendar_id: opt.value,
      calendar_name: opt.dataset.name || opt.textContent,
    });
    const n = result.sync?.outbound?.synced ?? 0;
    const imp = result.sync?.inbound?.imported ?? 0;
    showToast(n || imp ? `Synced ${n} to Google · ${imp} imported from Google` : "Calendar saved — sync active");
    closeDrawer();
  });

  document.getElementById("gc-disconnect")?.addEventListener("click", async () => {
    if (!window.confirm("Disconnect Google Calendar? Tokens will be removed.")) return;
    await apiPost("/api/integrations/google-calendar/disconnect", {});
    showToast("Disconnected");
    closeDrawer();
  });
}

async function handleOAuthReturn() {
  if (!PRODUCT_FLAGS.connectedApps || !PRODUCT_FLAGS.googleCalendarSync) return;
  const params = new URLSearchParams(window.location.search);
  if (params.get("integration") === "google_calendar" && params.get("step") === "select-calendar") {
    window.history.replaceState({}, "", "/app/settings");
    await openGoogleCalendarDrawer();
  }
  if (params.get("integration_error")) {
    showToast(`Connection failed: ${params.get("integration_error")}`);
    window.history.replaceState({}, "", "/app/settings");
  }
}

/** @param {HTMLElement} container */
export async function renderIntegrationsSection(container) {
  if (PRODUCT_FLAGS.integrationsPlaceholder && !PRODUCT_FLAGS.connectedApps) {
    await renderIntegrationsPlaceholder(container);
    return;
  }
  if (!PRODUCT_FLAGS.connectedApps) {
    container.innerHTML = `
      <section class="bos-panel">
        <div class="bos-panel-head"><h2 class="bos-panel-title">Connected Apps</h2></div>
        <p class="cp-muted">External integrations are paused while we focus on QR-based business workflows. Core features — QR, surveys, feedback, check-in, and booking — work without plugins.</p>
      </section>`;
    return;
  }
  container.innerHTML = `<div class="bos-loading">Loading integrations…</div>`;
  try {
    let plugins = await fetchJson("/api/integrations/plugins");
    if (!PRODUCT_FLAGS.googleCalendarSync) {
      plugins = plugins.filter((p) => p.slug !== "google_calendar");
    }
    container.innerHTML = `
      <section class="bos-panel">
        <div class="bos-panel-head"><h2 class="bos-panel-title">Connected Apps</h2></div>
        <p class="cp-muted">Optional plugins extend Business OS. Core features work without them.</p>
      </section>
      <div class="ws-integration-grid">${plugins.map(integrationCard).join("")}</div>`;

    container.querySelectorAll("[data-connect]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.connect === "google_calendar") connectGoogleCalendar();
      });
    });
    container.querySelectorAll("[data-manage]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.manage === "google_calendar") openGoogleCalendarDrawer();
      });
    });

    await handleOAuthReturn();
  } catch (err) {
    container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load integrations</p><p>${esc(err.message)}</p></div>`;
  }
}
