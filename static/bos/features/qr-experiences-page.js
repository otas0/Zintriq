/** Business OS — Experience Builder */

import { statusBadge, emptyState, loadingState, button, setPageActions, renderFilterTabs, resourceRow, qrExperienceCard, pageHeader, QRPreview } from "../components/index.js";
import { notifySuccess, notifyError } from "../services/notify.js";
import { showToast, apiPost, renderActionBar } from "../services/api.js";
import { MVP_FLAGS } from "../product-focus.js";
import { CUSTOMER_QR_TYPES } from "../customer-qr-types.js";

const MVP_BLOCK_TYPES = [
  { id: "text", label: "Text" },
  { id: "header", label: "Text" },
  { id: "image", label: "Image" },
  { id: "actions", label: "Button" },
  { id: "info", label: "Text" },
  { id: "survey", label: "Survey" },
];

/** Unique labels for the editor "Add block" dropdown (spec: Text, Image, Button, Feedback, Survey). */
const MVP_EDITOR_ADD_OPTIONS = [
  { id: "text", label: "Text" },
  { id: "image", label: "Image" },
  { id: "actions", label: "Button" },
  { id: "survey", label: "Feedback", preset: { title: "Share your feedback", body: "Rate your experience" } },
  { id: "survey", label: "Survey", preset: { title: "Quick survey", body: "Answer a few questions" } },
];

const MVP_QR_TYPES = CUSTOMER_QR_TYPES;

const FULL_BLOCK_TYPES = [
  ...MVP_BLOCK_TYPES,
  { id: "booking", label: "Booking" },
  { id: "check_in", label: "Check-in" },
  { id: "contact", label: "Contact" },
];

const BLOCK_TYPES = MVP_FLAGS.deferredActions ? FULL_BLOCK_TYPES : MVP_BLOCK_TYPES;

const MVP_ACTION_TYPES = [
  { id: "open_page", label: "Open Page" },
  { id: "start_survey", label: "Start Survey / Feedback" },
  { id: "show_information", label: "Show Information" },
];

const FULL_ACTION_TYPES = [
  ...MVP_ACTION_TYPES,
  { id: "create_booking", label: "Create Booking" },
  { id: "start_checkin", label: "Start Check-in" },
];

const ACTION_TYPES = MVP_FLAGS.deferredActions ? FULL_ACTION_TYPES : MVP_ACTION_TYPES;

const DEFERRED_TEMPLATE_IDS = new Set(["check_in_only", "event", "service", "hospitality"]);

const DETAIL_TABS = [
  ["overview", "Overview"],
  ["preview", "Preview"],
  ["qr-codes", "QR Codes"],
  ["responses", "Responses"],
  ["settings", "Settings"],
  ...(MVP_FLAGS.workflowEngine ? [["flow", "Customer Flow"]] : []),
  ...(MVP_FLAGS.advancedAnalytics ? [["analytics", "Analytics"]] : []),
];

