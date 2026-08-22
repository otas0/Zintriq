/** Zintriq — Customers (QR-generated interactions only, not CRM). */

import { escapeHtml } from "../services/search.js";
import { fetchJson, wsQuery } from "../services/bos-api.js";
import { openDrawer } from "../services/api.js";
import {
  emptyState,
  loadingState,
  sectionHeader,
  button,
  setPageActions,
  renderFilterTabs,
  resourceRow,
} from "../components/index.js";

const INTERACTION_FILTERS = [
  { id: "", label: "All" },
  { id: "qr_scan", label: "QR Scan" },
  { id: "feedback_submitted", label: "Feedback" },
  { id: "survey_completed", label: "Survey" },
  { id: "booking_created", label: "Booking" },
  { id: "checkin_completed", label: "Check-in" },
];

const TYPE_LABELS = {
  qr_scan: "QR Scan",
  feedback_submitted: "Feedback",
  survey_completed: "Survey",
  booking_created: "Booking",
  checkin_completed: "Check-in",
};

function kindLabel(k) {
  return TYPE_LABELS[k] || String(k || "").replace(/_/g, " ");
}

function fmtTime(value) {
  if (!value) return "—";
  return String(value).slice(0, 16).replace("T", " ");
}

function statCards(dashboard) {
  const d = dashboard || {};
  return `<section class="bos-dash-grid" style="margin-bottom:20px">
    <article class="bos-stat-card"><span class="bos-stat-val">${d.total_customers ?? 0}</span><span class="bos-stat-lbl">Total customers</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${d.recent_interactions_7d ?? 0}</span><span class="bos-stat-lbl">Interactions (7d)</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${d.by_type?.feedback_submitted ?? 0}</span><span class="bos-stat-lbl">Feedback</span></article>
    <article class="bos-stat-card"><span class="bos-stat-val">${d.by_type?.booking_created ?? 0}</span><span class="bos-stat-lbl">Bookings</span></article>
  </section>`;
}

function renderPopularExperiences(items) {
  const list = items || [];
  if (!list.length) return `<p class="cp-muted">No QR activity yet.</p>`;
  return `<ul class="bos-action-list">
    ${list.map((x) => `
      <li class="bos-action-item">
        <div><strong>${escapeHtml(x.name)}</strong><br><span class="cp-muted">${x.interactions} interaction${x.interactions === 1 ? "" : "s"}</span></div>
        ${button({ variant: "ghost", label: "Manage", tag: "a", href: "/app/store#experiences", sm: true })}
      </li>`).join("")}
  </ul>`;
}

function renderRecentActivity(items) {
  const list = items || [];
  if (!list.length) return `<p class="cp-muted">No recent activity.</p>`;
  return `<ul class="bos-timeline">
    ${list.map((a) => `
      <li>
        <strong>${escapeHtml(kindLabel(a.interaction_type))}</strong>
        ${a.experience_name ? ` — ${escapeHtml(a.experience_name)}` : ""}
        <br><span class="cp-muted">${escapeHtml(a.full_name || a.email || "Anonymous")} · ${fmtTime(a.created_at)}</span>
      </li>`).join("")}
  </ul>`;
}

