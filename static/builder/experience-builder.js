import { ACTIONS, COMPONENTS, MVP_EDITOR_ADD_OPTIONS, actionTypes, componentTypes } from "./component-registry.js";
import { addBlock, createBuilderDraft, newNodeKey, serializeActions, serializeBlocks } from "./builder-state.js";
import { createBuilderHistory } from "./builder-history.js";
import { updatePreviewFrame, translatedValue } from "./builder-preview.js";
import { csrfHeaders, fetchJson, listRevisions, rollbackRevision, saveDraftRevision } from "./builder-api.js";
import { SUPPORTED_LANGUAGES, languageSelectOptionsHtml, normalizeLanguage } from "../bos/services/languages.js";
import { notifyError, notifySuccess } from "../bos/services/notify.js";

const esc = (value) => String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const textInput = (label, field, value, type = "text") => `<label class="qxb-property"><span>${esc(label)}</span>${type === "textarea" ? `<textarea data-property="${field}" rows="3">${esc(value)}</textarea>` : type === "boolean" ? `<input data-property="${field}" type="checkbox"${value ? " checked" : ""}>` : `<input data-property="${field}" type="${type === "url" || type === "image" ? "url" : "text"}" value="${esc(value)}">`}</label>`;

export function openVisualBuilder(exp, { onClose, onSaved, deferredActions = true } = {}) {
  if (!document.querySelector('link[data-visual-builder-styles]')) {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = "/static/builder/experience-builder.css";
    stylesheet.dataset.visualBuilderStyles = "true";
    document.head.appendChild(stylesheet);
    const responsiveStylesheet = document.createElement("link");
    responsiveStylesheet.rel = "stylesheet";
    responsiveStylesheet.href = "/static/builder/experience-builder-responsive.css";
    responsiveStylesheet.dataset.visualBuilderStyles = "true";
    document.head.appendChild(responsiveStylesheet);
  }
  let history = createBuilderHistory(createBuilderDraft(exp));
  let draft = history.value;
  draft.translations = structuredClone(exp.experience_config?.translations || exp.content?.translations || {});
  history = createBuilderHistory(draft);
  let selected = draft.blocks[0] ? { kind: "block", key: draft.blocks[0].key } : { kind: "page" };
  let locale = normalizeLanguage(draft.branding.language);
  let previewMode = "mobile";
  let autosaveTimer = null;
  let saveSequence = Promise.resolve();
  let dirty = false;
  let revisions = [];
  let activeTab = "edit";
  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay qxb-overlay";

  const currentItem = () => selected.kind === "block"
    ? draft.blocks.find((item) => item.key === selected.key)
    : selected.kind === "action" ? draft.actions.find((item) => item.key === selected.key) : draft;

  const localized = (base, translations, field) => translatedValue(base, translations, locale, field);
  const setLocalized = (base, field, value, translationsKey = "translations") => {
    if (locale === normalizeLanguage(draft.branding.language)) base[field] = value;
    else {
      base[translationsKey] ||= {};
      base[translationsKey][locale] ||= {};
      base[translationsKey][locale][field] = value;
    }
  };

  const setStatus = (text, tone = "") => {
    const el = overlay.querySelector("#qxb-save-status");
    if (el) { el.textContent = text; el.dataset.tone = tone; }
  };

  const persist = async ({ revision = false } = {}) => {
    clearTimeout(autosaveTimer);
    const snapshot = structuredClone(draft);
    setStatus("Saving…", "saving");
    saveSequence = saveSequence.catch(() => {}).then(async () => {
      await fetchJson(`/api/qr-experiences/${exp.id}`, {
        method: "PATCH", headers: csrfHeaders(), body: JSON.stringify({
          name: snapshot.name,
          description: snapshot.description,
          branding: snapshot.branding,
          experience_config: { translations: snapshot.translations || {} },
        }),
      });
      await fetchJson(`/api/qr-experiences/${exp.id}/blocks`, {
        method: "PUT", headers: csrfHeaders(), body: JSON.stringify({ blocks: serializeBlocks(snapshot.blocks) }),
      });
      await fetchJson(`/api/qr-experiences/${exp.id}/actions`, {
        method: "PUT", headers: csrfHeaders(), body: JSON.stringify({ actions: serializeActions(snapshot.actions) }),
      });
      if (revision) await saveDraftRevision(exp.id, "Manual Builder save");
      dirty = false;
      setStatus(revision ? "Version saved" : "Autosaved", "saved");
    }).catch((error) => {
      setStatus("Save failed", "error");
      notifyError(error.message);
      throw error;
    });
    return saveSequence;
  };

  const scheduleSave = () => {
    dirty = true;
    setStatus("Unsaved changes");
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => persist(), 1200);
  };

  const syncDraft = (next, { repaint = true, save = true } = {}) => {
    draft = next;
    if (repaint) paintWorkspace();
    else updatePreview();
    updateHistoryButtons();
    if (save) scheduleSave();
  };

  const change = (mutator, options) => syncDraft(history.update(mutator), options);
  const undo = () => { const value = history.undo(); if (value) syncDraft(value); };
  const redo = () => { const value = history.redo(); if (value) syncDraft(value); };

  const updateHistoryButtons = () => {
    const undoButton = overlay.querySelector("#qxb-undo");
    const redoButton = overlay.querySelector("#qxb-redo");
    if (undoButton) undoButton.disabled = !history.canUndo;
    if (redoButton) redoButton.disabled = !history.canRedo;
  };

  const updatePreview = () => {
    const frame = overlay.querySelector("#qxb-preview-frame");
    updatePreviewFrame(frame, draft, locale);
    const shell = overlay.querySelector("#qxb-preview-shell");
    if (shell) shell.dataset.mode = previewMode;
  };

  const propertyPanel = () => {
    const item = currentItem();
    if (!item) return `<p class="cp-muted">Select an item.</p>`;
    const baseLocale = normalizeLanguage(draft.branding.language);
    const languageNote = locale === baseLocale ? "Default content" : `Translation · ${SUPPORTED_LANGUAGES.find((l) => l.code === locale)?.native || locale}`;
    if (selected.kind === "page") {
      const translation = draft.translations || {};
      return `<p class="qxb-property-note">${esc(languageNote)}</p>
        ${textInput("Page name", "name", localized(draft, translation, "name"))}
        ${textInput("Description", "description", localized(draft, translation, "description"), "textarea")}
        ${textInput("Business name", "business_name", localized(draft.branding, translation, "business_name"))}
        ${textInput("Logo URL", "logo_url", draft.branding.logo_url, "url")}
        ${textInput("Background", "background", draft.branding.background)}
        <label class="qxb-property"><span>Theme</span><select data-property="theme"><option value="light"${draft.branding.theme === "light" ? " selected" : ""}>Light</option><option value="dark"${draft.branding.theme === "dark" ? " selected" : ""}>Dark</option></select></label>
        <label class="qxb-property"><span>Default language</span><select data-property="default_language">${languageSelectOptionsHtml(baseLocale)}</select></label>`;
    }
    if (selected.kind === "block") {
      const spec = COMPONENTS[item.type] || { fields: {} };
      return `<p class="qxb-property-note">${esc(languageNote)}</p>${Object.entries(spec.fields || {}).map(([field, type]) => textInput(field.replaceAll("_", " "), field, localized(item.content || {}, item.content?.translations, field), type)).join("") || `<p class="cp-muted">This component has no editable fields.</p>`}`;
    }
    const spec = ACTIONS[item.type] || { fields: {} };
    return `<p class="qxb-property-note">${esc(languageNote)}</p><label class="qxb-property"><span>Action type</span><select data-property="action_type">${actionTypes(true).map((option) => `<option value="${option.id}"${option.id === item.type ? " selected" : ""}>${esc(option.label)}</option>`).join("")}</select></label>${textInput("Button label", "label", localized({ label: item.label }, item.configuration?.translations, "label"))}${Object.entries(spec.fields || {}).map(([field, type]) => textInput(field.replaceAll("_", " "), `config.${field}`, item.configuration?.[field] || "", type)).join("")}`;
  };

  const bindPropertyPanel = () => {
    overlay.querySelectorAll("[data-property]").forEach((field) => {
      let beforeEdit = null;
      const applyValue = () => {
        const prop = field.dataset.property;
        const value = field.type === "checkbox" ? field.checked : field.value;
        const next = structuredClone(draft);
          const target = selected.kind === "block" ? next.blocks.find((x) => x.key === selected.key) : selected.kind === "action" ? next.actions.find((x) => x.key === selected.key) : next;
          if (!target) return;
          if (selected.kind === "page") {
            if (prop === "logo_url" || prop === "background" || prop === "theme") next.branding[prop] = value;
            else if (prop === "default_language") next.branding.language = normalizeLanguage(value);
            else if (prop === "business_name") setLocalized(next.branding, prop, value);
            else setLocalized(next, prop, value);
          } else if (selected.kind === "block") setLocalized(target.content, prop, value);
          else if (prop === "action_type") target.type = value;
          else if (prop === "label") {
            target.configuration ||= {};
            if (locale === normalizeLanguage(next.branding.language)) target.label = value;
            else {
              target.configuration.translations ||= {};
              target.configuration.translations[locale] ||= {};
              target.configuration.translations[locale].label = value;
            }
          } else if (prop.startsWith("config.")) {
            target.configuration[prop.slice(7)] = value;
          }
        draft = history.replace(next, { record: false });
        updatePreview();
        scheduleSave();
      };
      const commitValue = () => {
        if (!beforeEdit) return;
        draft = history.commitFrom(beforeEdit, draft);
        beforeEdit = null;
        updateHistoryButtons();
      };
      field.addEventListener("focus", () => { beforeEdit = structuredClone(draft); });
      field.addEventListener("input", applyValue);
      field.addEventListener("change", () => {
        applyValue();
        commitValue();
        if (field.dataset.property === "default_language") {
          locale = normalizeLanguage(field.value);
          paintWorkspace();
        } else if (field.dataset.property === "action_type") {
          paintWorkspace();
        }
      });
      field.addEventListener("blur", commitValue);
    });
  };

  const bindDragList = (selector, kind, collection) => {
    let from = -1;
    overlay.querySelectorAll(selector).forEach((row) => {
      row.addEventListener("dragstart", () => { from = Number(row.dataset.index); row.classList.add("is-dragging"); });
      row.addEventListener("dragend", () => row.classList.remove("is-dragging"));
      row.addEventListener("dragover", (event) => { event.preventDefault(); row.classList.add("is-drop-target"); });
      row.addEventListener("dragleave", () => row.classList.remove("is-drop-target"));
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        const to = Number(row.dataset.index);
        row.classList.remove("is-drop-target");
        if (from < 0 || from === to) return;
        change((next) => { const [moved] = next[collection].splice(from, 1); next[collection].splice(to, 0, moved); });
      });
      row.addEventListener("click", () => { selected = { kind, key: row.dataset.key }; paintWorkspace(); });
    });
  };

  const paintWorkspace = () => {
    const body = overlay.querySelector("#qxb-workspace");
    if (!body) return;
    const blockOptions = deferredActions ? componentTypes(true) : MVP_EDITOR_ADD_OPTIONS;
    body.innerHTML = `<aside class="qxb-sidebar"><button class="qxb-page-row${selected.kind === "page" ? " is-selected" : ""}" id="qxb-select-page">▣ Page settings</button><h4>Sections</h4><div>${draft.blocks.map((block, index) => `<div class="qxb-layer${selected.kind === "block" && selected.key === block.key ? " is-selected" : ""}" draggable="true" data-block-row data-index="${index}" data-key="${esc(block.key)}"><span class="qxb-grip">⋮⋮</span><span>${esc(COMPONENTS[block.type]?.label || block.type)}</span><button data-remove-block="${esc(block.key)}" title="Remove">×</button></div>`).join("")}</div><div class="qxb-add"><select id="qxb-add-type">${blockOptions.map((item) => `<option value="${item.id}">${esc(item.label)}</option>`).join("")}</select><button id="qxb-add-block">Add section</button></div><h4>Buttons</h4><div>${draft.actions.map((action, index) => `<div class="qxb-layer${selected.kind === "action" && selected.key === action.key ? " is-selected" : ""}" draggable="true" data-action-row data-index="${index}" data-key="${esc(action.key)}"><span class="qxb-grip">⋮⋮</span><span>${esc(action.label || ACTIONS[action.type]?.label)}</span><button data-remove-action="${esc(action.key)}">×</button></div>`).join("")}</div><button class="qxb-add-action" id="qxb-add-action">+ Add button</button></aside>
      <main class="qxb-canvas"><div class="qxb-preview-toolbar"><button data-preview-mode="mobile" class="${previewMode === "mobile" ? "is-active" : ""}">Mobile</button><button data-preview-mode="desktop" class="${previewMode === "desktop" ? "is-active" : ""}">Desktop</button><span>${esc(locale)}</span></div><div class="qxb-preview-shell" id="qxb-preview-shell" data-mode="${previewMode}"><iframe id="qxb-preview-frame" title="Live customer preview" sandbox="allow-same-origin"></iframe></div></main>
      <aside class="qxb-properties"><div class="qxb-properties-head"><h4>Properties</h4><select id="qxb-content-language" aria-label="Content language">${languageSelectOptionsHtml(locale)}</select></div><div id="qxb-property-fields">${propertyPanel()}</div></aside>`;
    updatePreview();
    bindPropertyPanel();
    body.querySelector("#qxb-select-page")?.addEventListener("click", () => { selected = { kind: "page" }; paintWorkspace(); });
    body.querySelector("#qxb-content-language")?.addEventListener("change", (event) => { locale = normalizeLanguage(event.target.value); paintWorkspace(); });
    body.querySelectorAll("[data-preview-mode]").forEach((button) => button.addEventListener("click", () => { previewMode = button.dataset.previewMode; paintWorkspace(); }));
    bindDragList("[data-block-row]", "block", "blocks");
    bindDragList("[data-action-row]", "action", "actions");
    body.querySelectorAll("[data-remove-block]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); selected = { kind: "page" }; change((next) => { next.blocks = next.blocks.filter((x) => x.key !== button.dataset.removeBlock); }); }));
    body.querySelectorAll("[data-remove-action]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); selected = { kind: "page" }; change((next) => { next.actions = next.actions.filter((x) => x.key !== button.dataset.removeAction); }); }));
    body.querySelector("#qxb-add-block")?.addEventListener("click", () => {
      const select = body.querySelector("#qxb-add-type");
      const option = blockOptions[select.selectedIndex] || blockOptions[0];
      change((next) => { const block = addBlock(next, option.id, option.preset); selected = { kind: "block", key: block.key }; });
    });
    body.querySelector("#qxb-add-action")?.addEventListener("click", () => change((next) => { const action = { key: newNodeKey("act"), type: "open_page", label: "New button", configuration: {} }; next.actions.push(action); selected = { kind: "action", key: action.key }; }));
  };

  const paintRevisions = async () => {
    try { revisions = (await listRevisions(exp.id)).revisions || []; } catch (_) { revisions = []; }
    const body = overlay.querySelector("#qxb-workspace");
    body.innerHTML = `<section class="qxb-revisions"><h3>Publish & versions</h3><p>Publishing creates an immutable customer-facing version.</p><button class="bos-btn bos-btn-primary" id="qxb-publish">Publish current draft</button><div class="qxb-revision-list">${revisions.map((revision) => `<div><span><strong>v${revision.revision_number}</strong> · ${esc(revision.kind)}<small>${esc(revision.note || revision.created_at)}</small></span><button data-restore="${revision.id}">Restore</button></div>`).join("") || `<p>No versions yet.</p>`}</div></section>`;
    body.querySelector("#qxb-publish")?.addEventListener("click", async () => {
      try { await persist(); const published = await fetchJson(`/api/qr-experiences/${exp.id}/publish`, { method: "POST", headers: csrfHeaders(), body: "{}" }); Object.assign(exp, published); notifySuccess("Published"); onSaved?.(published); await paintRevisions(); } catch (error) { notifyError(error.message); }
    });
    body.querySelectorAll("[data-restore]").forEach((button) => button.addEventListener("click", async () => {
      if (!confirm("Restore this version into the editor? The published page stays online.")) return;
      try { const result = await rollbackRevision(exp.id, Number(button.dataset.restore)); draft = createBuilderDraft(result.experience); draft.translations = structuredClone(result.experience?.experience_config?.translations || {}); history = createBuilderHistory(draft); selected = { kind: "page" }; activeTab = "edit"; paint(); notifySuccess("Version restored"); } catch (error) { notifyError(error.message); }
    }));
  };

  const paint = () => {
    overlay.innerHTML = `<div class="qxb-app"><header class="qxb-topbar"><div><strong>${esc(draft.name)}</strong><span id="qxb-save-status">${dirty ? "Unsaved changes" : "All changes saved"}</span></div><div class="qxb-top-actions"><button id="qxb-undo" title="Undo">↶</button><button id="qxb-redo" title="Redo">↷</button><button id="qxb-save-version">Save version</button><button data-builder-tab="edit" class="${activeTab === "edit" ? "is-active" : ""}">Editor</button><button data-builder-tab="publish" class="${activeTab === "publish" ? "is-active" : ""}">Publish</button><button id="qxb-close">Close</button></div></header><div id="qxb-workspace" class="qxb-workspace"></div></div>`;
    overlay.querySelector("#qxb-close").addEventListener("click", async () => { if (dirty) await persist().catch(() => {}); clearTimeout(autosaveTimer); overlay.remove(); onClose?.(); });
    overlay.querySelector("#qxb-undo").addEventListener("click", undo);
    overlay.querySelector("#qxb-redo").addEventListener("click", redo);
    overlay.querySelector("#qxb-save-version").addEventListener("click", async () => { try { await persist({ revision: true }); notifySuccess("Draft version saved"); const updated = await fetchJson(`/api/qr-experiences/${exp.id}`); onSaved?.(updated); } catch (_) {} });
    overlay.querySelectorAll("[data-builder-tab]").forEach((button) => button.addEventListener("click", () => { activeTab = button.dataset.builderTab; activeTab === "edit" ? paintWorkspace() : paintRevisions(); overlay.querySelectorAll("[data-builder-tab]").forEach((item) => item.classList.toggle("is-active", item.dataset.builderTab === activeTab)); }));
    updateHistoryButtons();
    activeTab === "edit" ? paintWorkspace() : paintRevisions();
  };

  const keyboard = (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return;
    event.preventDefault();
    event.shiftKey ? redo() : undo();
  };
  overlay.addEventListener("keydown", keyboard);
  document.body.appendChild(overlay);
  paint();
}