const WORKFLOW_STEP_TYPES = [
  { id: "display_content", label: "Display Content" },
  { id: "customer_input", label: "Customer Input" },
  { id: "survey", label: "Survey" },
  { id: "feedback", label: "Feedback" },
  { id: "booking", label: "Booking" },
  { id: "check_in", label: "Check-in" },
];

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed (${res.status})`);
  }
  return res.json();
}

function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  return { "Content-Type": "application/json", "X-CSRF-Token": token };
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function flowLabel(flow) {
  if (!flow?.length) return "—";
  return flow.map((s) => s.label).join(" → ");
}

function connectedLabel(features) {
  if (!features?.length) return "—";
  const map = { booking: "Booking", feedback: "Feedback", checkin: "Check-in" };
  return features.map((f) => map[f] || f).join(", ");
}

const BATCH_ACTIONS = [
  { action: "archive", label: "Archive" },
  { action: "activate", label: "Activate" },
  { action: "duplicate", label: "Duplicate" },
  { action: "export", label: "Export" },
  { action: "delete", label: "Delete", variant: "danger" },
];

function filterExperiences(rows, filter) {
  return rows.filter((r) => {
    const status = r.status === "paused" ? "active" : r.status;
    if (filter === "all") return status !== "archived";
    if (filter === "archived") return status === "archived";
    return status === filter || r.status === filter;
  });
}

function renderExperienceList(container, rows, filter, { onSelect, onAction, selected }) {
  const filtered = filterExperiences(rows, filter);
  if (!filtered.length) {
    container.innerHTML = emptyState({
      title: filter === "archived" ? "No archived customer QR" : "Add your first customer QR",
      text: filter === "archived" ? "" : "Pick a type — restaurant, clinic, feedback — then go live.",
      actionHtml: filter !== "archived" ? button({ variant: "primary", label: "Add customer QR", id: "qrx-empty-create" }) : "",
    });
    container.querySelector("#qrx-empty-create")?.addEventListener("click", () => onAction("create"));
    return filtered;
  }
  container.innerHTML = `<div class="merchant-grid qrx-grid">${filtered.map((r) => {
    const item = { ...r, status: r.status === "paused" ? "active" : r.status };
    const isSelected = selected.has(r.id);
    return `<div class="merchant-qr-card-wrap qrx-card-wrap${isSelected ? " is-selected" : ""}" data-id="${r.id}">
      <label class="qrx-row-check" onclick="event.stopPropagation()">
        <input type="checkbox" class="qrx-select" data-id="${r.id}"${isSelected ? " checked" : ""} aria-label="Select ${escapeHtml(r.name)}">
      </label>
      ${qrExperienceCard(item)}
    </div>`;
  }).join("")}</div>`;

  container.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      onAction(btn.dataset.act, Number(btn.dataset.id));
    });
  });
  container.querySelectorAll(".qrx-select").forEach((input) => {
    input.addEventListener("change", (e) => {
      e.stopPropagation();
      onAction("toggle-select", Number(input.dataset.id), { checked: input.checked });
    });
  });
  container.querySelectorAll(".qrx-card-wrap").forEach((wrap) => {
    wrap.addEventListener("click", (e) => {
      if (e.target.closest("button, label, input, a")) return;
      onSelect(Number(wrap.dataset.id));
    });
  });
  return filtered;
}

function renderLandingPreview(host, payload, mode = "mobile") {
  if (!host) return;
  host.innerHTML = QRPreview(payload, { mode });
}

function paintBlocksInBuilder(body, draft) {
  const list = body.querySelector("#qxb-blocks");
  if (!list) return;
  list.innerHTML = draft.blocks.map((b, i) => {
    const c = b.content || {};
    return `
      <div class="bos-subpanel bos-subpanel--compact" data-bi="${i}">
        <div style="display:flex;justify-content:space-between;gap:4px;margin-bottom:6px">
          <strong style="font-size:12px">${escapeHtml(BLOCK_TYPES.find((t) => t.id === b.type)?.label || b.type)}</strong>
          <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" data-rm="${i}">×</button>
        </div>
        ${b.type === "header" ? `<input class="bos-input bos-input-sm" data-f="title" data-i="${i}" value="${escapeHtml(c.title || "")}" placeholder="Title">` : ""}
        ${b.type === "text" || b.type === "info" ? `<textarea class="bos-input bos-input-sm" data-f="body" data-i="${i}" rows="2">${escapeHtml(c.body || c.title || "")}</textarea>` : ""}
      </div>`;
  }).join("") || `<p class="cp-muted" style="font-size:12px">No blocks</p>`;
  list.querySelectorAll("[data-f]").forEach((el) => {
    el.addEventListener("input", () => {
      const i = Number(el.dataset.i);
      draft.blocks[i].content = draft.blocks[i].content || {};
      draft.blocks[i].content[el.dataset.f] = el.value;
      renderLandingPreview(body.querySelector("#qxb-preview-host"), { ...draft, name: draft.name, blocks: draft.blocks, actions: draft.actions, branding: draft.branding }, "mobile");
    });
  });
  list.querySelectorAll("[data-rm]").forEach((btn) => {
    btn.addEventListener("click", () => {
      draft.blocks.splice(Number(btn.dataset.rm), 1);
      paintBlocksInBuilder(body, draft);
      renderLandingPreview(body.querySelector("#qxb-preview-host"), { ...draft, name: draft.name, blocks: draft.blocks, actions: draft.actions, branding: draft.branding }, "mobile");
    });
  });
}

function paintActionsInBuilder(body, draft) {
  const list = body.querySelector("#qxb-actions");
  if (!list) return;
  list.innerHTML = draft.actions.map((a, i) => `
    <div class="bos-subpanel bos-subpanel--compact">
      <input class="bos-input bos-input-sm" data-af="label" data-i="${i}" value="${escapeHtml(a.label || "")}">
    </div>`).join("") || `<p class="cp-muted" style="font-size:12px">No actions</p>`;
  list.querySelectorAll("[data-af]").forEach((el) => {
    el.addEventListener("input", () => { draft.actions[Number(el.dataset.i)].label = el.value; });
  });
}

/** Full Experience Builder — Shopify-style 3-column editor */
function openBuilder(exp, { onClose, onSaved }) {
  let tab = "edit";
  let draft = {
    name: exp.name || "",
    description: exp.description || "",
    branding: {
      business_name: exp.branding?.business_name || "",
      logo_url: exp.branding?.logo_url || "",
      background: exp.branding?.background || "",
      theme: exp.branding?.theme || "light",
      language: exp.branding?.language || "en",
    },
    blocks: (exp.blocks || []).map((b) => ({ ...b, content: { ...(b.content || {}) } })),
    actions: (exp.actions || []).map((a) => ({
      ...a,
      configuration: { ...(a.configuration || {}) },
    })),
  };
  let previewMode = "mobile";
  let previewPayload = null;

  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay";

  const saveSettings = async () => {
    await fetchJson(`/api/qr-experiences/${exp.id}`, {
      method: "PATCH",
      headers: csrfHeaders(),
      body: JSON.stringify({
        name: draft.name,
        description: draft.description,
        branding: draft.branding,
      }),
    });
  };

  const saveBlocks = async () => {
    await fetchJson(`/api/qr-experiences/${exp.id}/blocks`, {
      method: "PUT",
      headers: csrfHeaders(),
      body: JSON.stringify({
        blocks: draft.blocks.map((b, i) => ({
          type: b.type,
          content: b.content || {},
          order: i,
        })),
      }),
    });
  };

  const saveActions = async () => {
    const res = await fetchJson(`/api/qr-experiences/${exp.id}/actions`, {
      method: "PUT",
      headers: csrfHeaders(),
      body: JSON.stringify({
        actions: draft.actions.map((a, i) => ({
          type: a.type,
          label: a.label,
          configuration: a.configuration || {},
          order: i,
        })),
      }),
    });
    draft.actions = res.actions || draft.actions;
  };

  const loadPreview = async () => {
    previewPayload = await fetchJson(`/api/qr-experiences/${exp.id}/preview`);
  };

  const paint = async () => {
    const tabs = [["edit", "Edit Experience"], ["publish", "Publish"]];
    overlay.innerHTML = `
      <div class="bos-modal bos-modal--wide">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:start">
          <div>
            <h2 class="bos-panel-title" style="margin:0">${escapeHtml(draft.name)}</h2>
            <p class="cp-muted" style="margin:4px 0 0">Experience Builder · ${statusBadge(exp.status)}</p>
          </div>
          <button type="button" class="bos-btn bos-btn-ghost" id="qxb-close">Close</button>
        </div>
        <nav class="bos-subnav" style="margin:16px 0">
          ${tabs.map(([id, label]) =>
            `<button type="button" class="bos-subnav__item${tab === id ? " is-active" : ""}" data-tab="${id}">${label}</button>`
          ).join("")}
        </nav>
        <div id="qxb-body"></div>
        <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end;flex-wrap:wrap">
          ${tab === "edit" ? `<button type="button" class="bos-btn bos-btn-primary" id="qxb-save">Save changes</button>` : ""}
          ${tab === "publish" && exp.status !== "active" ? `<button type="button" class="bos-btn bos-btn-primary" id="qxb-publish">Publish</button>` : ""}
        </div>
      </div>`;

    const body = overlay.querySelector("#qxb-body");

    if (tab === "edit") {
      body.innerHTML = `
        <div class="bos-builder-grid">
          <aside class="bos-builder-col">
            <h4 class="bos-builder-col__title">Components</h4>
            <div id="qxb-blocks"></div>
            <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
              <select class="bos-input bos-input-sm" id="qxb-add-type">
                ${(MVP_FLAGS.deferredActions ? BLOCK_TYPES : MVP_EDITOR_ADD_OPTIONS).map((t) => `<option value="${t.id}">${t.label}</option>`).join("")}
              </select>
              <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="qxb-add-block">Add</button>
            </div>
            <h4 class="bos-builder-col__title" style="margin-top:20px">Actions</h4>
            <div id="qxb-actions"></div>
          </aside>
          <main class="bos-builder-col bos-builder-col--preview">
            <h4 class="bos-builder-col__title">Customer preview</h4>
            <div id="qxb-preview-host"><p class="cp-muted">Loading…</p></div>
          </main>
          <aside class="bos-builder-col">
            <h4 class="bos-builder-col__title">Settings</h4>
            <div class="bos-field"><label class="bos-label">Name</label>
              <input class="bos-input" id="qxb-name" value="${escapeHtml(draft.name)}"></div>
            <div class="bos-field" style="margin-top:10px"><label class="bos-label">Description</label>
              <textarea class="bos-input" id="qxb-desc" rows="2">${escapeHtml(draft.description)}</textarea></div>
            <div class="bos-field" style="margin-top:10px"><label class="bos-label">Business name</label>
              <input class="bos-input" id="qxb-biz" value="${escapeHtml(draft.branding.business_name)}"></div>
            <div class="bos-field" style="margin-top:10px"><label class="bos-label">Logo URL</label>
              <input class="bos-input" id="qxb-logo" value="${escapeHtml(draft.branding.logo_url)}"></div>
            <div class="bos-field" style="margin-top:10px"><label class="bos-label">Background</label>
              <input class="bos-input" id="qxb-bg" value="${escapeHtml(draft.branding.background)}"></div>
          </aside>
        </div>`;
      await loadPreview();
      renderLandingPreview(body.querySelector("#qxb-preview-host"), previewPayload || { ...draft, name: draft.name, blocks: draft.blocks, actions: draft.actions, branding: draft.branding }, "mobile");
      paintBlocksInBuilder(body, draft);
      paintActionsInBuilder(body, draft);
      body.querySelector("#qxb-add-block")?.addEventListener("click", () => {
        const sel = body.querySelector("#qxb-add-type");
        const idx = sel?.selectedIndex ?? 0;
        const opts = MVP_FLAGS.deferredActions ? BLOCK_TYPES : MVP_EDITOR_ADD_OPTIONS;
        const pick = opts[idx] || opts[0];
        const content = pick.preset ? { title: pick.preset.title, body: pick.preset.body } : {};
        draft.blocks.push({ type: pick.id, content });
        paintBlocksInBuilder(body, draft);
        renderLandingPreview(body.querySelector("#qxb-preview-host"), { ...draft, name: draft.name, blocks: draft.blocks, actions: draft.actions, branding: draft.branding }, "mobile");
      });
    }

    if (tab === "publish") {
      body.innerHTML = `
        <p>Publishing makes your experience live for customers and generates QR codes.</p>
        <ul style="margin:12px 0;padding-left:18px;font-size:14px" class="cp-muted">
          <li>Name: ${escapeHtml(draft.name)}</li>
          <li>Blocks: ${draft.blocks.length} · Actions: ${draft.actions.length}</li>
          <li>Status: ${escapeHtml(exp.status)}</li>
        </ul>
        ${exp.status === "active" ? `
          <div style="text-align:center;margin-top:16px">
            ${exp.qr_image ? `<img src="${exp.qr_image}" alt="QR" width="160" height="160" style="border:1px solid var(--color-border);border-radius:8px;background:#fff">` : ""}
            <p style="margin:10px 0 0"><code>${escapeHtml(exp.public_url || exp.landing_url || "")}</code></p>
          </div>` : `<p class="cp-muted">Save changes in Edit, then publish.</p>`}`;
    }

    overlay.querySelector("#qxb-close").addEventListener("click", () => {
      overlay.remove();
      onClose?.();
    });
    overlay.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        tab = btn.dataset.tab;
        await paint();
      });
    });
    overlay.querySelector("#qxb-save")?.addEventListener("click", async () => {
      try {
        if (tab === "edit") {
          draft.name = overlay.querySelector("#qxb-name")?.value.trim() || draft.name;
          draft.description = overlay.querySelector("#qxb-desc")?.value.trim() || "";
          draft.branding.business_name = overlay.querySelector("#qxb-biz")?.value.trim() || "";
          draft.branding.logo_url = overlay.querySelector("#qxb-logo")?.value.trim() || "";
          draft.branding.background = overlay.querySelector("#qxb-bg")?.value.trim() || "";
          await saveSettings();
          await saveBlocks();
          await saveActions();
        }
        showToast("Saved", { type: "success" });
        const updated = await fetchJson(`/api/qr-experiences/${exp.id}`);
        Object.assign(exp, updated);
        onSaved?.(updated);
      } catch (err) {
        showToast(err.message);
      }
    });
    overlay.querySelector("#qxb-publish")?.addEventListener("click", async () => {
      try {
        await saveSettings();
        await saveBlocks();
        await saveActions();
        const published = await fetchJson(`/api/qr-experiences/${exp.id}/publish`, {
          method: "POST", headers: csrfHeaders(), body: "{}",
        });
        Object.assign(exp, published);
        notifySuccess("Experience published");
        tab = "publish";
        onSaved?.(published);
        await paint();
      } catch (err) {
        showToast(err.message);
      }
    });
  };

  document.body.appendChild(overlay);
  paint();
}

function stepTypeLabel(type) {
  return WORKFLOW_STEP_TYPES.find((t) => t.id === type)?.label || type;
}

/** Visual workflow editor — Steps | Canvas | Settings */
function openWorkflowEditor(exp, { onClose, onSaved }) {
  let workflow = null;
  let draftSteps = [];

  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay";

  const load = async () => {
    workflow = await fetchJson(`/api/qr-experiences/${exp.id}/workflow`);
    draftSteps = (workflow.steps || []).map((s) => ({ ...s, config: { ...(s.config || {}) } }));
    paint();
  };

  const paint = () => {
    overlay.innerHTML = `
      <div class="bos-modal bos-modal--wide">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:start">
          <div>
            <h2 class="bos-panel-title" style="margin:0">Customer Workflow</h2>
            <p class="cp-muted" style="margin:4px 0 0">${escapeHtml(exp.name)} · Trigger: QR Scanned · ${statusBadge(workflow?.status || "draft")}</p>
          </div>
          <button type="button" class="bos-btn bos-btn-ghost" id="qwf-close">Close</button>
        </div>
        <div class="bos-builder-grid" style="margin-top:16px">
          <aside class="bos-builder-col">
            <h4 class="bos-builder-col__title">Steps</h4>
            <div id="qwf-steps">${draftSteps.map((s, i) => `
              <div class="bos-subpanel bos-subpanel--compact" data-wi="${i}" style="cursor:pointer;margin-bottom:6px">
                <strong style="font-size:12px">${i + 1}. ${escapeHtml(s.label)}</strong>
                <p class="cp-muted" style="margin:2px 0 0;font-size:11px">${escapeHtml(stepTypeLabel(s.type))}</p>
              </div>`).join("") || `<p class="cp-muted" style="font-size:12px">No steps</p>`}
            </div>
            <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">
              <select class="bos-input bos-input-sm" id="qwf-add-type">
                ${WORKFLOW_STEP_TYPES.map((t) => `<option value="${t.id}">${t.label}</option>`).join("")}
              </select>
              <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="qwf-add">Add</button>
            </div>
          </aside>
          <main class="bos-builder-col bos-builder-col--preview">
            <h4 class="bos-builder-col__title">Workflow canvas</h4>
            <ol style="margin:0;padding-left:20px;font-size:14px">
              ${draftSteps.map((s, i) => `
                <li style="margin-bottom:12px;padding:10px;border:1px solid var(--color-border);border-radius:8px;list-style-position:outside">
                  <strong>${escapeHtml(s.label)}</strong>
                  <span class="cp-muted" style="margin-left:8px;font-size:12px">${escapeHtml(stepTypeLabel(s.type))}</span>
                  ${i < draftSteps.length - 1 ? `<p class="cp-muted" style="margin:8px 0 0;font-size:18px;text-align:center">↓</p>` : ""}
                </li>`).join("") || `<li class="cp-muted">Add steps to define the customer journey</li>`}
            </ol>
          </main>
          <aside class="bos-builder-col">
            <h4 class="bos-builder-col__title">Settings</h4>
            <div class="bos-field"><label class="bos-label">Workflow name</label>
              <input class="bos-input" id="qwf-name" value="${escapeHtml(workflow?.name || "")}"></div>
            <p class="cp-muted" style="font-size:12px;margin-top:12px">Publish the workflow to activate it when customers scan this experience.</p>
          </aside>
        </div>
        <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end;flex-wrap:wrap">
          <button type="button" class="bos-btn bos-btn-ghost" id="qwf-preview">Preview journey</button>
          ${workflow?.status !== "active" ? `<button type="button" class="bos-btn bos-btn-primary" id="qwf-publish">Publish workflow</button>` : `<button type="button" class="bos-btn bos-btn-ghost" id="qwf-pause">Pause workflow</button>`}
          <button type="button" class="bos-btn bos-btn-primary" id="qwf-save">Save workflow</button>
        </div>
      </div>`;

    overlay.querySelector("#qwf-close")?.addEventListener("click", () => { overlay.remove(); onClose?.(); });
    overlay.querySelector("#qwf-add")?.addEventListener("click", () => {
      const type = overlay.querySelector("#qwf-add-type").value;
      draftSteps.push({ id: `step_${Date.now()}`, type, label: stepTypeLabel(type), config: {}, order: draftSteps.length });
      paint();
    });
    overlay.querySelector("#qwf-save")?.addEventListener("click", async () => {
      try {
        const name = overlay.querySelector("#qwf-name")?.value.trim() || workflow?.name;
        workflow = await fetchJson(`/api/qr-experiences/${exp.id}/workflow`, {
          method: "PUT", headers: csrfHeaders(),
          body: JSON.stringify({ name, steps: draftSteps }),
        });
        notifySuccess("Workflow saved");
        onSaved?.(workflow);
        paint();
      } catch (err) { notifyError(err.message); }
    });
    overlay.querySelector("#qwf-publish")?.addEventListener("click", async () => {
      try {
        await fetchJson(`/api/qr-experiences/${exp.id}/workflow`, {
          method: "PUT", headers: csrfHeaders(),
          body: JSON.stringify({ name: workflow?.name, steps: draftSteps }),
        });
        workflow = await fetchJson(`/api/qr-experiences/${exp.id}/workflow/publish`, { method: "POST", headers: csrfHeaders(), body: "{}" });
        notifySuccess("Workflow published");
        onSaved?.(workflow);
        paint();
      } catch (err) { notifyError(err.message); }
    });
    overlay.querySelector("#qwf-pause")?.addEventListener("click", async () => {
      try {
        workflow = await fetchJson(`/api/qr-experiences/${exp.id}/workflow/pause`, { method: "POST", headers: csrfHeaders(), body: "{}" });
        notifySuccess("Workflow paused");
        onSaved?.(workflow);
        paint();
      } catch (err) { notifyError(err.message); }
    });
    overlay.querySelector("#qwf-preview")?.addEventListener("click", async () => {
      try {
        const preview = await fetchJson(`/api/qr-experiences/${exp.id}/workflow/preview`);
        showToast(`Journey: ${preview.journey.map((j) => j.label).join(" → ")}`, { type: "info" });
      } catch (err) { notifyError(err.message); }
    });
  };

  document.body.appendChild(overlay);
  load().catch((err) => { notifyError(err.message); overlay.remove(); });
}

function pct(n) {
  return `${Number(n ?? 0).toFixed(1)}%`;
}

function renderFlowFunnel(flow) {
  if (!flow?.length) return "<p class='cp-muted'>No flow data yet — publish and share your QR.</p>";
  return `<ol style="margin:0;padding-left:18px;font-size:13px;line-height:1.8">
    ${flow.map((s) => `<li><strong>${escapeHtml(s.label)}</strong> — ${s.count}</li>`).join("")}
  </ol>`;
}

function renderDropOffs(items) {
  if (!items?.length) return "<p class='cp-muted'>No action drop-offs recorded yet.</p>";
  return `<ul style="margin:0;padding-left:18px;font-size:13px">
    ${items.map((d) =>
      `<li><strong>${escapeHtml(d.action)}</strong>: ${d.started} started → ${d.completed} completed · <span class="cp-muted">drop-off ${d.drop_off}</span></li>`
    ).join("")}
  </ul>`;
}

async function renderAnalyticsDashboard(container, period = "30d", onSelectExperience) {
  container.innerHTML = `<p class="cp-muted">Loading analytics…</p>`;
  try {
    const data = await fetchJson(`/api/qr-experiences/analytics/dashboard?period=${period}`);
    const o = data.overview || {};
    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px">
        <h2 class="bos-panel-title" style="margin:0">Experience Analytics</h2>
        <select class="bos-input" id="qrx-analytics-period" style="max-width:160px">
          <option value="today" ${period === "today" ? "selected" : ""}>Today</option>
          <option value="7d" ${period === "7d" ? "selected" : ""}>Last 7 days</option>
          <option value="30d" ${period === "30d" ? "selected" : ""}>Last 30 days</option>
          <option value="all" ${period === "all" ? "selected" : ""}>All time</option>
        </select>
      </div>
      <section class="bos-dash-grid" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr))">
        <article class="bos-stat-card"><span class="bos-stat-val">${o.total_scans ?? 0}</span><span class="bos-stat-lbl">Total Scans</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${o.unique_visitors ?? 0}</span><span class="bos-stat-lbl">Unique Visitors</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${o.completed_actions ?? 0}</span><span class="bos-stat-lbl">Completed</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${pct(o.conversion_rate)}</span><span class="bos-stat-lbl">Conversion</span></article>
      </section>
      <h3 style="margin:20px 0 8px;font-size:14px">Experience Performance</h3>
      ${(data.performance || []).length ? `
        <div style="display:flex;flex-direction:column;gap:8px">
          ${data.performance.map((p) => `
            <button type="button" class="bos-subpanel" data-exp-id="${p.id}" style="cursor:pointer;text-align:left;width:100%">
              <strong>${escapeHtml(p.name)}</strong>
              <p class="cp-muted" style="margin:4px 0 0;font-size:12px">
                ${p.scans} scans · ${p.completed_actions} completed · ${pct(p.conversion_rate)} conversion
                ${p.survey_completed ? ` · ${p.survey_completed} feedback` : ""}
                ${p.checkin_completed ? ` · ${p.checkin_completed} check-ins` : ""}
                ${p.booking_completed ? ` · ${p.booking_completed} bookings` : ""}
              </p>
            </button>`).join("")}
        </div>` : `<p class="cp-muted">No published experiences with scan data yet.</p>`}
      ${(data.template_usage || []).length ? `
        <h3 style="margin:20px 0 8px;font-size:14px">Template Performance</h3>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${data.template_usage.map((t) => `
            <div class="bos-subpanel" style="text-align:left">
              <strong>${escapeHtml(t.template_name)}</strong>
              <span class="cp-muted" style="font-size:12px;margin-left:8px">${escapeHtml(t.category || "")}</span>
              <p class="cp-muted" style="margin:4px 0 0;font-size:12px">
                ${t.experiences_created} created · ${t.total_scans} scans · ${t.completed_actions} interactions
              </p>
            </div>`).join("")}
        </div>` : ""}
    `;
    container.querySelector("#qrx-analytics-period")?.addEventListener("change", (e) => {
      renderAnalyticsDashboard(container, e.target.value, onSelectExperience);
    });
    container.querySelectorAll("[data-exp-id]").forEach((btn) => {
      btn.addEventListener("click", () => onSelectExperience?.(Number(btn.dataset.expId)));
    });
  } catch (err) {
    container.innerHTML = `<p class="cp-muted">${escapeHtml(err.message)}</p>`;
  }
}

