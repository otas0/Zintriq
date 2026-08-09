/** Business OS — Feedback & Reputation Platform (QR surveys + internal feedback). */

import { statusBadge } from "../components/index.js";
import { showToast } from "../services/api.js";
import { PRODUCT_FLAGS } from "../product-focus.js";

function stars(rating) {
  if (!rating) return "—";
  return "★".repeat(Math.min(5, rating)) + "☆".repeat(Math.max(0, 5 - rating));
}

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

function sourceLabel(src) {
  return (src || "business_os").replace(/_/g, " ");
}

function renderDashboardStats(root, data) {
  root.innerHTML = `
    <section class="bos-dash-grid fb-bos-stats">
      <article class="bos-stat-card"><span class="bos-stat-val">${data.total ?? 0}</span><span class="bos-stat-lbl">Total feedback</span></article>
      <article class="bos-stat-card"><span class="bos-stat-val">${data.average_rating ?? 0}</span><span class="bos-stat-lbl">Avg rating</span></article>
      <article class="bos-stat-card"><span class="bos-stat-val">${data.response_rate ?? 0}%</span><span class="bos-stat-lbl">Response rate</span></article>
      <article class="bos-stat-card"><span class="bos-stat-val">${data.pending_requests ?? 0}</span><span class="bos-stat-lbl">Pending requests</span></article>
    </section>
    ${(data.by_source || []).length ? `
      <section class="bos-panel" style="margin-top:16px">
        <h3 class="bos-panel-title">By source</h3>
        <div class="bos-table-wrap">
          <table class="bos-table">
            <thead><tr><th>Source</th><th>Count</th><th>Avg rating</th></tr></thead>
            <tbody>${data.by_source.map((s) => `
              <tr><td>${sourceLabel(s.src)}</td><td>${s.c}</td><td>${s.avg_rating ?? "—"}</td></tr>`).join("")}
            </tbody>
          </table>
        </div>
      </section>` : ""}
  `;
}