function renderCustomerDrawer(customer) {
  const sources = customer.qr_sources || [];
  openDrawer(customer.name || "Customer", `
    <div class="cp-profile">
      ${customer.anonymous ? `<p class="cp-muted" style="margin-bottom:12px">Anonymous guest</p>` : ""}
      <dl class="cp-meta">
        <dt>Email</dt><dd>${escapeHtml(customer.email || "—")}</dd>
        <dt>Phone</dt><dd>${escapeHtml(customer.phone || "—")}</dd>
        <dt>Last activity</dt><dd>${fmtTime(customer.last_activity_at)}</dd>
      </dl>

      ${sources.length ? `
        <h4 class="bos-drawer-section">QR Sources</h4>
        <ul class="bos-timeline">
          ${sources.map((s) => `
            <li><strong>${escapeHtml(s.name)}</strong><br>
              <span class="cp-muted">${(s.actions || []).map(kindLabel).join(", ") || "—"}</span>
            </li>`).join("")}
        </ul>` : ""}

      <h4 class="bos-drawer-section">Activity Timeline</h4>
      <ul class="bos-timeline">
        ${(customer.timeline || []).slice(0, 20).map((a) => `
          <li><strong>${escapeHtml(a.title || kindLabel(a.activity_type))}</strong>
            ${a.detail ? `<br><span class="cp-muted">${escapeHtml(a.detail)}</span>` : ""}
            <br><span class="cp-muted">${fmtTime(a.created_at)}</span>
          </li>`).join("") || "<li>No activity yet</li>"}
      </ul>

      <h4 class="bos-drawer-section">Interactions</h4>
      <ul class="bos-timeline">
        ${(customer.interactions || []).slice(0, 15).map((i) => `
          <li><strong>${escapeHtml(kindLabel(i.interaction_type))}</strong>
            ${i.experience_name ? ` — ${escapeHtml(i.experience_name)}` : ""}
            <br><span class="cp-muted">${fmtTime(i.created_at)}</span>
          </li>`).join("") || "<li>No interactions</li>"}
      </ul>

      ${(customer.feedback || []).length ? `
        <h4 class="bos-drawer-section">Responses</h4>
        <ul class="bos-timeline">
          ${customer.feedback.map((f) => `
            <li>${"★".repeat(f.rating || 0)} ${escapeHtml((f.comment || "").slice(0, 120))}
              <br><span class="cp-muted">${escapeHtml(f.store_name || "")} · ${fmtTime(f.created_at)}</span>
            </li>`).join("")}
        </ul>` : ""}

      ${(customer.bookings || []).length ? `
        <h4 class="bos-drawer-section">Bookings</h4>
        <ul class="bos-timeline">
          ${customer.bookings.map((b) => `
            <li><strong>${escapeHtml(b.title || "Booking")}</strong>
              ${b.experience_name ? ` · ${escapeHtml(b.experience_name)}` : ""}
              <br><span class="cp-muted">${fmtTime(b.starts_at)} · ${escapeHtml(b.status || "")}</span>
            </li>`).join("")}
        </ul>` : ""}

      ${(customer.checkins || []).length ? `
        <h4 class="bos-drawer-section">Check-ins</h4>
        <ul class="bos-timeline">
          ${customer.checkins.map((c) => `
            <li><strong>${escapeHtml(c.customer_name || "Check-in")}</strong>
              ${c.experience_name ? ` · ${escapeHtml(c.experience_name)}` : ""}
              <br><span class="cp-muted">${fmtTime(c.checked_in_at)}</span>
            </li>`).join("")}
        </ul>` : ""}
    </div>
  `);
}