async function renderDetail(panel, exp, { onRefresh, onOpenBuilder, tab = "overview" }) {
  let analytics = null;
  if (tab === "analytics") {
    try {
      analytics = await fetchJson(`/api/qr-experiences/${exp.id}/analytics?period=30d`);
    } catch (err) {
      analytics = { error: err.message };
    }
  }

  const scans = exp.analytics?.scan_count ?? 0;
  const actions = exp.analytics?.response_count ?? exp.analytics?.completed_actions ?? 0;
  const unique = exp.analytics?.unique_visitors ?? 0;
  const conv = exp.analytics?.conversion_rate ?? 0;

  panel.innerHTML = `
    <h3 class="bos-drawer-title">${escapeHtml(exp.name)} ${statusBadge(exp.status)}</h3>
    <nav class="bos-subnav" style="margin:12px 0 16px">
      ${DETAIL_TABS.map(([id, label]) =>
        `<button type="button" class="bos-subnav__item${tab === id ? " is-active" : ""}" data-detail-tab="${id}">${label}</button>`
      ).join("")}
    </nav>
    <div id="qrx-detail-body"></div>
  `;

  const body = panel.querySelector("#qrx-detail-body");

  if (tab === "overview") {
    body.innerHTML = `
      <p>${escapeHtml(exp.type_label)} · ${statusBadge(exp.status)}</p>
      ${exp.template_name ? `<p class="cp-muted" style="font-size:13px">Template: ${escapeHtml(exp.template_name)}${exp.template_version ? ` (v${exp.template_version})` : ""}</p>` : ""}
      ${exp.description ? `<p class="cp-muted">${escapeHtml(exp.description)}</p>` : ""}
      ${exp.qr_image ? `
        <div style="margin:16px 0;text-align:center">
          <img src="${exp.qr_image}" alt="QR code" width="160" height="160" style="border:1px solid var(--color-border,#e5e5e5);border-radius:8px;background:#fff">
          <p class="cp-muted" style="margin:8px 0 0;font-size:12px">Primary QR · <button type="button" class="bos-link-btn" data-detail-tab="qr-codes">Manage all QR codes</button></p>
        </div>` : `<p class="cp-muted">Publish to generate QR codes and a public link.</p>`}
      ${exp.created_at ? `<p class="cp-muted" style="font-size:13px">Created ${escapeHtml(String(exp.created_at).slice(0, 10))}${exp.updated_at ? ` · Updated ${escapeHtml(String(exp.updated_at).slice(0, 10))}` : ""}</p>` : ""}
      <section class="bos-dash-grid" style="margin:16px 0;grid-template-columns:repeat(${MVP_FLAGS.advancedAnalytics ? 3 : 2},1fr)">
        <article class="bos-stat-card"><span class="bos-stat-val">${scans}</span><span class="bos-stat-lbl">Views</span></article>
        <article class="bos-stat-card"><span class="bos-stat-val">${actions}</span><span class="bos-stat-lbl">Responses</span></article>
        ${MVP_FLAGS.advancedAnalytics ? `<article class="bos-stat-card"><span class="bos-stat-val">${unique}</span><span class="bos-stat-lbl">Visitors</span></article>` : ""}
      </section>
      <div class="bos-field" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
        <button type="button" class="bos-btn bos-btn-primary" id="qr-builder">Edit Experience</button>
        ${exp.status !== "active" ? `<button type="button" class="bos-btn bos-btn-ghost" id="qr-publish">Publish</button>` : ""}
        <button type="button" class="bos-btn bos-btn-ghost" id="qr-duplicate">Duplicate</button>
        ${exp.code ? `<a class="bos-btn bos-btn-ghost" href="/e/${escapeHtml(exp.public_slug || exp.code)}" target="_blank" rel="noopener">Customer view</a>` : ""}
        ${exp.status !== "archived" ? `<button type="button" class="bos-btn bos-btn-ghost" id="qr-archive">Archive</button>` : ""}
        ${exp.status === "draft" || exp.status === "archived" ? `<button type="button" class="bos-btn bos-btn-danger" id="qr-delete">Delete</button>` : ""}
      </div>`;
  } else if (tab === "preview") {
    const previewUrl = exp.public_slug
      ? `/e/${encodeURIComponent(exp.public_slug)}`
      : (exp.code ? `/e/${encodeURIComponent(exp.code)}` : "");
    body.innerHTML = previewUrl ? `
      <p class="cp-muted" style="margin:0 0 12px">Customer view — mobile-first landing page</p>
      <iframe src="${previewUrl}" title="Customer preview" style="width:100%;min-height:520px;border:1px solid var(--color-border,#e5e5e5);border-radius:12px;background:#fff"></iframe>
      <a class="bos-btn bos-btn-ghost bos-btn-sm" href="${previewUrl}" target="_blank" rel="noopener" style="margin-top:12px">Open in new tab</a>`
      : `<p class="cp-muted">Publish this experience to preview the customer page.</p>`;
  } else if (tab === "qr-codes") {
    let codes = exp.qr_codes || [];
    try {
      codes = await fetchJson(`/api/experiences/${exp.id}/qr-codes`);
    } catch {
      codes = exp.qr_codes || [];
    }
    body.innerHTML = `
      <p class="cp-muted" style="margin:0 0 12px">One experience can have multiple QR codes — table, counter, website, and more.</p>
      <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
        <input class="bos-input bos-input-sm" id="qr-new-name" placeholder="QR name (e.g. Table 1)" style="max-width:220px">
        <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="qr-add-code">Create QR</button>
      </div>
      ${codes.length ? `
        <ul class="bos-timeline" id="qr-codes-list">
          ${codes.map((q) => `
            <li data-qr-id="${q.id}" style="display:flex;gap:12px;align-items:start;flex-wrap:wrap">
              ${q.qr_image ? `<img src="${q.qr_image}" alt="" width="72" height="72" style="border:1px solid var(--color-border,#e5e5e5);border-radius:8px;background:#fff">` : ""}
              <div style="flex:1;min-width:180px">
                <input class="bos-input bos-input-sm qr-code-name" value="${escapeHtml(q.name)}" data-id="${q.id}">
                <p class="cp-muted" style="margin:6px 0 0;font-size:12px">${statusBadge(q.status)}${q.is_primary ? " · Primary" : ""}</p>
                ${q.url ? `<code style="font-size:11px">${escapeHtml(q.url)}</code>` : `<span class="cp-muted" style="font-size:12px">Publish experience to activate</span>`}
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                ${q.qr_image ? `<a class="bos-btn bos-btn-ghost bos-btn-sm" href="${q.qr_image}" download="qr-${q.code}.png">Download</a>` : ""}
              </div>
            </li>`).join("")}
        </ul>` : `<p class="cp-muted">No QR codes yet. Create one after publishing, or use the primary QR generated on publish.</p>`}
    `;
    body.querySelector("#qr-add-code")?.addEventListener("click", async () => {
      const nameInput = body.querySelector("#qr-new-name");
      const qrName = nameInput?.value.trim() || "QR Code";
      try {
        await fetchJson(`/api/experiences/${exp.id}/qr-codes`, {
          method: "POST",
          headers: csrfHeaders(),
          body: JSON.stringify({ name: qrName }),
        });
        notifySuccess("QR code created");
        onRefresh?.();
        renderDetail(panel, exp, { onRefresh, onOpenBuilder, tab: "qr-codes" });
      } catch (err) {
        notifyError(err.message);
      }
    });
    body.querySelectorAll(".qr-code-name").forEach((input) => {
      input.addEventListener("change", async () => {
        const qrId = Number(input.dataset.id);
        const name = input.value.trim();
        if (!name) return;
        await fetchJson(`/api/experiences/${exp.id}/qr-codes/${qrId}`, {
          method: "PATCH",
          headers: csrfHeaders(),
          body: JSON.stringify({ name }),
        });
        notifySuccess("QR renamed");
        onRefresh?.();
      });
    });
  } else if (tab === "flow") {
    let wf = null;
    try {
      wf = await fetchJson(`/api/qr-experiences/${exp.id}/workflow`);
    } catch { wf = null; }
    const steps = wf?.steps || exp.customer_flow || [];
    body.innerHTML = `
      <p class="cp-muted" style="margin:0 0 12px">Customer journey after QR scan — ${wf ? statusBadge(wf.status) : statusBadge("draft")}</p>
      <ol style="margin:0;padding-left:20px;font-size:14px">
        ${steps.map((s, i) => `
          <li style="margin-bottom:10px">
            <strong>${escapeHtml(s.label)}</strong>
            <span class="cp-muted" style="margin-left:6px;font-size:12px">${escapeHtml(stepTypeLabel(s.type || s.id || ""))}</span>
            ${i < steps.length - 1 ? `<p class="cp-muted" style="margin:4px 0 0;font-size:12px">↓</p>` : ""}
          </li>`).join("") || "<li class='cp-muted'>No workflow steps — configure the customer journey</li>"}
      </ol>
      <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
        <button type="button" class="bos-btn bos-btn-primary" id="qr-workflow-edit">Edit workflow</button>
        <button type="button" class="bos-btn bos-btn-ghost" id="qr-builder">Edit experience</button>
        ${wf?.status !== "active" ? `<button type="button" class="bos-btn bos-btn-ghost" id="qr-wf-publish">Publish workflow</button>` : ""}
      </div>`;
    body.querySelector("#qr-workflow-edit")?.addEventListener("click", () => {
      openWorkflowEditor(exp, { onClose: () => onRefresh?.(), onSaved: () => onRefresh?.() });
    });
    body.querySelector("#qr-wf-publish")?.addEventListener("click", async () => {
      await fetchJson(`/api/qr-experiences/${exp.id}/workflow/publish`, { method: "POST", headers: csrfHeaders(), body: "{}" });
      notifySuccess("Workflow published");
      onRefresh?.();
    });
  } else if (tab === "analytics") {
    if (analytics?.error) {
      body.innerHTML = `<p class="cp-muted">${escapeHtml(analytics.error)}</p>`;
    } else {
      body.innerHTML = `
        <section class="bos-dash-grid" style="grid-template-columns:repeat(2,1fr);margin-bottom:16px">
          <article class="bos-stat-card"><span class="bos-stat-val">${analytics.total_scans ?? 0}</span><span class="bos-stat-lbl">Scans</span></article>
          <article class="bos-stat-card"><span class="bos-stat-val">${analytics.unique_visitors ?? 0}</span><span class="bos-stat-lbl">Visitors</span></article>
          <article class="bos-stat-card"><span class="bos-stat-val">${analytics.completed_actions ?? 0}</span><span class="bos-stat-lbl">Completed</span></article>
          <article class="bos-stat-card"><span class="bos-stat-val">${pct(analytics.conversion_rate)}</span><span class="bos-stat-lbl">Conversion</span></article>
        </section>
        <h4>Customer Flow</h4>
        ${renderFlowFunnel(analytics.flow)}
        <h4 style="margin-top:16px">Drop-offs</h4>
        ${renderDropOffs(analytics.drop_offs)}
        <h4 style="margin-top:16px">Devices</h4>
        <p class="cp-muted" style="font-size:13px">
          Mobile ${analytics.devices?.mobile ?? 0} · Desktop ${analytics.devices?.desktop ?? 0} · Tablet ${analytics.devices?.tablet ?? 0}
        </p>
        <h4 style="margin-top:16px">Completions</h4>
        <ul style="margin:0;padding-left:18px;font-size:13px">
          <li>Feedback: ${analytics.by_action?.survey_completed ?? 0}</li>
          <li>Bookings: ${analytics.by_action?.booking_completed ?? 0}</li>
          <li>Check-ins: ${analytics.by_action?.checkin_completed ?? 0}</li>
        </ul>`;
    }
  } else if (tab === "responses") {
    let rows = [];
    try {
      rows = await fetchJson(`/api/qr-experiences/${exp.id}/responses`);
    } catch { rows = []; }
    body.innerHTML = rows.length ? `
      <ul class="bos-timeline">
        ${rows.map((r) => `
          <li>
            <strong>${"★".repeat(r.rating || 0)}</strong>
            ${escapeHtml((r.comment || r.content || "").slice(0, 100))}
            <br><span class="cp-muted">${escapeHtml(r.customer_name || "Anonymous")} · ${escapeHtml((r.created_at || "").slice(0, 16))}</span>
          </li>`).join("")}
      </ul>
      <a class="bos-btn bos-btn-ghost bos-btn-sm" href="/app/store#responses" style="margin-top:12px">All responses</a>`
      : `<p class="cp-muted">No responses yet for this experience.</p>
         <a class="bos-btn bos-btn-primary bos-btn-sm" href="/app/store#responses" style="margin-top:12px">View all responses</a>`;
  } else if (tab === "settings") {
    body.innerHTML = `
      <form id="qr-settings-form" class="bos-form">
        <div class="bos-field"><label class="bos-label">Name</label>
          <input class="bos-input" name="name" value="${escapeHtml(exp.name)}"></div>
        <div class="bos-field" style="margin-top:12px"><label class="bos-label">Description</label>
          <textarea class="bos-input" name="description" rows="2">${escapeHtml(exp.description || "")}</textarea></div>
        <div class="bos-field" style="margin-top:12px"><label class="bos-label">Type</label>
          <p>${escapeHtml(exp.type_label || exp.type || "—")}</p></div>
        <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
          <button type="submit" class="bos-btn bos-btn-primary">Save</button>
          <button type="button" class="bos-btn bos-btn-ghost" id="qr-builder">Edit content</button>
          ${exp.status !== "active" ? `<button type="button" class="bos-btn bos-btn-primary" id="qr-publish">Publish</button>` : ""}
        </div>
      </form>`;
    body.querySelector("#qr-settings-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      await fetchJson(`/api/qr-experiences/${exp.id}`, {
        method: "PATCH",
        headers: csrfHeaders(),
        body: JSON.stringify({ name: fd.get("name"), description: fd.get("description") }),
      });
      notifySuccess("Settings saved");
      onRefresh?.();
    });
  }

  panel.querySelectorAll("[data-detail-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      renderDetail(panel, exp, { onRefresh, onOpenBuilder, tab: btn.dataset.detailTab });
    });
  });

  panel.querySelectorAll("#qr-builder").forEach((btn) => {
    btn.addEventListener("click", () => onOpenBuilder(exp));
  });
  panel.querySelector("#qr-duplicate")?.addEventListener("click", async () => {
    const dup = await fetchJson(`/api/qr-experiences/${exp.id}/duplicate`, { method: "POST", headers: csrfHeaders(), body: "{}" });
    showToast("Duplicated");
    onRefresh();
    if (dup?.id) onOpenBuilder(dup);
  });
  panel.querySelector("#qr-publish")?.addEventListener("click", async () => {
    await fetchJson(`/api/qr-experiences/${exp.id}/publish`, { method: "POST", headers: csrfHeaders(), body: "{}" });
    showToast("Published");
    onRefresh();
  });
  panel.querySelector("#qr-archive")?.addEventListener("click", async () => {
    if (!confirm("Archive this experience?")) return;
    await fetchJson(`/api/qr-experiences/${exp.id}/archive`, { method: "POST", headers: csrfHeaders(), body: "{}" });
    showToast("Archived");
    panel.classList.add("hidden");
    onRefresh();
  });
  panel.querySelector("#qr-delete")?.addEventListener("click", async () => {
    const msg = exp.status === "archived"
      ? "Permanently delete this archived experience? This cannot be undone."
      : "Permanently delete this draft experience? This cannot be undone.";
    if (!confirm(msg)) return;
    await fetchJson(`/api/qr-experiences/${exp.id}`, { method: "DELETE", headers: csrfHeaders() });
    showToast("Deleted");
    panel.classList.add("hidden");
    onRefresh();
  });
}

