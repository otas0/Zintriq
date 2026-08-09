import * as store from "../core/store.js";
import { getDrawerState, setDrawerState } from "../core/ui-state.js";
import { escapeHtml } from "../services/search.js";
import { openDrawer, closeDrawer, showToast } from "../services/api.js";
import { statusBadge, tag as tagBadge } from "../components/index.js";
import { OBJECT_TYPES, getObjectType, getObjectTitle } from "./object-types.js";
import { STANDARD_DRAWER_TABS } from "./object-standards.js";
import { groupRelatedObjects } from "./relationships.js";
import { renderPropertiesPanel, parsePropertyForm, renderPropertyDisplay } from "./properties.js";
import { formatActivityAction } from "./activity.js";
import { assignTag, removeTag } from "./tags.js";
import { listAttachments, addAttachment, removeAttachment, getFileIcon, mockPickFile } from "./attachments.js";
import { listNotes, addNote, updateNote, deleteNote, renderNoteBody } from "./notes.js";
import { trackObjectRecent, toggleObjectFavorite, isObjectFavorite } from "./recents.js";

/** @type {{ collection: string, id: string }[]} */
let drawerStack = [];

/** @type {(() => void) | null} */
let onRefresh = null;

const TABS = STANDARD_DRAWER_TABS;

function renderOverview(typeDef, record) {
  const tags = (record.tagIds || []).map((id) => {
    const t = store.getById("tags", id);
    return t ? tagBadge(String(t.name), String(t.color)) : "";
  }).join(" ");

  const summaryProps = typeDef.properties.filter((p) => p.key !== "tagIds").slice(0, 6);

  return `<div class="bos-obj-overview">
    <div class="bos-obj-overview__head">
      ${record.status ? statusBadge(String(record.status)) : ""}
      ${tags ? `<div class="bos-obj-tags">${tags}</div>` : ""}
    </div>
    <dl class="bos-prop-list bos-prop-list--compact">
      ${summaryProps.map((p) => `<div class="bos-prop-row"><dt>${escapeHtml(p.label)}</dt><dd>${renderPropertyDisplay(p, record[p.key])}</dd></div>`).join("")}
    </dl>
    <p class="bos-card__meta">Updated ${escapeHtml(String(record.updatedAt || record.createdAt || "").slice(0, 16).replace("T", " "))}</p>
  </div>`;
}

function renderRelated(collection, id) {
  const groups = groupRelatedObjects(collection, id);
  const keys = Object.keys(groups);
  if (!keys.length) return `<p class="bos-empty__text">No related objects yet.</p>`;

  return keys.map((label) => `
    <section class="bos-related-group">
      <h4 class="bos-related-group__title">${escapeHtml(label)}</h4>
      <ul class="bos-related-list">
        ${groups[label].map((r) => `<li><button type="button" class="bos-related-link" data-rel-collection="${r.collection}" data-rel-id="${r.id}">${escapeHtml(r.label)}</button></li>`).join("")}
      </ul>
    </section>`).join("");
}

function renderActivityTimeline(collection, id) {
  const items = store.getObjectActivities(collection, id);
  if (!items.length) return `<p class="bos-empty__text">No activity recorded yet.</p>`;
  return `<ul class="bos-timeline">${items.map((a) => `
    <li class="bos-timeline__item">
      <span class="bos-timeline__action">${escapeHtml(formatActivityAction(String(a.action || "updated")))}</span>
      <span class="bos-timeline__msg">${escapeHtml(String(a.message))}</span>
      <span class="bos-timeline__meta">${escapeHtml(String(a.actor))} · ${escapeHtml(String(a.at).slice(0, 16).replace("T", " "))}</span>
    </li>`).join("")}</ul>`;
}

function renderAttachmentsPanel(collection, id) {
  const items = listAttachments(collection, id);
  return `<div class="bos-att-panel">
    <button type="button" class="os-btn os-btn-ghost os-btn-sm" id="bos-add-attachment">Add attachment (mock)</button>
    ${items.length ? `<ul class="bos-att-list">${items.map((a) => `
      <li class="bos-att-item">
        <span class="bos-att-icon">${getFileIcon(String(a.type))}</span>
        <span class="bos-att-name">${escapeHtml(String(a.name))}</span>
        <span class="bos-att-size">${escapeHtml(String(a.size))}</span>
        <button type="button" class="os-btn os-btn-ghost os-btn-sm" data-del-att="${a.id}">Remove</button>
      </li>`).join("")}</ul>` : `<p class="bos-empty__text">No attachments yet.</p>`}
  </div>`;
}