/** @param {HTMLElement} root */
export async function mountCustomersPage(root) {
  root.innerHTML = loadingState();
  setPageActions(button({ variant: "primary", label: "Customer QR", tag: "a", href: "/app/store#experiences", sm: true }));

  let filterType = "";
  let searchQ = "";

  const load = async () => {
    const qParams = new URLSearchParams(wsQuery().replace(/^\?/, ""));
    if (searchQ.trim()) qParams.set("q", searchQ.trim());
    if (filterType) qParams.set("type", filterType);
    const listQuery = qParams.toString() ? `?${qParams}` : wsQuery();

    const [dashboard, qrCustomers, interactions] = await Promise.all([
      fetchJson(`/api/customers/qr/dashboard${wsQuery()}`).catch(() => ({})),
      fetchJson(`/api/customers/qr${listQuery}`).catch(() => ({ customers: [] })),
      fetchJson(`/api/interactions/summary${wsQuery()}`).catch(() => ({ feedback: [], counts: {} })),
    ]);
    const customers = qrCustomers.customers || [];
    const feedback = interactions.feedback || [];

    root.innerHTML = `
      ${statCards(dashboard)}

      <div class="bos-panel-grid" style="margin-bottom:20px;display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <section class="bos-panel">
          ${sectionHeader({ title: "Popular landing pages" })}
          ${renderPopularExperiences(dashboard.popular_experiences)}
        </section>
        <section class="bos-panel">
          ${sectionHeader({ title: "Recent activity" })}
          ${renderRecentActivity(dashboard.recent_activity)}
        </section>
      </div>

      <section class="bos-panel" style="margin-bottom:20px">
        ${sectionHeader({
          title: "Customers",
          actionsHtml: `<span class="cp-muted" style="font-size:13px">${customers.length} from QR</span>`,
        })}
        <div class="bos-toolbar-inline" style="margin-bottom:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center">
          <input type="search" class="bos-input" id="qr-cust-search" placeholder="Search name, email, phone, QR…" value="${escapeHtml(searchQ)}" style="max-width:280px">
          <div id="qr-cust-filters"></div>
        </div>
        <div id="qr-cust-list">
          ${customers.length ? customers.map((c) => resourceRow({
            id: c.id,
            title: c.name,
            status: c.anonymous ? "draft" : "active",
            meta: `${c.interactions} interaction${c.interactions === 1 ? "" : "s"} · ${(c.kinds || []).map(kindLabel).join(", ") || "—"} · ${fmtTime(c.last_activity)}`,
            actionsHtml: button({ variant: "ghost", label: "View", attrs: `data-open-customer="${c.id}"`, sm: true }),
          })).join("") : emptyState({
            title: "No customer interactions yet",
            text: "When customers scan your QR codes and leave feedback, book, or check in, they appear here.",
            actionHtml: button({ variant: "primary", label: "Customer QR", tag: "a", href: "/app/store#experiences" }),
          })}
        </div>
      </section>

      <section class="bos-panel" id="responses">
        ${sectionHeader({
          title: "Recent responses",
          actionsHtml: `${interactions.counts?.new_feedback ? `<span class="bos-badge bos-badge--needs_attention">${interactions.counts.new_feedback} new</span>` : ""}
            ${button({ variant: "ghost", label: "All feedback", tag: "a", href: "/app/feedback", sm: true })}`,
        })}
        ${feedback.length ? `
          <ul class="bos-action-list">
            ${feedback.slice(0, 8).map((f) => `
              <li class="bos-action-item">
                <div>
                  <strong>${"★".repeat(f.rating || 0)}</strong>
                  <span class="cp-muted" style="margin-left:8px">${escapeHtml((f.comment || "").slice(0, 80))}</span>
                </div>
                ${button({ variant: "primary", label: "View response", tag: "a", href: "/app/feedback", sm: true })}
              </li>`).join("")}
          </ul>` : `<p class="cp-muted">No responses yet.</p>`}
      </section>`;

    renderFilterTabs(
      root.querySelector("#qr-cust-filters"),
      INTERACTION_FILTERS,
      filterType,
      (id) => {
        filterType = id;
        load().catch((err) => {
          root.innerHTML = emptyState({ title: "Could not load customers", text: err.message });
        });
      },
    );

    root.querySelector("#qr-cust-search")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        searchQ = e.target.value || "";
        load().catch((err) => {
          root.innerHTML = emptyState({ title: "Could not load customers", text: err.message });
        });
      }
    });

    root.querySelectorAll("[data-open-customer]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const id = btn.getAttribute("data-open-customer");
        try {
          const detail = await fetchJson(`/api/customers/qr/${id}${wsQuery()}`);
          renderCustomerDrawer(detail);
        } catch (err) {
          openDrawer("Customer", emptyState({ title: "Could not load customer", text: err.message }));
        }
      });
    });

    root.querySelectorAll(".bos-resource-row[data-id]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        row.querySelector("[data-open-customer]")?.click();
      });
    });
  };

  try {
    await load();
  } catch (err) {
    root.innerHTML = emptyState({ title: "Could not load customers", text: err.message });
  }
}