/** MVP create flow — pick customer QR type */
function openCreateWizard(_categories, onCreated, opts = {}) {
  const { storeId = null } = opts;
  let selected = MVP_QR_TYPES[0];
  let name = selected.name;

  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay";
  overlay.innerHTML = `
    <div class="bos-modal bos-modal--sm bos-create-wizard" role="dialog" aria-labelledby="qrx-create-title">
      <header class="bos-create-wizard__head">
        <h2 class="bos-panel-title" id="qrx-create-title">Add customer QR</h2>
        <p class="cp-muted bos-create-wizard__hint">Pick a type → customize → go live → share with customers</p>
      </header>
      <div class="bos-type-picker" role="listbox" aria-label="Experience type">
        ${MVP_QR_TYPES.map((t) => `
          <button type="button" class="bos-type-picker__option${selected.id === t.id ? " is-selected" : ""}" data-tpl="${t.id}" role="option" aria-selected="${selected.id === t.id}">
            <strong class="bos-type-picker__name">${escapeHtml(t.name)}</strong>
            <p class="bos-type-picker__desc">${escapeHtml(t.description)}</p>
          </button>`).join("")}
      </div>
      <div class="bos-field bos-create-wizard__name">
        <label class="bos-label" for="qrx-name">Name</label>
        <input class="bos-input" id="qrx-name" value="${escapeHtml(name)}">
      </div>
      <footer class="bos-create-wizard__foot">
        <button type="button" class="bos-btn bos-btn-ghost" id="qrx-cancel">Cancel</button>
        <button type="button" class="bos-btn bos-btn-primary" id="qrx-create">Continue</button>
      </footer>
    </div>`;

  const paintSel = () => {
    overlay.querySelectorAll("[data-tpl]").forEach((btn) => {
      const on = selected.id === btn.dataset.tpl;
      btn.classList.toggle("is-selected", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
  };
  overlay.querySelectorAll("[data-tpl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selected = MVP_QR_TYPES.find((t) => t.id === btn.dataset.tpl) || selected;
      overlay.querySelector("#qrx-name").value = selected.name;
      paintSel();
    });
  });
  overlay.querySelector("#qrx-cancel").addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  overlay.querySelector(".bos-modal")?.addEventListener("click", (e) => e.stopPropagation());
  overlay.querySelector("#qrx-create").addEventListener("click", async () => {
    name = overlay.querySelector("#qrx-name")?.value.trim() || selected.name;
    const description = selected.description;
    try {
      const created = await fetchJson("/api/qr-experiences", {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({
          name,
          type: selected.id,
          description,
          template_id: selected.template_id,
          store_id: storeId || undefined,
          experience_config: { template_id: selected.template_id, description },
        }),
      });
      overlay.remove();
      onCreated?.(created);
    } catch (err) {
      notifyError(err.message);
    }
  });
  document.body.appendChild(overlay);
  overlay.querySelector("#qrx-name")?.focus();
}