function renderNotesPanel(collection, id) {
  const items = listNotes(collection, id);
  return `<div class="bos-notes-panel">
    <form class="bos-note-form" id="bos-note-form">
      <textarea class="os-input bos-note-input" name="body" rows="3" placeholder="Add a note… Supports **bold** markdown."></textarea>
      <button type="submit" class="os-btn os-btn-primary os-btn-sm">Add note</button>
    </form>
    ${items.length ? `<div class="bos-notes-list">${items.map((n) => `
      <article class="bos-note" data-note-id="${n.id}">
        <div class="bos-note__body" contenteditable="true">${renderNoteBody(String(n.body))}</div>
        <footer class="bos-note__foot">
          <span>${escapeHtml(String(n.author))} · ${escapeHtml(String(n.updatedAt || n.createdAt || "").slice(0, 10))}</span>
          <button type="button" class="os-btn os-btn-ghost os-btn-sm" data-del-note="${n.id}">Delete</button>
        </footer>
      </article>`).join("")}</div>` : ""}
  </div>`;
}

function renderTagManager(typeDef, record) {
  if (!typeDef.taggable) return "";
  const allTags = store.getCollection("tags");
  const assigned = new Set(record.tagIds || []);
  return `<div class="bos-tag-manager">
    <p class="bos-card__meta">Tags</p>
    <div class="bos-tag-manager__chips">${allTags.map((t) => `
      <button type="button" class="bos-filter-chip${assigned.has(t.id) ? " is-active" : ""}" data-tag-toggle="${t.id}">${escapeHtml(String(t.name))}</button>`).join("")}</div>
  </div>`;
}

function renderTabPanel(tab, typeDef, record, collection, id) {
  switch (tab) {
    case "overview":
      return renderOverview(typeDef, record) + renderTagManager(typeDef, record);
    case "properties":
      return renderPropertiesPanel(typeDef.properties, record);
    case "related":
      return renderRelated(collection, id);
    case "activity":
      return renderActivityTimeline(collection, id);
    case "attachments":
      return renderAttachmentsPanel(collection, id);
    case "notes":
      return renderNotesPanel(collection, id);
    default:
      return "";
  }
}

function wireTabPanel(tab, typeDef, record, collection, id) {
  const body = document.getElementById("bos-drawer-body");
  if (!body) return;

  if (tab === "properties") {
    body.querySelector("#bos-prop-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const patch = parsePropertyForm(new FormData(e.target), typeDef.properties);
      store.update(collection, id, patch);
      showToast("Properties saved");
      renderObjectDetail(collection, id, tab);
      onRefresh?.();
    });
  }

  if (tab === "related") {
    body.querySelectorAll("[data-rel-collection]").forEach((btn) => {
      btn.addEventListener("click", () => {
        renderObjectDetail(btn.getAttribute("data-rel-collection"), btn.getAttribute("data-rel-id"), "overview", { push: true });
      });
    });
  }

  if (tab === "attachments") {
    body.querySelector("#bos-add-attachment")?.addEventListener("click", () => {
      const mock = mockPickFile();
      addAttachment(collection, id, mock);
      showToast("Attachment added");
      renderObjectDetail(collection, id, tab);
    });
    body.querySelectorAll("[data-del-att]").forEach((btn) => {
      btn.addEventListener("click", () => {
        removeAttachment(btn.getAttribute("data-del-att"));
        showToast("Attachment removed");
        renderObjectDetail(collection, id, tab);
      });
    });
  }

  if (tab === "notes") {
    body.querySelector("#bos-note-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const bodyText = String(fd.get("body") || "").trim();
      if (!bodyText) return;
      addNote(collection, id, bodyText);
      showToast("Note added");
      renderObjectDetail(collection, id, tab);
    });
    body.querySelectorAll("[data-del-note]").forEach((btn) => {
      btn.addEventListener("click", () => {
        deleteNote(btn.getAttribute("data-del-note"));
        showToast("Note deleted");
        renderObjectDetail(collection, id, tab);
      });
    });
    body.querySelectorAll(".bos-note__body").forEach((el) => {
      el.addEventListener("blur", () => {
        const noteEl = el.closest("[data-note-id]");
        const noteId = noteEl?.getAttribute("data-note-id");
        if (!noteId) return;
        updateNote(noteId, el.innerText);
      });
    });
  }

  body.querySelectorAll("[data-tag-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tagId = btn.getAttribute("data-tag-toggle");
      const has = (record.tagIds || []).includes(tagId);
      if (has) removeTag(collection, id, tagId);
      else assignTag(collection, id, tagId);
      showToast(has ? "Tag removed" : "Tag assigned");
      renderObjectDetail(collection, id, tab);
      onRefresh?.();
    });
  });
}