function renderFeedbackTable(container, records, onSelect) {
  if (!records.length) {
    container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No feedback yet</p><p>Publish a QR survey to collect customer feedback.</p></div>`;
    return;
  }
  container.innerHTML = `
    <div class="bos-table-wrap">
      <table class="bos-table">
        <thead><tr><th>Rating</th><th>Comment</th><th>Source</th><th>Customer</th><th>Status</th><th>Date</th></tr></thead>
        <tbody>
          ${records.map((r) => `
            <tr data-id="${r.id}" class="bos-row-click">
              <td>${stars(r.rating)}</td>
              <td>${(r.content || r.comment || "—").slice(0, 60)}${(r.content || r.comment || "").length > 60 ? "…" : ""}</td>
              <td>${sourceLabel(r.source || r.source_type)}</td>
              <td>${r.customer_id ? `<a href="/app/contacts#contact/${r.customer_id}">${r.customer_name || "View"}</a>` : (r.customer_name || "—")}</td>
              <td>${statusBadge(r.status)}</td>
              <td>${(r.created_at || "").slice(0, 10)}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  container.querySelectorAll(".bos-row-click").forEach((row) => {
    row.addEventListener("click", () => onSelect(Number(row.dataset.id)));
  });
}

function renderDetail(panel, record) {
  panel.innerHTML = `
    <h3 class="bos-drawer-title">Feedback #${record.id}</h3>
    <p>${stars(record.rating)} · ${record.feedback_type} · ${sourceLabel(record.source || record.source_type)}</p>
    <p class="bos-drawer-body">${record.content || record.comment || "—"}</p>
    <p><strong>Contact:</strong> ${record.customer_id ? `<a href="/app/contacts#contact/${record.customer_id}">${record.customer_name || "View profile"}</a>` : (record.customer_name || "—")}</p>
    ${record.external_mapping ? `<p><strong>External:</strong> ${record.external_mapping.platform} · ${record.external_mapping.external_id}</p>` : ""}
    <h4 style="margin-top:20px">Activity</h4>
    <ul class="bos-timeline">${(record.activity || []).map((a) => `<li><strong>${a.action}</strong> · ${(a.created_at || "").slice(0, 16)}</li>`).join("") || "<li>No activity</li>"}</ul>
  `;
}

function renderSurveys(container, surveys, onPublish) {
  if (!surveys.length) {
    container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">No surveys</p><p>Create a survey to collect structured feedback via QR.</p></div>`;
    return;
  }
  container.innerHTML = `
    <div class="bos-table-wrap">
      <table class="bos-table">
        <thead><tr><th>Title</th><th>Status</th><th>QR code</th><th>Updated</th><th></th></tr></thead>
        <tbody>${surveys.map((s) => `
          <tr>
            <td>${s.title}</td>
            <td>${statusBadge(s.status)}</td>
            <td>${s.pub_code ? `<code>/survey/${s.pub_code}</code>` : "—"}</td>
            <td>${(s.updated_at || "").slice(0, 10)}</td>
            <td>${s.status === "draft" ? `<button type="button" class="bos-btn bos-btn-sm" data-publish="${s.id}">Publish</button>` : ""}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  container.querySelectorAll("[data-publish]").forEach((btn) => {
    btn.addEventListener("click", () => onPublish(Number(btn.dataset.publish)));
  });
}

function renderPlugins(container, plugins) {
  container.innerHTML = `
    <div class="bos-table-wrap">
      <table class="bos-table">
        <thead><tr><th>Platform</th><th>Status</th><th>Capabilities</th></tr></thead>
        <tbody>${plugins.map((p) => `
          <tr>
            <td>${p.name}</td>
            <td>${p.connected ? statusBadge("connected") : statusBadge("not_connected")}</td>
            <td>${(p.capabilities || []).join(", ")}</td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>
    <p class="bos-hint" style="margin-top:12px">Connect reputation platforms in Connected Apps to sync external reviews.</p>`;
}

/** @param {HTMLElement} root */
export async function mountFeedbackPage(root) {
  root.innerHTML = `<div class="bos-loading">Loading feedback…</div>`;
  try {
    const fetches = [
      fetchJson("/api/feedback/dashboard"),
      fetchJson("/api/feedback/workspace"),
      fetchJson("/api/surveys"),
    ];
    if (PRODUCT_FLAGS.reputationPlugins) fetches.push(fetchJson("/api/feedback/plugins"));
    const [dashboard, records, surveys, plugins] = await Promise.all(fetches);

    const showPlugins = PRODUCT_FLAGS.reputationPlugins;

    root.innerHTML = `
      <nav class="bos-tabs" id="fb-tabs">
        <button type="button" class="bos-tab active" data-tab="dashboard">Dashboard</button>
        <button type="button" class="bos-tab" data-tab="feedback">Feedback</button>
        <button type="button" class="bos-tab" data-tab="surveys">Surveys</button>
        ${showPlugins ? `<button type="button" class="bos-tab" data-tab="plugins">Platforms</button>` : ""}
      </nav>
      <div id="fb-tab-dashboard"></div>
      <section id="fb-tab-feedback" class="bos-panel hidden">
        <div class="bos-panel-head">
          <h2 class="bos-panel-title">All feedback</h2>
          <input type="search" class="bos-input bos-input-sm" id="fb-bos-search" placeholder="Search…" style="max-width:200px">
        </div>
        <div id="fb-bos-table"></div>
      </section>
      <section id="fb-tab-surveys" class="bos-panel hidden">
        <div class="bos-panel-head">
          <h2 class="bos-panel-title">Surveys</h2>
          <button type="button" class="bos-btn bos-btn-primary" id="fb-new-survey">New survey</button>
        </div>
        <div id="fb-surveys-list"></div>
      </section>
      ${showPlugins ? `<section id="fb-tab-plugins" class="bos-panel hidden">
        <h2 class="bos-panel-title">Reputation platforms</h2>
        <div id="fb-plugins-list"></div>
      </section>` : ""}
      <aside id="fb-bos-detail" class="bos-side-panel hidden"></aside>
    `;

    const dashEl = document.getElementById("fb-tab-dashboard");
    renderDashboardStats(dashEl, dashboard);

    const tableEl = document.getElementById("fb-bos-table");
    const detailEl = document.getElementById("fb-bos-detail");
    let allRecords = records;

    const refreshDetail = async (id) => {
      const record = await fetchJson(`/api/feedback/workspace/${id}`);
      detailEl.classList.remove("hidden");
      renderDetail(detailEl, record);
    };

    renderFeedbackTable(tableEl, allRecords, refreshDetail);

    document.getElementById("fb-bos-search")?.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      const filtered = allRecords.filter((r) =>
        (r.content || r.comment || "").toLowerCase().includes(q) ||
        (r.customer_name || "").toLowerCase().includes(q) ||
        sourceLabel(r.source).toLowerCase().includes(q)
      );
      renderFeedbackTable(tableEl, filtered, refreshDetail);
    });

    const surveysEl = document.getElementById("fb-surveys-list");
    const refreshSurveys = async () => {
      const list = await fetchJson("/api/surveys");
      renderSurveys(surveysEl, list, async (id) => {
        await fetchJson(`/api/surveys/${id}/publish`, { method: "POST", headers: { "Content-Type": "application/json" } });
        showToast("Survey published");
        refreshSurveys();
      });
    };
    renderSurveys(surveysEl, surveys, async (id) => {
      await fetchJson(`/api/surveys/${id}/publish`, { method: "POST", headers: { "Content-Type": "application/json" } });
      showToast("Survey published");
      refreshSurveys();
    });

    document.getElementById("fb-new-survey")?.addEventListener("click", async () => {
      const title = prompt("Survey title");
      if (!title?.trim()) return;
      await fetchJson("/api/surveys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          questions: [
            { type: "rating", question: "How would you rate your experience?", required: true, order: 0 },
            { type: "text", question: "Any additional comments?", required: false, order: 1 },
          ],
        }),
      });
      showToast("Survey created");
      refreshSurveys();
    });

    if (showPlugins && plugins) {
      renderPlugins(document.getElementById("fb-plugins-list"), plugins);
    }

    document.querySelectorAll("#fb-tabs .bos-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#fb-tabs .bos-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        ["dashboard", "feedback", "surveys", ...(showPlugins ? ["plugins"] : [])].forEach((name) => {
          const el = document.getElementById(`fb-tab-${name}`);
          if (el) el.classList.toggle("hidden", tab.dataset.tab !== name);
        });
        dashEl.classList.toggle("hidden", tab.dataset.tab !== "dashboard");
      });
    });
  } catch {
    root.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load feedback</p><p>Sign in, select a workspace, and ensure the server is running.</p></div>`;
  }
}