/** @deprecated full template picker — kept for deferredActions */
function openCreateWizardFull(categories, onCreated) {
  const allTemplates = categories.flatMap((c) => (c.templates || []).map((t) => ({ ...t, category: c.label })));
  let selected = allTemplates[0] || null;
  let name = selected?.default_name || "";
  let description = selected?.description || "";

  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay";
  overlay.innerHTML = `
    <div class="bos-modal" style="max-width:640px">
      <h2 class="bos-panel-title">Create Experience</h2>
      <p class="cp-muted">Choose a business scenario, customize, then publish.</p>
      <div id="qrx-tpl-categories" style="margin:16px 0;max-height:360px;overflow-y:auto">
        ${categories.map((cat) => `
          <section style="margin-bottom:20px">
            <h3 style="margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--color-text-secondary,#666)">${escapeHtml(cat.label)}</h3>
            <div class="bos-dash-grid" style="grid-template-columns:1fr;gap:8px">
              ${(cat.templates || []).map((t) => `
                <button type="button" class="bos-stat-card" data-tpl="${t.id}"
                  style="cursor:pointer;text-align:left;border:2px solid ${selected?.id === t.id ? "var(--color-text-primary,#111)" : "transparent"}">
                  <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
                    <strong>${escapeHtml(t.name || t.label)}</strong>
                    <span class="bos-btn bos-btn-sm bos-btn-ghost" style="pointer-events:none;font-size:11px">Create</span>
                  </div>
                  <p class="cp-muted" style="margin:6px 0 0;font-size:13px">${escapeHtml(t.description)}</p>
                  <p style="margin:8px 0 0;font-size:12px">${escapeHtml(flowLabel(t.customer_flow))}</p>
                </button>`).join("")}
            </div>
          </section>`).join("")}
      </div>
      <div class="bos-field">
        <label class="bos-label">Experience Name</label>
        <input class="bos-input" id="qrx-name" value="${escapeHtml(name)}">
      </div>
      <div class="bos-field" style="margin-top:12px">
        <label class="bos-label">Description</label>
        <textarea class="bos-input" id="qrx-desc" rows="2">${escapeHtml(description)}</textarea>
      </div>
      <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end">
        <button type="button" class="bos-btn bos-btn-ghost" id="qrx-cancel">Cancel</button>
        <button type="button" class="bos-btn bos-btn-primary" id="qrx-create">Continue to Builder</button>
      </div>
    </div>`;

  const paintSel = () => {
    overlay.querySelectorAll("[data-tpl]").forEach((btn) => {
      btn.style.borderColor = selected?.id === btn.dataset.tpl ? "var(--color-text-primary,#111)" : "transparent";
    });
  };
  overlay.querySelectorAll("[data-tpl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selected = allTemplates.find((t) => t.id === btn.dataset.tpl);
      overlay.querySelector("#qrx-name").value = selected.default_name;
      overlay.querySelector("#qrx-desc").value = selected.description;
      paintSel();
    });
  });
  overlay.querySelector("#qrx-cancel").addEventListener("click", () => overlay.remove());
  overlay.querySelector("#qrx-create").addEventListener("click", async () => {
    if (!selected) { showToast("Choose a template"); return; }
    name = overlay.querySelector("#qrx-name")?.value.trim() || selected.default_name;
    description = overlay.querySelector("#qrx-desc")?.value.trim() || "";
    try {
      const created = await fetchJson("/api/qr-experiences", {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({
          name,
          description,
          template_id: selected.id,
          type: selected.type || selected.experience_type,
          experience_config: {
            template_id: selected.id,
            template_version: selected.version || 1,
            description,
            customer_flow: selected.customer_flow,
            connected: selected.connected,
            enabled_actions: selected.enabled_actions,
          },
        }),
      });
      overlay.remove();
      showToast("Draft created — customize, then publish");
      onCreated(created);
    } catch (err) {
      showToast(err.message);
    }
  });
  document.body.appendChild(overlay);
}