function renderActions(typeDef, record, collection, id) {
  return `<div class="bos-obj-actions">
    ${drawerStack.length > 0 ? '<button type="button" class="os-btn os-btn-ghost os-btn-sm" data-obj-back>← Back</button>' : ""}
    <button type="button" class="os-btn os-btn-ghost os-btn-sm" data-action="duplicate">Duplicate</button>
    ${record.status === "archived"
    ? '<button type="button" class="os-btn os-btn-ghost os-btn-sm" data-action="restore">Restore</button>'
    : '<button type="button" class="os-btn os-btn-ghost os-btn-sm" data-action="archive">Archive</button>'}
    <button type="button" class="os-btn os-btn-danger os-btn-sm" data-action="delete">Delete</button>
    ${record.type === "qr" ? '<a class="os-btn os-btn-primary os-btn-sm" href="/app/store#experiences">View store</a>' : ""}
  </div>`;
}

function wireActions(typeDef, record, collection, id) {
  const body = document.getElementById("bos-drawer-body");
  body?.querySelector("[data-obj-back]")?.addEventListener("click", () => {
    drawerStack.pop();
    const prev = drawerStack[drawerStack.length - 1];
    if (prev) renderObjectDetail(prev.collection, prev.id, "overview", { push: false });
    else closeDrawer();
  });

  body?.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-action");
      if (action === "duplicate") { store.duplicate(collection, id); showToast("Duplicated"); onRefresh?.(); closeObjectDrawer(); }
      if (action === "archive") { store.archive(collection, id); showToast("Archived"); onRefresh?.(); closeObjectDrawer(); }
      if (action === "restore") { store.restore(collection, id); showToast("Restored"); onRefresh?.(); closeObjectDrawer(); }
      if (action === "delete") {
        if (!window.confirm("Delete this record permanently?")) return;
        store.remove(collection, id);
        showToast("Deleted");
        onRefresh?.();
        closeObjectDrawer();
      }
    });
  });

  body?.querySelector("[data-fav-toggle]")?.addEventListener("click", () => {
    const title = getObjectTitle(record, typeDef);
    const pinned = toggleObjectFavorite(collection, id, title);
    showToast(pinned ? "Added to favorites" : "Removed from favorites");
    renderObjectDetail(collection, id, document.querySelector(".bos-obj-tab.is-active")?.getAttribute("data-tab") || "overview", { push: false });
  });
}

/**
 * @param {string} collection
 * @param {string} id
 * @param {string} [activeTab]
 * @param {{ push?: boolean, refresh?: () => void }} [opts]
 */