/** @param {HTMLElement} root @param {{ embedded?: boolean, storeId?: number | null }} [opts] */
export async function mountQrExperiencesPage(root, opts = {}) {
  const { embedded = false, storeId = null } = opts;
  root.innerHTML = loadingState();
  if (!embedded) {
    setPageActions(button({ variant: "primary", label: "Add customer QR", id: "qrx-new", sm: true }));
  }

  const storeLabel = storeId && window.WORKSPACE_BOOT?.stores
    ? window.WORKSPACE_BOOT.stores.find((s) => s.id === storeId)?.name
    : null;

  const triggerCreate = () => {
    openCreateWizard(null, async (created) => {
      await refresh();
      if (created?.id) openBuilderFor(created);
    }, { storeId });
  };

  window.addEventListener("bos:add-customer-qr", (e) => {
    if (storeId && e.detail?.storeId && e.detail.storeId !== storeId) return;
    triggerCreate();
  });
  try {
    let all = await fetchJson("/api/qr-experiences");
    let categories = null;

    const loadTemplates = async () => {
      if (categories) return categories;
      const tplData = await fetchJson("/api/qr-templates?grouped=true");
      categories = (tplData.categories || [])
        .map((cat) => ({
          ...cat,
          templates: (cat.templates || []).filter(
            (t) => MVP_FLAGS.deferredActions || !DEFERRED_TEMPLATE_IDS.has(t.id),
          ),
        }))
        .filter((cat) => (cat.templates || []).length);
      return categories;
    };

    let filter = "all";
    let searchQ = "";
    const selected = new Set();

    const qrxToolbar = `
      <div class="bos-toolbar-inline qrx-toolbar" style="margin-bottom:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center">
        <input type="search" class="bos-input merchant-search" id="qrx-search" placeholder="Search experiences…" style="flex:1;min-width:200px;max-width:320px" value="${escapeHtml(searchQ)}">
        <label class="qrx-select-all checkbox-label"><input type="checkbox" id="qrx-select-all"> Select all</label>
        ${button({ variant: "primary", label: "Add customer QR", id: "qrx-create-top", sm: true })}
      </div>`;

    root.innerHTML = embedded ? `
      <div id="qrx-embedded">
        ${storeLabel ? `<p class="qrx-store-filter cp-muted">Showing customer QR for <strong>${escapeHtml(storeLabel)}</strong></p>` : ""}
        ${qrxToolbar}
        <div id="qrx-filters" style="margin-bottom:16px"></div>
        <div id="qrx-list"></div>
        <aside id="qrx-detail" class="bos-side-panel hidden"></aside>
      </div>` : `<div class="merchant-page">
      ${pageHeader({
        title: "Customer QR",
        subtitle: storeLabel
          ? `QR codes customers scan at ${storeLabel}.`
          : "QR codes customers scan — menu, feedback, booking, and more.",
        actionsHtml: button({ variant: "primary", label: "Add customer QR", id: "qrx-create-top-header", sm: true }),
      })}
      ${qrxToolbar}
      <div id="qrx-filters" style="margin-bottom:16px"></div>
      <div id="qrx-list"></div>
      <aside id="qrx-detail" class="bos-side-panel hidden"></aside>
    </div>`;

    const listEl = document.getElementById("qrx-list");
    const detailEl = document.getElementById("qrx-detail");
    const filtersEl = document.getElementById("qrx-filters");
    const selectAllEl = document.getElementById("qrx-select-all");

    const updateBatchBar = (visibleRows = []) => {
      const count = selected.size;
      renderActionBar(count, BATCH_ACTIONS, runBatch);
      document.body.classList.toggle("has-action-bar", count > 0);
      if (!selectAllEl) return;
      if (!visibleRows.length) {
        selectAllEl.checked = false;
        selectAllEl.indeterminate = false;
        return;
      }
      const visibleIds = visibleRows.map((r) => r.id);
      const selectedVisible = visibleIds.filter((id) => selected.has(id)).length;
      selectAllEl.checked = selectedVisible === visibleIds.length && visibleIds.length > 0;
      selectAllEl.indeterminate = selectedVisible > 0 && selectedVisible < visibleIds.length;
    };

    const runBatch = async (action) => {
      const ids = [...selected];
      if (!ids.length) {
        showToast("Select at least one experience.");
        return;
      }
      if (action === "delete" && !confirm(`Permanently delete ${ids.length} experience(s)? Active items will be skipped.`)) return;
      if (action === "archive" && !confirm(`Archive ${ids.length} experience(s)?`)) return;
      try {
        const data = await apiPost("/api/qr-experiences/batch", { action, experience_ids: ids });
        if (action === "export") {
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
          const link = document.createElement("a");
          link.href = URL.createObjectURL(blob);
          link.download = `experiences-${Date.now()}.json`;
          link.click();
          notifySuccess(`Exported ${ids.length} experience(s).`);
          return;
        }
        selected.clear();
        await refresh();
        const msg = data.skipped
          ? `${data.processed} done, ${data.skipped} skipped`
          : `${data.processed} experience(s) updated`;
        notifySuccess(msg);
      } catch (err) {
        notifyError(err.message);
      }
    };

    const paintList = () => {
      const visible = renderExperienceList(listEl, all, filter, {
        onSelect: openDetail,
        onAction: handleAction,
        selected,
      });
      updateBatchBar(visible);
      renderFilterTabs(filtersEl, [
        { id: "all", label: "All" },
        { id: "active", label: "Active" },
        { id: "draft", label: "Draft" },
        { id: "archived", label: "Archived" },
      ], filter, (id) => { filter = id; paintList(); });
    };

    document.getElementById("qrx-search")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        searchQ = e.target.value || "";
        refresh();
      }
    });

    const refresh = async () => {
      const q = searchQ.trim();
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (storeId) params.set("store_id", String(storeId));
      const url = params.toString() ? `/api/qr-experiences?${params}` : "/api/qr-experiences";
      all = await fetchJson(url);
      paintList();
    };

    const handleAction = async (act, id, extra = {}) => {
      if (act === "toggle-select") {
        if (extra.checked) selected.add(id);
        else selected.delete(id);
        paintList();
        return;
      }
      if (act === "create") {
        triggerCreate();
        return;
      }
      const exp = await fetchJson(`/api/qr-experiences/${id}`);
      if (act === "open") await openDetail(id);
      else if (act === "edit") openBuilderFor(exp);
      else if (act === "duplicate") {
        const dup = await fetchJson(`/api/qr-experiences/${id}/duplicate`, { method: "POST", headers: csrfHeaders(), body: "{}" });
        notifySuccess("Duplicated");
        await refresh();
        if (dup?.id) openBuilderFor(dup);
      } else if (act === "archive") {
        if (!confirm("Archive this experience?")) return;
        await fetchJson(`/api/qr-experiences/${id}/archive`, { method: "POST", headers: csrfHeaders(), body: "{}" });
        notifySuccess("Archived");
        detailEl.classList.add("hidden");
        await refresh();
      } else if (act === "delete") {
        const item = all.find((r) => r.id === id);
        const msg = item?.status === "archived"
          ? "Permanently delete this archived experience? This cannot be undone."
          : "Permanently delete this draft experience? This cannot be undone.";
        if (!confirm(msg)) return;
        await fetchJson(`/api/qr-experiences/${id}`, { method: "DELETE", headers: csrfHeaders() });
        notifySuccess("Deleted");
        detailEl.classList.add("hidden");
        await refresh();
      }
    };

    const openBuilderFor = (exp) => {
      openBuilder(exp, {
        onClose: () => refresh(),
        onSaved: async (updated) => {
          await refresh();
          renderDetail(detailEl, updated, {
            onRefresh: async () => {
              await refresh();
              const u = await fetchJson(`/api/qr-experiences/${updated.id}`);
              renderDetail(detailEl, u, { onRefresh: refresh, onOpenBuilder: openBuilderFor });
            },
            onOpenBuilder: openBuilderFor,
          });
        },
      });
    };

    const openDetail = async (id, detailTab = "overview") => {
      const exp = await fetchJson(`/api/qr-experiences/${id}`);
      detailEl.classList.remove("hidden");
      window.location.hash = `experience/${id}`;
      renderDetail(detailEl, exp, {
        tab: detailTab,
        onRefresh: async () => {
          await refresh();
          const updated = await fetchJson(`/api/qr-experiences/${id}`);
          renderDetail(detailEl, updated, { onRefresh: refresh, onOpenBuilder: openBuilderFor, tab: detailTab });
        },
        onOpenBuilder: openBuilderFor,
      });
    };

    paintList();

    selectAllEl?.addEventListener("change", (e) => {
      const visible = filterExperiences(all, filter);
      if (e.target.checked) visible.forEach((r) => selected.add(r.id));
      else visible.forEach((r) => selected.delete(r.id));
      paintList();
    });

    document.getElementById("qrx-create-top")?.addEventListener("click", () => handleAction("create"));
    document.getElementById("qrx-create-top-header")?.addEventListener("click", () => handleAction("create"));
    document.getElementById("qrx-new")?.addEventListener("click", () => handleAction("create"));

    const hash = window.location.hash.match(/(?:experience|builder)\/(\d+)/);
    if (hash) {
      const id = Number(hash[1]);
      await openDetail(id);
      if (window.location.hash.includes("builder")) {
        const exp = await fetchJson(`/api/qr-experiences/${id}`);
        openBuilderFor(exp);
      }
    }
  } catch (err) {
    root.innerHTML = emptyState({
      title: "Could not load experiences",
      text: `${err.message}. Select a workspace first.`,
    });
  }
}