export function renderObjectDetail(collection, id, activeTab, opts = {}) {
  const typeDef = getObjectType(collection);
  const record = store.getById(collection, id);
  if (!typeDef || !record) {
    openDrawer("Not found", `<div class="bos-empty"><p class="bos-empty__title">Object not found</p><p class="bos-empty__text">This record may have been deleted or the link is invalid.</p><button type="button" class="os-btn os-btn-ghost os-btn-sm" data-drawer-close-btn>Close</button></div>`);
    document.getElementById("bos-drawer-body")?.querySelector("[data-drawer-close-btn]")?.addEventListener("click", closeObjectDrawer);
    showToast("Object not found");
    return;
  }

  if (opts.refresh) onRefresh = opts.refresh;
  if (opts.push !== false) {
    if (!drawerStack.length || drawerStack[drawerStack.length - 1].collection !== collection || drawerStack[drawerStack.length - 1].id !== id) {
      drawerStack.push({ collection, id });
    }
  }

  const savedDrawer = getDrawerState();
  const tab = activeTab || (savedDrawer?.collection === collection && savedDrawer?.id === id ? savedDrawer.tab : "overview");
  setDrawerState({ collection, id, tab });

  const title = getObjectTitle(record, typeDef);
  trackObjectRecent(collection, id, title);
  store.trackRecent(collection, id, title, `${typeDef.modulePath}#obj/${collection}/${id}`);

  const fav = isObjectFavorite(collection, id);
  location.hash = `obj/${collection}/${id}`;

  openDrawer("", `
    <div class="bos-obj-detail">
      <header class="bos-obj-header">
        <p class="bos-obj-type">${escapeHtml(typeDef.label)}</p>
        <h2 class="bos-obj-title">${escapeHtml(title)}</h2>
        <button type="button" class="bos-obj-fav${fav ? " is-active" : ""}" data-fav-toggle aria-label="Favorite">${fav ? "★" : "☆"}</button>
      </header>
      ${renderActions(typeDef, record, collection, id)}
      <nav class="bos-obj-tabs" role="tablist">
        ${TABS.map((t) => `<button type="button" role="tab" class="bos-obj-tab${t.id === tab ? " is-active" : ""}" data-tab="${t.id}">${t.label}</button>`).join("")}
      </nav>
      <div class="bos-obj-panel" role="tabpanel">${renderTabPanel(tab, typeDef, record, collection, id)}</div>
    </div>`);

  const titleEl = document.getElementById("bos-drawer-title");
  if (titleEl) titleEl.textContent = title;

  window.dispatchEvent(new CustomEvent("bos:object-opened", {
    detail: { moduleId: typeDef.moduleId || document.body.dataset.module, objectLabel: title },
  }));

  const body = document.getElementById("bos-drawer-body");
  body?.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const nextTab = btn.getAttribute("data-tab") || "overview";
      setDrawerState({ collection, id, tab: nextTab });
      renderObjectDetail(collection, id, nextTab, { push: false });
    });
  });

  wireTabPanel(tab, typeDef, record, collection, id);
  wireActions(typeDef, record, collection, id);
}

export function openObjectDetail(collection, id, opts = {}) {
  drawerStack = [{ collection, id }];
  const saved = getDrawerState();
  const tab = saved?.collection === collection && saved?.id === id ? saved.tab : "overview";
  renderObjectDetail(collection, id, tab, opts);
}

export function openCreateObject(collection, opts = {}) {
  const typeDef = getObjectType(collection);
  if (!typeDef) return;

  const defaults = { status: "active", tagIds: [] };
  if (collection === "workspaces") defaults.organizationId = store.getCollection("organizations")[0]?.id;
  if (["catalog", "documents", "assets", "operations"].includes(collection)) {
    defaults.workspaceId = store.getCollection("workspaces")[0]?.id;
  }
  if (collection === "transactions") {
    defaults.date = new Date().toISOString();
    defaults.catalogItemIds = [];
  }
  if (collection === "operations") {
    defaults.dueAt = new Date().toISOString();
    defaults.assigneeIds = [];
    defaults.assetIds = [];
  }
  if (collection === "team") defaults.workspaceIds = [];

  drawerStack = [];
  openDrawer(`New ${typeDef.label}`, `
    <div class="bos-obj-detail">
      <p class="bos-obj-type">${escapeHtml(typeDef.label)}</p>
      ${renderPropertiesPanel(typeDef.properties.filter((p) => !p.readonly), defaults)}
    </div>`);

  document.getElementById("bos-drawer-title").textContent = `New ${typeDef.label}`;
  document.getElementById("bos-drawer-body")?.querySelector("form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const data = parsePropertyForm(new FormData(e.target), typeDef.properties);
    if (collection === "organizations" && data.name) {
      data.slug = String(data.name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    }
    const created = store.create(collection, data);
    showToast(`${typeDef.label} created`);
    opts.refresh?.();
    openObjectDetail(collection, created.id, { refresh: opts.refresh });
  });
}

export function parseObjectHash() {
  const m = location.hash.match(/^#obj\/([^/]+)\/([^/]+)$/);
  if (!m) return null;
  return { collection: m[1], id: m[2] };
}

export function clearDrawerStack() {
  drawerStack = [];
}

export function closeObjectDrawer() {
  closeDrawer();
  clearDrawerStack();
  setDrawerState(null);
  if (location.hash.startsWith("#obj/")) {
    history.replaceState(null, "", location.pathname + location.search);
  }
}
