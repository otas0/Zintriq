import { api, request, toast } from "./universal-api.js";
import { canNest, effectiveStyles, renderCanvas, renderLayers, getBreakpointPosition, setBreakpointPosition } from "./universal-canvas.js";
import { renderLogicGraph, renderConnectionGraph } from "./studio-graph.js";

const root = document.getElementById("ub-editor");
const projectId = Number(root.dataset.projectId);
const canvas = document.getElementById("ub-canvas");
const leftPanel = document.getElementById("ub-left-panel");
const inspector = document.getElementById("ub-inspector");
const fullMode = document.getElementById("ub-full-mode");
const modal = document.getElementById("ub-modal");
const state = { projectId, panel: "pages", overlay: null, overlayContext: null, inspectorTab: "content", breakpoint: "desktop", mode: "structured", locale: "base", selectedKey: null, selectedKeys: [], data: null, nodes: [], bindings: [], actions: [], conditions: [], registry: { components: {}, actions: {} }, recordCache: {}, undo: [], redo: [], dirtyTimer: null };

const esc = (value = "") => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const selectedNode = () => state.nodes.find((item) => item.key === state.selectedKey);
const selectedNodes = () => state.nodes.filter((item) => state.selectedKeys.includes(item.key));
const activeDocument = () => state.data?.active_document;
const activeSurface = () => state.data?.surfaces?.find((item) => item.id === activeDocument()?.surface_id) || state.data?.surfaces?.[0];

function setSaveStatus(text, error = false) { const el = document.getElementById("ub-save-state"); el.textContent = text; el.classList.toggle("is-error", error); }
function updateHistoryButtons() { document.getElementById("ub-undo").disabled = !state.undo.length; document.getElementById("ub-redo").disabled = !state.redo.length; }
function pushHistory(entry) { state.undo.push(entry); if (state.undo.length > 50) state.undo.shift(); state.redo = []; updateHistoryButtons(); }

async function load(documentId = null, { keepSelection = false } = {}) {
  setSaveStatus("Loading…");
  try {
    const data = await api.bootstrap(projectId, documentId);
    state.data = data; state.nodes = data.nodes || []; state.bindings = data.bindings || []; state.actions = data.actions || []; state.conditions = data.conditions || []; state.registry = data.registry;
    const present = new Set(state.nodes.map((node) => node.key));
    state.selectedKeys = keepSelection ? state.selectedKeys.filter((key) => present.has(key)) : [];
    if (!state.selectedKeys.includes(state.selectedKey)) state.selectedKey = state.selectedKeys[state.selectedKeys.length - 1] || null;
    hydrateToolbar(); await loadRecordPreviews(); render(); setSaveStatus("Saved");
  } catch (error) { setSaveStatus("Error", true); toast(error.message, "error"); }
}

async function loadRecordPreviews() {
  const required = [...new Set(state.bindings.filter((item) => item.source_type === "collection").map((item) => item.source_config?.model_key).filter(Boolean))];
  await Promise.all(required.map(async (key) => { try { state.recordCache[key] = (await api.records(projectId, key)).records; } catch { state.recordCache[key] = []; } }));
  const domainSources = [...new Set(state.bindings.filter((item) => item.source_type === "domain").map((item) => item.source_config?.source_id).filter(Boolean))];
  await Promise.all(domainSources.map(async (key) => { try { state.recordCache[key] = (await api.domainData(projectId, key)).records; } catch { state.recordCache[key] = []; } }));
}

function hydrateToolbar() {
  document.getElementById("ub-project-name").value = state.data.name;
  const surfaceSelect = document.getElementById("ub-surface-select");
  if (surfaceSelect) {
    surfaceSelect.innerHTML = state.data.surfaces.map((item) => `<option value="${item.id}" ${item.id === activeSurface()?.id ? "selected" : ""}>${esc(item.name)}</option>`).join("") + '<option value="new">+ New site</option>';
  }
  const pageSelect = document.getElementById("ub-page-select");
  if (pageSelect) {
    const surfaceId = activeSurface()?.id;
    const docs = state.data.documents.filter((item) => item.status === "active" && (!surfaceId || item.surface_id === surfaceId));
    pageSelect.innerHTML = docs.map((item) => `<option value="${item.id}" ${item.id === activeDocument()?.id ? "selected" : ""}>${esc(item.name)}</option>`).join("") + '<option value="new">+ New page</option>';
  }
}

function render() {
  renderLeft(); renderCanvasView(); renderInspector(); renderOverlay(); updateSelectionState();
}

function renderOverlay() {
  if (!state.overlay) { fullMode.classList.add("hidden"); fullMode.innerHTML = ""; return; }
  fullMode.classList.remove("hidden");
  if (state.overlay === "data") renderDataMode(state.overlayContext || state.data.data_models[0]?.model_key);
  if (state.overlay === "design") renderDesignMode();
  if (state.overlay === "workflows") renderWorkflowsMode();
  if (state.overlay === "connection") renderConnectionMode();
  if (state.overlay === "marketplace") renderMarketplaceMode();
  if (state.overlay === "publish") renderPublishMode();
  syncPrimitiveRail();
  if (state.overlay === "component-editor") componentEditor(state.overlayContext);
}

function showOverlay(name, context = null) { state.overlay = name; state.overlayContext = context; renderOverlay(); }
function hideOverlay() { state.overlay = null; state.overlayContext = null; renderOverlay(); }

function studioBase() {
  return document.getElementById("ub-editor")?.dataset.studioBase || "/studio";
}
function communityUrl(packageId = "") {
  const base = document.getElementById("ub-editor")?.dataset.communityUrl || "/app/community";
  if (!packageId) return base;
  const join = base.includes("?") ? "&" : "?";
  return `${base}${join}package=${encodeURIComponent(packageId)}`;
}
function openCommunity(packageId = "") {
  window.location.assign(communityUrl(packageId));
}

function syncPrimitiveRail() {
  document.querySelectorAll("[data-primitive]").forEach((button) => {
    const primitive = button.dataset.primitive;
    let active = false;
    if (primitive === "interface") active = !state.overlay || state.overlay === "design" || state.overlay === "component-editor";
    if (primitive === "data") active = state.overlay === "data";
    if (primitive === "logic") active = state.overlay === "workflows";
    if (primitive === "connection") active = state.overlay === "connection" || state.overlay === "marketplace";
    if (primitive === "publish") active = state.overlay === "publish";
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const grid = document.querySelector(".ub-builder-grid, .ub-compose-grid");
  if (grid) grid.hidden = Boolean(state.overlay);
  const bottombar = document.getElementById("ub-interface-bottombar");
  if (bottombar) bottombar.hidden = Boolean(state.overlay);
}

function openPrimitive(name) {
  if (name === "interface") { hideOverlay(); return; }
  if (name === "data") { showOverlay("data"); return; }
  if (name === "logic") { showOverlay("workflows"); return; }
  if (name === "connection") { showOverlay("connection"); return; }
  if (name === "publish") { showOverlay("publish"); }
}

fullMode.addEventListener("click", (event) => { if (event.target === fullMode) hideOverlay(); });

function updateSelectionState() {
  const el = document.getElementById("ub-selection-state");
  if (!el) return;
  if (state.selectedKeys.length > 1) el.textContent = `${state.selectedKeys.length} elements selected`;
  else if (state.selectedKey) { const node = selectedNode(); el.textContent = node ? (state.registry.components[node.component_type]?.label || node.component_type) : ""; }
  else el.textContent = "";
}

function renderCanvasView() {
  const freeformClass = state.mode === "freeform" ? " ub-canvas--freeform" : "";
  canvas.className = `ub-canvas ub-canvas--${state.breakpoint}${freeformClass}`;
  const canvasSizeEl = document.getElementById("ub-canvas-size");
  if (canvasSizeEl) canvasSizeEl.textContent = state.breakpoint[0].toUpperCase() + state.breakpoint.slice(1);
  const canvasLabelEl = document.getElementById("ub-canvas-label-text");
  if (canvasLabelEl) {
    const widths = { desktop: "1200", tablet: "768", mobile: "390" };
    const modeLabel = state.mode === "freeform" ? " · Free-form" : "";
    canvasLabelEl.textContent = `${state.breakpoint[0].toUpperCase() + state.breakpoint.slice(1)} ${widths[state.breakpoint] || ""}${modeLabel}`;
  }
  if (isOfficialSystem() && !isNativeDocument()) { renderLegacyTemplateCanvas(); return; }
  renderCanvas(canvas, state, { select: selectNode, drop: handleDrop, inlineEdit: updateInline, refresh: renderCanvasView, enter: enterComponent, updatePosition: updateNodePosition });
  canvas.ondragover = (event) => event.preventDefault();
  canvas.ondrop = (event) => handleDrop(event, null);
}

function enterComponent(nodeKey) {
  selectNode(nodeKey);
  toast("Entered component. Use Escape to go back up.", "info");
}

async function updateNodePosition(nodeKey, position) {
  const node = state.nodes.find((n) => n.key === nodeKey);
  if (!node) return;
  const before = { position: node.position };
  const after = { position };
  await applyNodePatch(nodeKey, after, { history: { type: "patch", key: nodeKey, before, after } });
  toast("Position updated", "info");
}

async function captureStructuredPositions() {
  const canvasRect = canvas.getBoundingClientRect();
  const measurements = [];
  canvas.querySelectorAll("[data-node-key]").forEach((el) => {
    const node = state.nodes.find((n) => n.key === el.dataset.nodeKey);
    if (!node) return;
    const pos = node.position || {};
    if (pos.desktop || pos.tablet || pos.mobile || pos.x !== undefined) return;
    const rect = el.getBoundingClientRect();
    measurements.push({
      key: node.key,
      x: Math.round(rect.left - canvasRect.left),
      y: Math.round(rect.top - canvasRect.top),
    });
  });
  if (!measurements.length) return;
  measurements.forEach(({ key, x, y }) => {
    const node = state.nodes.find((n) => n.key === key);
    if (node) node.position = { [state.breakpoint]: { x, y, z: 1 } };
  });
  await Promise.all(measurements.map(({ key, x, y }) =>
    api.updateNode(projectId, key, { position: { [state.breakpoint]: { x, y, z: 1 } } })
  ));
}

function isOfficialSystem() { return state.data?.legacy_source_type === "workspace_system"; }
function isNativeDocument() { return ["hybrid", "native"].includes(activeDocument()?.schema?.migration_status); }

function renderLegacyTemplateCanvas() {
  const page = activeDocument();
  const route = page?.route || "";
  const canPreview = route.startsWith("/") && !route.includes("{") && !route.includes("*") && route !== "/app/builder";
  canvas.innerHTML = `<div class="ub-template-preview">
    <div class="ub-template-preview__bar"><div><span class="ub-badge ub-badge--official">Official template</span><strong>${esc(page?.name || "Business & Customer App")}</strong><small>Live page · ${esc(page?.schema?.adapter || "flask_legacy_bridge")}</small></div>${canPreview ? `<a class="ub-btn" href="${esc(route)}" target="_blank">Open full page</a>` : ""}</div>
    ${canPreview ? `<iframe title="${esc(page?.name || "Template preview")}" src="${esc(route)}"></iframe>` : `<div class="ub-template-preview__empty"><strong>${esc(page?.name || "System module")}</strong><p>This page represents an existing system capability. It remains connected to the same data, routes and permissions through the official template adapter.</p></div>`}
  </div>`;
}

function renderLeft() {
  document.querySelectorAll("[data-panel]").forEach((button) => button.classList.toggle("is-active", button.dataset.panel === state.panel));
  if (state.panel === "add") renderAddPanel();
  if (state.panel === "pages") renderPagesPanel();
  if (state.panel === "layers") renderLayersPanel();
  if (state.panel === "assets") renderAssetsPanel();
  if (state.panel === "components") renderComponentsPanel();
  if (state.panel === "theme") renderThemePanel();
}

function renderThemePanel() {
  const tokens = state.data.design_tokens || [];
  const variables = state.data.project_variables || [];
  leftPanel.innerHTML = `<div class="ub-panel-title"><h2>Design</h2><button type="button" class="ub-btn ub-btn--primary" data-open-design>Open Design System</button></div>
    <p class="ub-dialog__hint">Tokens and variables belong to Interface. Edit them in the Design System overlay.</p>
    <h3 class="ub-panel-section-label">Tokens</h3>
    ${tokens.slice(0, 8).map((item) => `<div class="ub-data-item"><strong>${esc(item.name)}</strong><small>${esc(item.token_key)}</small></div>`).join("") || '<div class="ub-empty-panel"><p>No tokens yet.</p></div>'}
    <h3 class="ub-panel-section-label">Variables</h3>
    ${variables.slice(0, 6).map((item) => `<div class="ub-data-item"><strong>${esc(item.name)}</strong><small>${esc(item.variable_key)}</small></div>`).join("") || '<div class="ub-empty-panel"><p>No variables yet.</p></div>'}`;
  leftPanel.querySelector("[data-open-design]")?.addEventListener("click", () => showOverlay("design"));
}

function renderAddPanel(query = "") {
  if (isOfficialSystem() && !isNativeDocument()) {
    const capabilities = state.data.settings?.capabilities || [];
    leftPanel.innerHTML = `<div class="ub-panel-title"><h2>Template capabilities</h2></div><div class="ub-issue">Official starters ship as one composition. Existing functions stay connected — they are not separate Studio products.</div><div class="ub-template-capabilities">${capabilities.map((item) => `<span>${esc(labelize(item))}</span>`).join("")}</div>`;
    return;
  }
  const enabled = new Set(state.data.enabled_capabilities || []);
  const entries = Object.entries(state.registry.components).filter(([id, spec]) => {
    if (id === "component_instance") return false;
    const haystack = [id, spec.label, spec.category, spec.description, ...(spec.keywords || [])].join(" ").toLowerCase();
    return haystack.includes(query.toLowerCase());
  });
  const groups = Object.groupBy ? Object.groupBy(entries, ([, spec]) => spec.category || "Other") : entries.reduce((map, item) => { const key = item[1].category || "Other"; (map[key] ||= []).push(item); return map; }, {});
  leftPanel.innerHTML = `<div class="ub-panel-title"><h2>Add components</h2></div><input class="ub-search" id="ub-component-search" type="search" placeholder="Search components" value="${esc(query)}">${Object.entries(groups).map(([category, items]) => `<section class="ub-component-group"><h3>${esc(labelize(category))}</h3><div class="ub-component-list">${items.map(([id, spec]) => { const missing = (spec.required_capabilities || []).filter((item) => !enabled.has(item)); return `<button class="ub-component-item" draggable="true" data-add-component="${esc(id)}"><strong>${esc(spec.label)}</strong><small>${esc(spec.kind || "primitive")} · ${esc(spec.description)}</small>${missing.length ? `<span class="ub-capability-lock">Needs ${esc(missing.join(", "))}</span>` : ""}</button>`; }).join("")}</div></section>`).join("") || '<div class="ub-empty-panel"><strong>No matches</strong><p>Try a broader search.</p></div>'}`;
  document.getElementById("ub-component-search").addEventListener("input", (event) => renderAddPanel(event.target.value));
  leftPanel.querySelectorAll("[data-add-component]").forEach((button) => {
    button.addEventListener("click", () => addComponent(button.dataset.addComponent, bestParent()));
    button.addEventListener("dragstart", (event) => { event.dataTransfer.setData("application/x-ub-component", button.dataset.addComponent); event.dataTransfer.effectAllowed = "copy"; });
  });
}

function renderPagesPanel() {
  const surfaces = state.data.surfaces || [];
  const surface = activeSurface();
  const docs = state.data.documents.filter((item) => item.status === "active" && item.surface_id === surface?.id);
  leftPanel.innerHTML = `<div class="ub-panel-title"><h2>${esc(surface?.name || "Web surface")}</h2><button class="ub-icon-btn" data-new-surface title="New surface">＋</button></div><button class="ub-btn" data-new-page>+ New page</button><div class="ub-component-group">${docs.map((item) => `<button class="ub-page-item ${item.id === activeDocument()?.id ? "is-active" : ""}" data-page="${item.id}"><span>▤</span><span>${esc(item.name)}${item.route === "/" ? ' <span class="ub-badge ub-badge--official" title="Homepage">Home</span>' : ""}</span><small>${esc(item.route)}</small></button>`).join("")}</div><div class="ub-section-box"><button class="ub-btn" data-rename-page>Rename</button> <button class="ub-btn" data-route-page>Edit route</button> <button class="ub-btn" data-home-page>Make homepage</button></div><div class="ub-section-box"><button class="ub-btn" data-preview-page>Preview page</button> <button class="ub-btn" data-duplicate-page>Duplicate</button><button class="ub-danger-link" data-delete-page>Archive</button></div><div class="ub-section-box"><button class="ub-btn" data-rename-surface>Rename surface</button></div>`;
  leftPanel.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => load(Number(button.dataset.page))));
  leftPanel.querySelector("[data-new-page]")?.addEventListener("click", createPage);
  leftPanel.querySelector("[data-new-surface]")?.addEventListener("click", createSurface);
  leftPanel.querySelector("[data-rename-page]")?.addEventListener("click", renamePage);
  leftPanel.querySelector("[data-route-page]")?.addEventListener("click", editPageRoute);
  leftPanel.querySelector("[data-home-page]")?.addEventListener("click", setHomepage);
  leftPanel.querySelector("[data-preview-page]")?.addEventListener("click", previewPage);
  leftPanel.querySelector("[data-duplicate-page]")?.addEventListener("click", async () => { try { const page = await api.duplicateDocument(projectId, activeDocument().id); await load(page.id); toast(`Page duplicated → ${page.route}`); } catch (error) { toast(error.message, "error"); } });
  leftPanel.querySelector("[data-delete-page]")?.addEventListener("click", archivePage);
  leftPanel.querySelector("[data-rename-surface]")?.addEventListener("click", renameSurface);
}

function renderLayersPanel() {
  const isFreeform = state.mode === "freeform";
  leftPanel.innerHTML = `<div class="ub-panel-title"><h2>Layers</h2><button class="ub-icon-btn" data-add-section title="Add section">＋</button></div>${isFreeform ? '<small class="ub-dialog__hint" style="padding:0 0 8px">Drag layers to reorder z-index. Higher = on top.</small>' : ""}<div id="ub-layer-tree">${renderLayers(state, { freeform: isFreeform, breakpoint: state.breakpoint })}</div>`;
  leftPanel.querySelectorAll("[data-layer]").forEach((button) => {
    button.draggable = true; button.addEventListener("click", (event) => selectNode(button.dataset.layer, event));
    button.addEventListener("dragstart", (event) => event.dataTransfer.setData("application/x-ub-node", button.dataset.layer));
    button.addEventListener("dragover", (event) => event.preventDefault());
    button.addEventListener("drop", (event) => handleDrop(event, button.dataset.layer));
  });
  leftPanel.querySelectorAll("[data-z-up]").forEach((btn) => btn.addEventListener("click", async (event) => {
    event.stopPropagation();
    const nodeKey = btn.dataset.zUp;
    const node = state.nodes.find((n) => n.key === nodeKey);
    if (!node) return;
    const pos = getBreakpointPosition(node, state.breakpoint);
    const newPos = setBreakpointPosition(node, state.breakpoint, { ...pos, z: (pos.z || 1) + 1 });
    await updateNodePosition(nodeKey, newPos);
  }));
  leftPanel.querySelectorAll("[data-z-down]").forEach((btn) => btn.addEventListener("click", async (event) => {
    event.stopPropagation();
    const nodeKey = btn.dataset.zDown;
    const node = state.nodes.find((n) => n.key === nodeKey);
    if (!node) return;
    const pos = getBreakpointPosition(node, state.breakpoint);
    const newPos = setBreakpointPosition(node, state.breakpoint, { ...pos, z: Math.max(0, (pos.z || 1) - 1) });
    await updateNodePosition(nodeKey, newPos);
  }));
  leftPanel.querySelector("[data-add-section]")?.addEventListener("click", () => addComponent("section", null));
}

function renderAssetsPanel() {
  const images = state.nodes.filter((node) => node.component_type === "image" && node.props?.src);
  leftPanel.innerHTML = `<div class="ub-panel-title"><h2>Assets</h2></div><p class="ub-panel-intro">Images used on this page appear here. Add an Image component to include one.</p><div class="ub-asset-grid">${images.map((node) => `<div class="ub-asset-item" data-asset-node="${esc(node.key)}"><img src="${esc(node.props.src)}" alt="${esc(node.props.alt || "")}" loading="lazy"><span>${esc(node.props.alt || node.props.src.split("/").pop() || "Image")}</span></div>`).join("")}</div>${images.length ? "" : '<div class="ub-empty-panel"><strong>No images yet</strong><p>Add an Image component to the canvas, then it will appear here for reuse.</p></div>'}`;
  leftPanel.querySelectorAll("[data-asset-node]").forEach((el) => el.addEventListener("click", () => { state.panel = "layers"; renderLeft(); selectNode(el.dataset.assetNode); }));
}

function renderComponentsPanel() {
  const definitions = state.data.component_definitions || [];
  leftPanel.innerHTML = `<div class="ub-panel-title"><h2>Components</h2><button class="ub-icon-btn" data-new-component title="Create component">＋</button></div><h3 class="ub-panel-section-label">My Components</h3>${definitions.length ? definitions.map((item) => `<button class="ub-component-list-item" data-edit-def="${item.id}"><strong>${esc(item.name)}</strong><small>${item.usage_count || 0} uses · ${Object.keys(item.variants || {}).length} variants</small></button>`).join("") : '<div class="ub-empty-panel"><p>No reusable components yet. Select layers on the canvas and create a component to reuse them.</p></div>'}<div class="ub-section-box"><h3 class="ub-panel-section-label">Installed</h3><a class="ub-btn" href="#" data-open-community="1">Browse Community</a><button class="ub-btn" type="button" data-open-installed>Manage installed</button></div>`;
  leftPanel.querySelector("[data-new-component]")?.addEventListener("click", () => { if (selectedNode()) createComponentDialog(); else toast("Select layers on the canvas first", "info"); });
  leftPanel.querySelectorAll("[data-edit-def]").forEach((btn) => btn.addEventListener("click", () => showOverlay("component-editor", Number(btn.dataset.editDef))));
  leftPanel.querySelector("[data-open-installed]")?.addEventListener("click", () => showOverlay("marketplace"));
}

function bestParent() { const selected = selectedNode(); return selected && canNest(state, "text", selected.key) ? selected.key : state.nodes.find((item) => item.component_type === "section")?.key || null; }

async function ensureCapabilities(componentType) {
  const required = state.registry.components[componentType]?.required_capabilities || [];
  const enabled = new Set(state.data.enabled_capabilities || []); const missing = required.filter((item) => !enabled.has(item));
  if (!missing.length) return true;
  return new Promise((resolve) => {
    showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Capability</p><h2>Enable ${esc(missing.join(", "))}?</h2></div><button class="ub-icon-btn" data-cancel-enable>×</button></div><p>This component needs ${esc(missing.join(", "))}. Enabling it keeps all other project features available.</p><div class="ub-dialog__actions"><button class="ub-btn" data-cancel-enable>Cancel</button><button class="ub-btn ub-btn--primary" data-enable-capability>Enable and add</button></div>`, () => {
      modal.querySelectorAll("[data-cancel-enable]").forEach((button) => button.addEventListener("click", () => { modal.close(); resolve(false); }));
      modal.querySelector("[data-enable-capability]").addEventListener("click", async () => {
        try {
          const result = await api.updateProject(projectId, { enabled_capabilities: [...enabled, ...missing] });
          state.data.enabled_capabilities = result.enabled_capabilities; modal.close(); resolve(true);
        } catch (error) { toast(error.message, "error"); resolve(false); }
      });
    });
  });
}

async function addComponent(componentType, parentKey = null) {
  try {
    if (!(await ensureCapabilities(componentType))) return;
    if (parentKey && !canNest(state, componentType, parentKey)) {
      const nearestParent = findNearestValidParent(componentType, parentKey);
      if (nearestParent) {
        parentKey = nearestParent;
        toast(`Placed in nearest valid container`, "info");
      } else {
        toast("That component cannot be placed there", "error");
        return;
      }
    }
    setSaveStatus("Saving…");
    const created = await api.createNode(projectId, { document_id: activeDocument().id, component_type: componentType, parent_key: parentKey, order: siblingCount(parentKey) });
    pushHistory({ type: "delete-created", key: created.key }); await load(activeDocument().id); selectNode(created.key); toast(`${state.registry.components[componentType]?.label || componentType} added`);
  } catch (error) { setSaveStatus("Error", true); toast(error.message, "error"); }
}

function findNearestValidParent(componentType, startKey) {
  let current = state.nodes.find((n) => n.key === startKey);
  while (current) {
    if (canNest(state, componentType, current.key)) return current.key;
    current = current.parent_key ? state.nodes.find((n) => n.key === current.parent_key) : null;
  }
  const section = state.nodes.find((n) => n.component_type === "section");
  return section?.key || null;
}

function siblingCount(parentKey) { return state.nodes.filter((item) => (item.parent_key || null) === (parentKey || null)).length; }

async function handleDrop(event, parentKey) {
  const componentType = event.dataTransfer.getData("application/x-ub-component");
  const nodeKey = event.dataTransfer.getData("application/x-ub-node");
  if (componentType) return addComponent(componentType, parentKey);
  if (!nodeKey || nodeKey === parentKey) return;
  const node = state.nodes.find((item) => item.key === nodeKey);
  if (!node) return;
  if (parentKey && !canNest(state, node.component_type, parentKey)) {
    const nearestParent = findNearestValidParent(node.component_type, parentKey);
    if (nearestParent) {
      parentKey = nearestParent;
      toast(`Moved to nearest valid container`, "info");
    } else {
      return toast("Invalid drop location", "error");
    }
  }
  const descendants = descendantsOf(nodeKey); if (parentKey && descendants.includes(parentKey)) return toast("A component cannot contain itself", "error");
  const before = { parent_key: node.parent_key, order: node.order }; const after = { parent_key: parentKey, order: siblingCount(parentKey) };
  await applyNodePatch(nodeKey, after, { history: { type: "patch", key: nodeKey, before, after } });
}

function descendantsOf(key) { const result = []; const visit = (parent) => state.nodes.filter((item) => item.parent_key === parent).forEach((child) => { result.push(child.key); visit(child.key); }); visit(key); return result; }

function setSelection(keys) { state.selectedKeys = [...keys]; state.selectedKey = keys.length ? keys[keys.length - 1] : null; }

function selectNode(key, event) {
  const additive = event && (event.metaKey || event.ctrlKey) && key;
  if (additive) {
    const index = state.selectedKeys.indexOf(key);
    if (index >= 0) { const keys = state.selectedKeys.slice(); keys.splice(index, 1); setSelection(keys); }
    else setSelection([...state.selectedKeys, key]);
  } else {
    setSelection(key ? [key] : []);
  }
  renderCanvasView(); if (state.panel === "layers") renderLayersPanel(); renderInspector();
}

function selectAllNodes() { setSelection(state.nodes.map((node) => node.key)); renderCanvasView(); if (state.panel === "layers") renderLayersPanel(); renderInspector(); }

async function updateInline(key, property, value) {
  const node = state.nodes.find((item) => item.key === key);
  if (!node) return;
  if (state.locale !== "base") {
    const before = structuredClone(node.translations || {}); const translations = structuredClone(node.translations || {});
    translations[state.locale] = { ...(translations[state.locale] || {}), [property]: value };
    return applyNodePatch(key, { translations }, { history: { type: "patch", key, before: { translations: before }, after: { translations } } });
  }
  if (node.props[property] === value) return;
  const before = { props: { ...node.props } }; const props = { ...node.props, [property]: value }; const after = { props };
  await applyNodePatch(key, after, { history: { type: "patch", key, before, after } });
}

async function applyNodePatch(key, patch, { history = null, quiet = false } = {}) {
  const node = state.nodes.find((item) => item.key === key); if (!node) return;
  if (history) pushHistory(history); Object.assign(node, patch); setSaveStatus("Saving…"); renderCanvasView();
  try { await api.updateNode(projectId, key, patch); setSaveStatus("Saved"); if (!quiet) renderInspector(); }
  catch (error) { setSaveStatus("Error", true); toast(error.message, "error"); await load(activeDocument().id, { keepSelection: true }); }
}

function scheduleNodePatch(key, section, values, before) {
  const node = state.nodes.find((item) => item.key === key); node[section] = values; setSaveStatus("Saving…"); renderCanvasView();
  clearTimeout(state.dirtyTimer); state.dirtyTimer = setTimeout(async () => {
    const after = { [section]: { ...values } }; pushHistory({ type: "patch", key, before: { [section]: before }, after });
    try { await api.updateNode(projectId, key, after); setSaveStatus("Saved"); }
    catch (error) { setSaveStatus("Error", true); toast(error.message, "error"); }
  }, 500);
}

function renderInspector() {
  if (state.selectedKeys.length > 1) { renderMultiInspector(); return; }
  const node = selectedNode();
  if (!node) {
    if (isOfficialSystem() && !isNativeDocument()) {
      const entrypoints = state.data.settings?.template_entrypoints || {};
      inspector.innerHTML = `<div class="ub-inspector__head"><h2>Official starter</h2><p>Composition template</p></div><div class="ub-inspector-body"><div class="ub-issue">Published customer surfaces use /build/&lt;slug&gt;. Business ops open under /manage/&lt;store&gt;.</div><a class="ub-btn ub-btn--primary ub-block-btn" href="${esc(entrypoints.business || "/app/builder")}">Open operations</a><a class="ub-btn ub-block-btn" href="${esc(entrypoints.customer || "/app/builder")}" target="_blank">Open published surface</a><div class="ub-section-box"><strong>Template runtime</strong><p>Compatibility adapter keeps existing routes and data authoritative while native composition documents evolve.</p></div></div>`;
      return;
    }
    inspector.innerHTML = '<div class="ub-empty-panel"><strong>Select a layer</strong><p>Pick something on the canvas or in Layers to edit Interface props, Data bindings, and Logic actions.</p></div>'; return;
  }
  if (node.component_type === "component_instance") { renderInstanceInspector(node); return; }
  const spec = state.registry.components[node.component_type] || {};
  const tabs = ["content", "design", "layout", "responsive", "data", "actions", "motion", "visibility", "advanced"];
  const hasChildren = state.nodes.some((item) => item.parent_key === node.key);
  const isNav = node.component_type === "navigation";
  inspector.innerHTML = `<div class="ub-inspector__head"><h2>${esc(spec.label || node.component_type)}</h2><p>${esc(node.metadata?.display_label || spec.label || node.component_type)}</p>${isNav ? '<button class="ub-btn" data-nav-editor>Edit links</button>' : ""}${hasChildren ? '<button class="ub-btn" data-ungroup>Ungroup</button>' : ""}</div><div class="ub-inspector-tabs">${tabs.map((tab) => `<button class="${tab === state.inspectorTab ? "is-active" : ""}" data-inspector-tab="${tab}">${tab[0].toUpperCase() + tab.slice(1)}</button>`).join("")}</div><div class="ub-inspector-body" id="ub-inspector-body"></div>`;
  inspector.querySelector("[data-nav-editor]")?.addEventListener("click", () => navigationEditor(node));
  inspector.querySelector("[data-ungroup]")?.addEventListener("click", ungroupSelection);
  inspector.querySelectorAll("[data-inspector-tab]").forEach((button) => button.addEventListener("click", () => { state.inspectorTab = button.dataset.inspectorTab; renderInspector(); }));
  const body = document.getElementById("ub-inspector-body");
  if (state.inspectorTab === "content") renderContentInspector(body, node, spec);
  if (["design", "layout", "responsive"].includes(state.inspectorTab)) renderStyleInspector(body, node, spec);
  if (state.inspectorTab === "data") renderDataInspector(body, node, spec);
  if (state.inspectorTab === "actions") renderActionsInspector(body, node, spec);
  if (state.inspectorTab === "motion") renderMotionInspector(body, node);
  if (state.inspectorTab === "visibility") renderVisibilityInspector(body, node);
  if (state.inspectorTab === "advanced") renderAdvancedInspector(body, node);
}

function renderMultiInspector() {
  const nodes = selectedNodes();
  const labels = nodes.map((node) => state.registry.components[node.component_type]?.label || node.component_type);
  inspector.innerHTML = `<div class="ub-inspector__head"><h2>${nodes.length} elements selected</h2><p>Multi-selection</p></div><div class="ub-inspector-body"><div class="ub-section-box"><button class="ub-btn ub-block-btn" data-multi-duplicate>Duplicate all</button><button class="ub-btn ub-block-btn" data-multi-group>Group into section</button><button class="ub-danger-link" data-multi-delete>Delete all</button></div><div class="ub-section-box"><strong>Selected</strong><p>${esc(labels.join(", "))}</p></div><div class="ub-issue">Group, duplicate and delete apply to the whole selection as a single undo step.</div></div>`;
  inspector.querySelector("[data-multi-duplicate]").addEventListener("click", duplicateSelected);
  inspector.querySelector("[data-multi-group]").addEventListener("click", groupSelection);
  inspector.querySelector("[data-multi-delete]").addEventListener("click", deleteSelected);
}

function renderInstanceInspector(node) {
  const instance=(state.data.component_instances||[]).find((item)=>item.node_key===node.key); const definition=(state.data.component_definitions||[]).find((item)=>item.id===instance?.component_definition_id);
  if(!instance||!definition){inspector.innerHTML='<div class="ub-empty-panel"><strong>Missing component</strong><p>This instance needs repair.</p></div>';return;}
  const exposed=definition.property_schema?.properties||{};
  inspector.innerHTML=`<div class="ub-inspector__head"><h2>${esc(definition.name)}</h2><p>Reusable component · ${Object.keys(instance.overrides||{}).length?"Overridden":"Inherited"}</p></div><div class="ub-inspector-body"><label class="ub-field"><span>Variant</span><select id="ub-instance-variant">${Object.entries(definition.variants||{}).map(([key,value])=>`<option value="${esc(key)}" ${instance.variant===key?"selected":""}>${esc(value.label||labelize(key))}</option>`).join("")}</select></label>${Object.entries(exposed).map(([key,schema])=>{const overridden=Object.hasOwn(instance.overrides||{},key);const value=overridden?instance.overrides[key]:"";return `<label class="ub-field"><span class="ub-field__hint"><span>${esc(schema.label||labelize(key))} <small>${overridden?"Overridden":"Inherited"}</small></span>${overridden?`<button class="ub-danger-link" data-reset-override="${esc(key)}">Reset</button>`:""}</span>${schema.type==="boolean"?`<select data-instance-override="${esc(key)}"><option value="">Inherit</option><option value="true" ${value===true?"selected":""}>Show</option><option value="false" ${value===false?"selected":""}>Hide</option></select>`:`<input data-instance-override="${esc(key)}" value="${esc(value)}" placeholder="Inherited from component">`}</label>`;}).join("")}<div class="ub-section-box"><strong>Slots</strong>${Object.entries(definition.slots||{}).map(([key,value])=>`<div class="ub-action-card"><strong>${esc(labelize(key))}</strong><small>${(value.accepts||[]).join(", ")}</small><button class="ub-btn" data-add-slot-content="${esc(key)}">Add content</button></div>`).join("")||'<p>No instance slots.</p>'}</div><div class="ub-section-box"><button class="ub-btn" data-edit-definition>Edit component</button> <button class="ub-btn ub-btn--danger" data-detach-instance>Detach instance</button></div></div>`;
  document.getElementById("ub-instance-variant").addEventListener("change",async(event)=>{await api.updateInstance(projectId,node.key,{variant:event.target.value});await load(activeDocument().id,{keepSelection:true});});
  inspector.querySelectorAll("[data-instance-override]").forEach((input)=>input.addEventListener("change",async()=>{let value=input.value;if(value==="true"||value==="false")value=value==="true";if(value==="")return;await api.updateInstance(projectId,node.key,{overrides:{...(instance.overrides||{}),[input.dataset.instanceOverride]:value}});await load(activeDocument().id,{keepSelection:true});}));
  inspector.querySelectorAll("[data-reset-override]").forEach((button)=>button.addEventListener("click",async()=>{const overrides={...(instance.overrides||{})};delete overrides[button.dataset.resetOverride];await api.updateInstance(projectId,node.key,{overrides});await load(activeDocument().id,{keepSelection:true});}));
  inspector.querySelector("[data-edit-definition]").addEventListener("click",()=>{showOverlay("component-editor",definition.id);});
  inspector.querySelectorAll("[data-add-slot-content]").forEach((button)=>button.addEventListener("click",async()=>{const created=await api.createNode(projectId,{document_id:activeDocument().id,component_type:"button",parent_key:node.key,slot:button.dataset.addSlotContent,props:{label:"Slot action"},order:state.nodes.filter((item)=>item.parent_key===node.key).length});await load(activeDocument().id);selectNode(created.key);toast("Slot content added");}));
  inspector.querySelector("[data-detach-instance]").addEventListener("click",async()=>{if(!confirm("Detach this instance into ordinary layers? The source component will not change."))return;await api.detachInstance(projectId,node.key);await load(activeDocument().id);toast("Instance detached");});
}

function renderMotionInspector(body,node){const items=(state.data.interactions||[]).filter((item)=>item.node_key===node.key);body.innerHTML=`${items.map((item)=>`<div class="ub-action-card"><strong>${esc(labelize(item.trigger_type))}</strong><p>${esc(labelize(item.interaction_type))}</p></div>`).join("")||'<div class="ub-empty-panel"><strong>No motion yet</strong><p>Add declarative motion without JavaScript.</p></div>'}<label class="ub-field">Trigger<select id="ub-motion-trigger"><option>entrance</option><option>hover</option><option>press</option><option>focus</option><option>scroll_reveal</option></select></label><label class="ub-field">Preset<select id="ub-motion-type"><option value="fade">Fade</option><option value="slide-up">Slide Up</option><option value="scale">Scale</option><option value="press">Press</option></select></label><label class="ub-field">State background<input id="ub-motion-background" list="ub-motion-token-list" placeholder="Optional color or token:color.brand.primary"><datalist id="ub-motion-token-list">${(state.data.design_tokens||[]).filter((item)=>item.category==="color").map((item)=>`<option value="token:${esc(item.token_key)}">`).join("")}</datalist></label><button class="ub-btn ub-btn--primary" data-add-motion>Add interaction</button><div class="ub-issue">Published pages respect reduced-motion preferences.</div>`;body.querySelector("[data-add-motion]").addEventListener("click",async()=>{const background=document.getElementById("ub-motion-background").value;await api.saveInteraction(projectId,{document_id:activeDocument().id,node_key:node.key,trigger:document.getElementById("ub-motion-trigger").value,type:document.getElementById("ub-motion-type").value,configuration:{duration:"token:duration.normal",easing:"token:easing.standard",styles:background?{background}: {}}});await load(activeDocument().id,{keepSelection:true});});}

function fieldControl(key, schema, value) {
  const editor = schema.editor || schema.type;
  if (editor === "boolean") return `<label class="ub-field"><span>${esc(labelize(key))}</span><select data-prop="${esc(key)}"><option value="true" ${value ? "selected" : ""}>Yes</option><option value="false" ${!value ? "selected" : ""}>No</option></select></label>`;
  if (editor === "textarea" || editor === "richtext") return `<label class="ub-field"><span>${esc(labelize(key))}</span><textarea rows="4" data-prop="${esc(key)}">${esc(value || "")}</textarea></label>`;
  if (schema.enum) return `<label class="ub-field"><span>${esc(labelize(key))}</span><select data-prop="${esc(key)}">${schema.enum.map((opt) => `<option value="${esc(opt)}" ${value === opt ? "selected" : ""}>${esc(labelize(opt))}</option>`).join("")}</select></label>`;
  if (editor === "select") return `<label class="ub-field"><span>${esc(labelize(key))}</span><input data-prop="${esc(key)}" value="${esc(value ?? "")}"></label>`;
  return `<label class="ub-field"><span>${esc(labelize(key))}</span><input type="${editor === "url" ? "url" : schema.type === "number" ? "number" : "text"}" data-prop="${esc(key)}" value="${esc(value ?? "")}"></label>`;
}

function renderContentInspector(body, node, spec) {
  const fields = spec.property_schema?.properties || {};
  const localized = state.locale === "base" ? node.props : { ...node.props, ...((node.translations || {})[state.locale] || {}) };
  body.innerHTML = `<label class="ub-field"><span>Content language</span><select id="ub-content-locale"><option value="base">Default</option>${[["zh-Hans","简体中文"],["zh-Hant","繁體中文"],["ja","日本語"],["ms","Bahasa Melayu"],["id","Bahasa Indonesia"],["ko","한국어"],["th","ไทย"],["vi","Tiếng Việt"],["fil","Filipino"],["es","Español"],["pt-BR","Português (Brasil)"],["fr","Français"],["de","Deutsch"],["ar","العربية"],["sv","Svenska"]].map(([value,label]) => `<option value="${value}" ${state.locale === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>${state.locale !== "base" ? '<div class="ub-issue">Localized values override the default language. Empty fields continue to use the default.</div>' : ""}${Object.entries(fields).map(([key, schema]) => fieldControl(key, schema, localized?.[key])).join("") || '<div class="ub-empty-panel"><strong>No content settings</strong><p>Use Design or Layout for this component.</p></div>'}`;
  if (node.component_type === "app_module") {
    const input = body.querySelector('[data-prop="module_id"]');
    if (input) input.outerHTML = `<select data-prop="module_id">${Object.values(state.data.app_module_registry || {}).map((item) => `<option value="${esc(item.id)}" ${item.id === localized.module_id ? "selected" : ""}>${esc(item.name)}</option>`).join("")}</select>`;
    const module = state.data.app_module_registry?.[localized.module_id];
    if (module?.manager_url) body.insertAdjacentHTML("beforeend", `<a class="ub-btn ub-block-btn" href="${esc(module.manager_url)}" target="_blank">Open ${esc(module.name)}</a>`);
  }
  if (node.component_type === "form") {
    const collections = state.data.data_models || [];
    const targetInput = body.querySelector('[data-prop="target_model"]');
    if (targetInput) {
      targetInput.outerHTML = `<label class="ub-field"><span>${esc(labelize("target_model"))}</span><select data-prop="target_model"><option value="">— choose a collection —</option>${collections.map((m) => `<option value="${esc(m.model_key)}" ${localized?.target_model === m.model_key ? "selected" : ""}>${esc(m.name)}</option>`).join("")}</select></label>`;
      const selectedModel = collections.find((m) => m.model_key === localized?.target_model);
      if (selectedModel) {
        const fieldKeys = Object.keys(selectedModel.schema?.properties || {});
        body.insertAdjacentHTML("beforeend", `<div class="ub-binding-preview"><strong>Fields in ${esc(selectedModel.name)}</strong>${fieldKeys.length ? `<ul class="ub-binding-field-list">${fieldKeys.map((key) => `<li><code>${esc(key)}</code><small>${esc(selectedModel.schema.properties[key]?.type || "string")}</small></li>`).join("")}</ul>` : '<p class="ub-binding-preview__empty">This collection has no fields.</p>'}</div>`);
      } else if (collections.length) {
        body.insertAdjacentHTML("beforeend", '<div class="ub-issue">Choose a collection to receive form submissions. The form fields below should match the collection\'s fields.</div>');
      } else {
        body.insertAdjacentHTML("beforeend", '<div class="ub-issue"><strong>No collections yet</strong><p>Create a collection in the Data tab first.</p></div>');
      }
    }
    const formFields = state.nodes.filter((n) => n.parent_key === node.key && n.component_type === "form_field").sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    body.insertAdjacentHTML("beforeend", `<div class="ub-section-box"><div class="ub-panel-title"><h3>Form fields</h3><button class="ub-btn" data-add-form-field>+ Add field</button></div>${formFields.length ? formFields.map((field) => `<div class="ub-action-card"><div class="ub-action-card__head"><strong>${esc(field.props?.label || "Field")}</strong><button class="ub-danger-link" data-remove-form-field="${esc(field.key)}">Remove</button></div><small>${esc(field.props?.field_name || "unnamed")} · ${esc(field.props?.field_type || "text")}${field.props?.required ? " · required" : ""}</small></div>`).join("") : '<div class="ub-empty-panel"><strong>No form fields yet</strong><p>Add fields to collect data from visitors.</p></div>'}</div>`);
    body.querySelector("[data-add-form-field]")?.addEventListener("click", async () => {
      const order = state.nodes.filter((n) => n.parent_key === node.key).length;
      await api.createNode(projectId, { document_id: activeDocument().id, component_type: "form_field", parent_key: node.key, props: { label: "New field", field_name: "field", field_type: "text" }, order });
      await load(activeDocument().id, { keepSelection: true }); toast("Form field added");
    });
    body.querySelectorAll("[data-remove-form-field]").forEach((btn) => btn.addEventListener("click", async () => { await api.deleteNode(projectId, btn.dataset.removeFormField); await load(activeDocument().id, { keepSelection: true }); toast("Field removed"); }));
  }
  document.getElementById("ub-content-locale").addEventListener("change", (event) => { state.locale = event.target.value; renderInspector(); });
  body.querySelectorAll("[data-prop]").forEach((input) => {
    input.addEventListener("input", () => {
      let value = input.value; if (input.tagName === "SELECT" && ["true", "false"].includes(value)) value = value === "true";
      if (state.locale === "base") { const before = { ...node.props }; scheduleNodePatch(node.key, "props", { ...node.props, [input.dataset.prop]: value }, before); }
      else { const before = structuredClone(node.translations || {}); const translations = structuredClone(node.translations || {}); translations[state.locale] = { ...(translations[state.locale] || {}), [input.dataset.prop]: value }; scheduleNodePatch(node.key, "translations", translations, before); }
    });
  });
}

const STYLE_GROUPS = { design: ["color", "background", "fontSize", "fontWeight", "textAlign", "borderRadius", "border", "boxShadow", "opacity"], layout: ["display", "width", "minWidth", "maxWidth", "height", "minHeight", "padding", "margin", "gap", "flexDirection", "flexWrap", "alignItems", "justifyContent", "gridTemplateColumns", "position", "top", "right", "bottom", "left", "overflow"] };
function renderStyleInspector(body, node) {
  const responsive = state.inspectorTab === "responsive"; const target = responsive ? { ...((node.responsive || {})[state.breakpoint] || {}) } : { ...node.styles };
  const keys = responsive ? [...STYLE_GROUPS.design, ...STYLE_GROUPS.layout] : STYLE_GROUPS[state.inspectorTab];
  const tokens=(state.data.design_tokens||[]);
  const isFreeform = state.mode === "freeform";
  const pos = isFreeform ? getBreakpointPosition(node, state.breakpoint) : null;
  body.innerHTML = `${isFreeform && state.inspectorTab === "layout" ? `<div class="ub-section-box"><h3>Free-form position</h3><small class="ub-dialog__hint">Position is stored per viewport. Drag on canvas or enter values here.</small><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--ub-space-sm)"><label class="ub-field"><span>X</span><input type="number" data-pos="x" value="${pos?.x || 0}"></label><label class="ub-field"><span>Y</span><input type="number" data-pos="y" value="${pos?.y || 0}"></label><label class="ub-field"><span>Layer (z)</span><input type="number" data-pos="z" value="${pos?.z || 1}" min="0" max="999"></label></div><small class="ub-dialog__hint">Higher z values appear on top. Current viewport: ${esc(state.breakpoint)}</small></div>` : ""}${responsive ? `<div class="ub-issue">Editing ${esc(state.breakpoint)} overrides. Empty values inherit from the base style.</div>` : '<div class="ub-issue">Choose a shared token or enter a custom value.</div>'}<datalist id="ub-token-values">${tokens.map((token)=>`<option value="token:${esc(token.token_key)}">${esc(token.name)}</option>`).join("")}</datalist>${keys.map((key) => `<label class="ub-field"><span class="ub-field__hint"><span>${esc(labelize(key))}</span>${responsive && key in target ? `<button class="ub-danger-link" data-reset-style="${key}">Reset</button>` : ""}</span><input data-style="${key}" list="ub-token-values" value="${esc(target[key] ?? "")}" placeholder="${esc(effectiveStyles(node, state.breakpoint)[key] || "Default")}">${String(target[key]||"").startsWith("token:")?'<small>Connected to Design System</small>':""}</label>`).join("")}`;
  if (isFreeform && state.inspectorTab === "layout") {
    body.querySelectorAll("[data-pos]").forEach((input) => input.addEventListener("change", async () => {
      const currentPos = getBreakpointPosition(node, state.breakpoint);
      const updated = { ...currentPos, [input.dataset.pos]: Number(input.value) };
      const newPosition = setBreakpointPosition(node, state.breakpoint, updated);
      await updateNodePosition(node.key, newPosition);
    }));
  }
  body.querySelectorAll("[data-style]").forEach((input) => input.addEventListener("input", () => {
    if (responsive) { const before = structuredClone(node.responsive || {}); const values = { ...target }; if (input.value) values[input.dataset.style] = input.value; else delete values[input.dataset.style]; scheduleNodePatch(node.key, "responsive", { ...(node.responsive || {}), [state.breakpoint]: values }, before); }
    else { const before = { ...node.styles }; const values = { ...node.styles }; if (input.value) values[input.dataset.style] = input.value; else delete values[input.dataset.style]; scheduleNodePatch(node.key, "styles", values, before); }
  }));
  body.querySelectorAll("[data-reset-style]").forEach((button) => button.addEventListener("click", async () => { const before = structuredClone(node.responsive || {}); const next = structuredClone(node.responsive || {}); delete next[state.breakpoint]?.[button.dataset.resetStyle]; await applyNodePatch(node.key, { responsive: next }, { history: { type: "patch", key: node.key, before: { responsive: before }, after: { responsive: next } } }); }));
}

function renderDataInspector(body, node) {
  const binding = state.bindings.find((item) => item.node_key === node.key);
  const componentSpec = state.registry.components[node.component_type] || {};
  const properties = Object.keys(componentSpec.property_schema?.properties || {});
  const acceptsItems = ["repeater", "store_grid"].includes(node.component_type);
  const collections = state.data.data_models || [];
  const domainSources = Object.values(state.data.data_source_registry || {});
  body.innerHTML = `<div class="ub-binding-intro"><strong>Connect data</strong><p>Link a property on this ${esc(componentSpec.label || node.component_type)} to real data from a collection, domain source, or page state.</p></div><label class="ub-field"><span>Property to connect</span><select id="ub-binding-property">${properties.map((key) => `<option value="${esc(key)}" ${binding?.binding_key === key ? "selected" : ""}>${esc(labelize(key))}</option>`).join("")}${acceptsItems ? '<option value="items" selected>items (repeat over records)</option>' : ""}</select></label><label class="ub-field"><span>Data source</span><select id="ub-binding-source"><option value="static" ${!binding ? "selected" : ""}>Static — use the content value</option><option value="collection" ${binding?.source_type === "collection" ? "selected" : ""}>Composition collection</option><option value="domain" ${binding?.source_type === "domain" ? "selected" : ""}>Connected domain data</option><option value="item" ${binding?.source_type === "item" ? "selected" : ""}>Current repeater item</option><option value="state" ${binding?.source_type === "state" ? "selected" : ""}>Page state</option></select></label><div id="ub-binding-config"></div>${binding ? `<div class="ub-binding-card"><strong>Connected</strong><p>${esc(binding.source_type === "collection" ? "Builder collection" : binding.source_type === "domain" ? "Existing app data" : binding.source_type)} → ${esc(binding.source_config?.model_key || binding.source_config?.source_id || binding.source_config?.path || "value")}</p><button class="ub-danger-link" data-remove-binding>Disconnect</button></div>` : ""}`;
  const config = document.getElementById("ub-binding-config"); const source = document.getElementById("ub-binding-source");
  const paint = () => {
    if (source.value === "collection") {
      const selectedKey = binding?.source_config?.model_key || collections[0]?.model_key || "";
      const selectedModel = collections.find((m) => m.model_key === selectedKey);
      const fields = Object.entries(selectedModel?.schema?.properties || {});
      config.innerHTML = `<label class="ub-field"><span>Choose a collection</span><select id="ub-source-value">${collections.map((m) => `<option value="${esc(m.model_key)}" ${m.model_key === selectedKey ? "selected" : ""}>${esc(m.name)}</option>`).join("") || '<option disabled>No collections yet</option>'}</select></label>${selectedModel ? `<div class="ub-binding-preview"><strong>Fields in ${esc(selectedModel.name)}</strong>${fields.length ? `<ul class="ub-binding-field-list">${fields.map(([key, schema]) => `<li><code>${esc(key)}</code><small>${esc(schema.type || "string")}</small></li>`).join("")}</ul>` : '<p class="ub-binding-preview__empty">This collection has no fields yet.</p>'}</div>` : ""}${collections.length ? '<button class="ub-btn ub-btn--primary" data-connect>Connect collection</button>' : '<div class="ub-empty-panel"><strong>No collections yet</strong><p>Create a collection in the Data tab first, then come back to connect it.</p></div>'}`;
      config.querySelector("#ub-source-value")?.addEventListener("change", () => paint());
    } else if (source.value === "domain") {
      config.innerHTML = `<label class="ub-field"><span>Choose a data source</span><select id="ub-source-value">${domainSources.map((item) => `<option value="${esc(item.id)}" ${binding?.source_config?.source_id === item.id ? "selected" : ""}>${esc(item.namespace)} · ${esc(item.name)}</option>`).join("") || '<option disabled>No domain sources</option>'}</select></label>${domainSources.length ? '<button class="ub-btn ub-btn--primary" data-connect>Connect existing data</button>' : '<div class="ub-empty-panel"><strong>No existing data sources</strong><p>Domain data sources come from installed capabilities.</p></div>'}`;
    } else if (source.value === "item") {
      config.innerHTML = '<label class="ub-field"><span>Field path on current item</span><input id="ub-source-value" placeholder="e.g. name, email, price" value="' + esc(binding?.source_config?.path || "") + '"></label><small class="ub-dialog__hint">Use the field names from the collection connected to the parent Repeater.</small><button class="ub-btn ub-btn--primary" data-connect>Connect field</button>';
    } else if (source.value === "state") {
      config.innerHTML = '<label class="ub-field"><span>State key</span><input id="ub-source-value" placeholder="e.g. selectedItem, isLoggedIn" value="' + esc(binding?.source_config?.path || "") + '"></label><button class="ub-btn ub-btn--primary" data-connect>Connect state</button>';
    } else {
      config.innerHTML = '<p class="ub-empty-panel">This property uses its static content value. Choose a data source above to connect live data instead.</p>';
    }
    config.querySelector("[data-connect]")?.addEventListener("click", saveBinding);
  };
  source.addEventListener("change", paint); paint();
  body.querySelector("[data-remove-binding]")?.addEventListener("click", async () => { await api.deleteBinding(projectId, binding.id); await load(activeDocument().id, { keepSelection: true }); toast("Data disconnected"); });
  if (acceptsItems) {
    const repeaterSection = document.createElement("div");
    repeaterSection.className = "ub-section-box";
    const limit = node.props?.limit || "";
    const sortField = node.props?.sort_field || "";
    const sortDir = node.props?.sort_direction || "asc";
    const emptyText = node.props?.empty_text || "";
    repeaterSection.innerHTML = `<h3>Display options</h3><label class="ub-field"><span>Maximum items</span><input type="number" min="1" max="100" data-repeater-prop="limit" value="${esc(limit)}" placeholder="All"></label><label class="ub-field"><span>Sort by field</span><input data-repeater-prop="sort_field" value="${esc(sortField)}" placeholder="e.g. date, name, order"></label><label class="ub-field"><span>Sort direction</span><select data-repeater-prop="sort_direction"><option value="asc" ${sortDir === "asc" ? "selected" : ""}>Ascending (A→Z, 1→9)</option><option value="desc" ${sortDir === "desc" ? "selected" : ""}>Descending (Z→A, 9→1)</option></select></label><label class="ub-field"><span>Empty message</span><input data-repeater-prop="empty_text" value="${esc(emptyText)}" placeholder="No items yet"></label><small class="ub-dialog__hint">These settings control how connected records are shown. Sorting and limits apply to the preview and published page.</small>`;
    body.appendChild(repeaterSection);
    repeaterSection.querySelectorAll("[data-repeater-prop]").forEach((input) => {
      input.addEventListener("change", () => {
        const prop = input.dataset.repeaterProp;
        const value = input.type === "number" ? (input.value ? Number(input.value) : null) : input.value;
        const before = { ...node.props }; const after = { ...node.props, [prop]: value || null };
        if (!after[prop]) delete after[prop];
        applyNodePatch(node.key, { props: after }, { history: { type: "patch", key: node.key, before: { props: before }, after: { props: after } } });
      });
    });
  }
}

async function saveBinding() {
  const node = selectedNode(); const sourceType = document.getElementById("ub-binding-source").value; const value = document.getElementById("ub-source-value")?.value;
  const sourceConfig = sourceType === "domain" ? { source_id: value, query: {} } : sourceType === "collection" ? { model_key: value } : { path: value };
  await api.saveBinding(projectId, { document_id: activeDocument().id, node_key: node.key, binding_key: document.getElementById("ub-binding-property").value, source_type: sourceType, source_config: sourceConfig });
  await load(activeDocument().id, { keepSelection: true }); toast("Data connected");
}

function renderActionsInspector(body, node) {
  const items = state.actions.filter((item) => item.node_key === node.key).sort((a, b) => a.sort_order - b.sort_order);
  const actions = state.registry.actions;
  body.innerHTML = `<div class="ub-panel-title"><h2>On interaction</h2><button class="ub-icon-btn" data-add-action>＋</button></div>${items.map((item, index) => `<div class="ub-action-card"><div class="ub-action-card__head"><strong>${index + 1}. ${esc(actions[item.action_type]?.label || item.action_type)}</strong><span><button class="ub-icon-btn" data-move-action="${item.id}" data-direction="-1" ${index === 0 ? "disabled" : ""}>↑</button><button class="ub-icon-btn" data-move-action="${item.id}" data-direction="1" ${index === items.length - 1 ? "disabled" : ""}>↓</button><button class="ub-danger-link" data-delete-action="${item.id}">Remove</button></span></div><small>${esc(item.event_type)} · ${esc(JSON.stringify(item.configuration || {}))}</small></div>`).join("") || '<div class="ub-empty-panel"><strong>No actions yet</strong><p>Add what should happen on click, submit or change.</p></div>'}`;
  body.querySelector("[data-add-action]").addEventListener("click", () => actionDialog(node, items.length));
  body.querySelectorAll("[data-delete-action]").forEach((button) => button.addEventListener("click", async () => { await api.deleteAction(projectId, Number(button.dataset.deleteAction)); await load(activeDocument().id, { keepSelection: true }); }));
  body.querySelectorAll("[data-move-action]").forEach((button) => button.addEventListener("click", async () => {
    const index = items.findIndex((item) => item.id === Number(button.dataset.moveAction)); const otherIndex = index + Number(button.dataset.direction);
    if (index < 0 || otherIndex < 0 || otherIndex >= items.length) return;
    await Promise.all([items[index], items[otherIndex]].map((item, offset) => api.saveAction(projectId, {
      key: item.action_key, document_id: item.document_id, node_key: item.node_key, event_type: item.event_type,
      action_type: item.action_type, configuration: item.configuration, order: offset === 0 ? otherIndex : index,
    })));
    await load(activeDocument().id, { keepSelection: true });
  }));
}

function actionDialog(node, order) {
  const groups = Object.entries(state.registry.actions).reduce((map, item) => { (map[item[1].category] ||= []).push(item); return map; }, {});
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Action</p><h2>What should happen?</h2></div><button class="ub-icon-btn" data-close>×</button></div><label class="ub-field">Trigger<select id="ub-action-trigger">${(state.registry.components[node.component_type]?.events || ["click"]).map((event) => `<option>${esc(event)}</option>`).join("") || '<option>click</option>'}</select></label><label class="ub-field">Action<select id="ub-action-type">${Object.entries(groups).map(([group, items]) => `<optgroup label="${esc(group)}">${items.map(([key, spec]) => `<option value="${key}">${esc(spec.label)}</option>`).join("")}</optgroup>`).join("")}</select></label><div id="ub-action-fields"></div><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-save-action>Add action</button></div>`, () => {
    const typeSelect = document.getElementById("ub-action-type"); const fields = document.getElementById("ub-action-fields");
    const paint = () => { const spec = state.registry.actions[typeSelect.value]; fields.innerHTML = Object.entries(spec.fields || {}).map(([key, kind]) => `<label class="ub-field">${esc(labelize(key))}<input data-action-field="${key}" type="${kind === "url" ? "url" : "text"}"></label>`).join(""); }; typeSelect.addEventListener("change", paint); paint();
    modal.querySelector("[data-save-action]").addEventListener("click", async () => { const configuration = {}; modal.querySelectorAll("[data-action-field]").forEach((input) => configuration[input.dataset.actionField] = input.value); await api.saveAction(projectId, { document_id: activeDocument().id, node_key: node.key, event_type: document.getElementById("ub-action-trigger").value, action_type: typeSelect.value, configuration, order }); modal.close(); await load(activeDocument().id, { keepSelection: true }); toast("Action added"); });
  });
}

function renderVisibilityInspector(body, node) {
  const condition = state.conditions.find((item) => item.id === node.condition_id);
  const collections = state.data.data_models || [];
  const OP_LABELS = { eq: "equals", ne: "does not equal", contains: "contains", gt: "greater than", gte: "at least", lt: "less than", lte: "at most", truthy: "is set (has any value)", falsy: "is empty (no value)" };
  const buildPathOptions = () => {
    const options = ['<optgroup label="Page state">'];
    options.push('<option value="state.">state. — page state values</option>');
    options.push('</optgroup>');
    if (collections.length) {
      options.push('<optgroup label="Collections">');
      for (const model of collections) {
        const fields = Object.keys(model.schema?.properties || {});
        for (const field of fields) {
          options.push(`<option value="collections.${esc(model.model_key)}.${esc(field)}">collections.${esc(model.model_key)}.${esc(field)}</option>`);
        }
      }
      options.push('</optgroup>');
    }
    const variables = state.data.project_variables || [];
    if (variables.length) {
      options.push('<optgroup label="Variables">');
      for (const v of variables) options.push(`<option value="variable.${esc(v.variable_key)}">variable.${esc(v.variable_key)}</option>`);
      options.push('</optgroup>');
    }
    return options.join("");
  };
  const currentLeft = condition?.expression?.left || "";
  body.innerHTML = `<label class="ub-field"><span>Visibility</span><select id="ub-node-visibility"><option value="visible" ${node.visibility === "visible" ? "selected" : ""}>Always visible</option><option value="hidden" ${node.visibility === "hidden" ? "selected" : ""}>Always hidden</option><option value="visible" ${condition ? "selected" : ""}>Conditional — controlled below</option></select></label><div class="ub-section-box"><h3>Show this layer when…</h3><p class="ub-dialog__hint">Choose a data path and a rule. The layer appears only when the rule is true.</p><label class="ub-field"><span>Data path</span><select id="ub-condition-left"><option value="" ${!currentLeft ? "selected" : ""}>— choose a path —</option>${buildPathOptions()}</select><input id="ub-condition-left-custom" value="${esc(currentLeft)}" placeholder="Or type a custom path…" style="margin-top:4px"></label><label class="ub-field"><span>Condition</span><select id="ub-condition-op">${Object.entries(OP_LABELS).map(([op, label]) => `<option value="${op}" ${condition?.expression?.operator === op ? "selected" : ""}>${label}</option>`).join("")}</select></label><label class="ub-field"><span>Compared to</span><input id="ub-condition-right" value="${esc(condition?.expression?.right ?? "")}" placeholder="e.g. active, true, 100"></label><small class="ub-dialog__hint">Leave blank for "is set" / "is empty" conditions.</small><button class="ub-btn ub-btn--primary" data-save-condition style="margin-top:10px">${condition ? "Update condition" : "Save condition"}</button>${condition ? '<button class="ub-danger-link" data-remove-condition style="margin-top:8px;display:block">Remove condition</button>' : ""}</div>`;
  const leftSelect = document.getElementById("ub-condition-left");
  const leftCustom = document.getElementById("ub-condition-left-custom");
  leftSelect.addEventListener("change", () => { if (leftSelect.value) leftCustom.value = leftSelect.value; });
  if (currentLeft && !leftSelect.querySelector(`option[value="${currentLeft}"]`)) leftCustom.value = currentLeft;
  document.getElementById("ub-node-visibility").addEventListener("change", (event) => applyNodePatch(node.key, { visibility: event.target.value }, { history: { type: "patch", key: node.key, before: { visibility: node.visibility }, after: { visibility: event.target.value } } }));
  body.querySelector("[data-save-condition]").addEventListener("click", async () => {
    const leftPath = leftCustom.value.trim() || leftSelect.value;
    if (!leftPath) { toast("Choose a data path", "error"); return; }
    const result = await api.saveCondition(projectId, { key: condition?.condition_key, name: `${node.component_type} visibility`, expression: { left: leftPath, operator: document.getElementById("ub-condition-op").value, right: document.getElementById("ub-condition-right").value } });
    await api.updateNode(projectId, node.key, { condition_id: result.id });
    await load(activeDocument().id, { keepSelection: true }); toast("Visibility condition saved");
  });
  body.querySelector("[data-remove-condition]")?.addEventListener("click", async () => {
    await api.updateNode(projectId, node.key, { condition_id: null });
    await load(activeDocument().id, { keepSelection: true }); toast("Condition removed");
  });
}

function renderAdvancedInspector(body, node) {
  body.innerHTML = `<label class="ub-field">Layer name<input id="ub-layer-name" value="${esc(node.metadata?.display_label || "")}" placeholder="${esc(state.registry.components[node.component_type]?.label || node.component_type)}"></label><button class="ub-btn ub-btn--primary" data-create-component>Create component</button><button class="ub-btn" data-duplicate-node>Duplicate</button> <button class="ub-btn ub-btn--danger" data-delete-node>Delete</button><div class="ub-section-box"><button class="ub-btn" data-save-version>Save version</button><button class="ub-btn" data-history>Version history</button></div><details class="ub-section-box"><summary>Developer details</summary><p><code>${esc(node.key)}</code></p><p>${esc(node.component_reference)}</p></details>`;
  document.getElementById("ub-layer-name").addEventListener("change", (event) => applyNodePatch(node.key, { metadata: { ...node.metadata, display_label: event.target.value } }));
  body.querySelector("[data-duplicate-node]").addEventListener("click", duplicateSelected);
  body.querySelector("[data-delete-node]").addEventListener("click", deleteSelected);
  body.querySelector("[data-save-version]").addEventListener("click", saveVersion);
  body.querySelector("[data-history]").addEventListener("click", showHistory);
  body.querySelector("[data-create-component]").addEventListener("click", createComponentDialog);
}

function createComponentDialog(){const node=selectedNode();if(!node)return;showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Reusable component</p><h2>Create from selected layers</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>The selected layer and its children become one synchronized component instance.</p><label class="ub-field">Name<input id="ub-component-name" value="${esc(node.metadata?.display_label||state.registry.components[node.component_type]?.label||"New Component")}"></label><label class="ub-field">Description<textarea id="ub-component-description"></textarea></label><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-confirm-component>Create component</button></div>`,()=>modal.querySelector("[data-confirm-component]").addEventListener("click",async()=>{const result=await api.createComponent(projectId,{document_id:activeDocument().id,node_key:node.key,name:document.getElementById("ub-component-name").value,description:document.getElementById("ub-component-description").value});modal.close();await load(activeDocument().id);selectNode(node.key);toast(`${result.name} created`);}));}

function refreshSelectionViews() { renderCanvasView(); if (state.panel === "layers") renderLayersPanel(); renderInspector(); }
function topLevelSelected() {
  const set = new Set(state.selectedKeys);
  return selectedNodes().filter((node) => { let parent = node.parent_key; while (parent) { if (set.has(parent)) return false; parent = state.nodes.find((item) => item.key === parent)?.parent_key; } return true; });
}
async function deleteSelected() {
  const targets = state.selectedKeys.length > 1 ? topLevelSelected() : selectedNodes();
  if (!targets.length) return;
  const many = targets.length > 1;
  if (!confirm(many ? `Delete ${targets.length} components and everything inside them?` : "Delete this component and everything inside it?")) return;
  for (const node of targets) await api.deleteNode(projectId, node.key);
  pushHistory({ type: "cannot-restore", label: many ? `Delete ${targets.length}` : "Delete" });
  setSelection([]); await load(activeDocument().id);
  toast(many ? `${targets.length} components deleted` : "Component deleted");
}
async function duplicateSelected() {
  const targets = selectedNodes(); if (!targets.length) return;
  const created = []; for (const node of targets) { const result = await api.duplicateNode(projectId, node.key); created.push(result.key); }
  if (targets.length > 1) pushHistory({ type: "cannot-restore", label: `Duplicate ${targets.length}` });
  await load(activeDocument().id);
  setSelection(created.filter((key) => state.nodes.some((node) => node.key === key))); refreshSelectionViews();
  toast(targets.length > 1 ? `${created.length} components duplicated` : "Component duplicated");
}
async function groupSelection() {
  const targets = topLevelSelected();
  if (targets.length < 2) return toast("Select two or more elements to group", "info");
  if (!(await ensureCapabilities("section"))) return;
  const parentKey = targets[0].parent_key || null;
  const order = siblingCount(parentKey);
  let section;
  try { section = await api.createNode(projectId, { document_id: activeDocument().id, component_type: "section", parent_key: parentKey, order }); }
  catch (error) { return toast(error.message, "error"); }
  await load(activeDocument().id);
  const keys = targets.map((node) => node.key);
  const incompatible = keys.filter((key) => !canNest(state, state.nodes.find((node) => node.key === key)?.component_type, section.key));
  if (incompatible.length) {
    await api.deleteNode(projectId, section.key); await load(activeDocument().id);
    const labels = incompatible.map((key) => { const node = targets.find((item) => item.key === key); return state.registry.components[node?.component_type]?.label || node?.component_type; });
    return toast(`${labels.join(", ")} can't be grouped into a section`, "error");
  }
  const sorted = keys.map((key) => targets.find((node) => node.key === key)).sort((a, b) => a.order - b.order);
  for (let index = 0; index < sorted.length; index++) await applyNodePatch(sorted[index].key, { parent_key: section.key, order: index }, { quiet: true });
  pushHistory({ type: "cannot-restore", label: `Group ${sorted.length}` });
  await load(activeDocument().id); setSelection([section.key]); refreshSelectionViews();
  toast(`${sorted.length} elements grouped`);
}
async function ungroupSelection() {
  const node = selectedNode(); if (!node) return toast("Select a group to ungroup", "info");
  const children = state.nodes.filter((item) => item.parent_key === node.key).sort((a, b) => a.order - b.order);
  if (!children.length) return toast("This element has no children to ungroup", "info");
  const parentKey = node.parent_key || null;
  if (parentKey && children.some((child) => !canNest(state, child.component_type, parentKey))) return toast("Some children can't move up to that level", "error");
  let base = siblingCount(parentKey);
  for (let index = 0; index < children.length; index++) await applyNodePatch(children[index].key, { parent_key: parentKey, order: base + index }, { quiet: true });
  await api.deleteNode(projectId, node.key);
  pushHistory({ type: "cannot-restore", label: "Ungroup" });
  await load(activeDocument().id); setSelection([]); refreshSelectionViews();
  toast("Group removed");
}

function createPage() {
  const surface = activeSurface();
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">New page</p><h2>Create a page</h2></div><button class="ub-icon-btn" data-close>×</button></div><label class="ub-field">Page name<input id="ub-new-page-name" placeholder="About" autofocus></label><label class="ub-field">Route<input id="ub-new-page-route" placeholder="/about"></label><p class="ub-issue">The route is suggested from the name and stays editable. Use / for the home page.</p><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-create-page>Create page</button></div>`, () => {
    const nameInput = document.getElementById("ub-new-page-name");
    const routeInput = document.getElementById("ub-new-page-route");
    let routeTouched = false;
    routeInput.addEventListener("input", () => { routeTouched = true; });
    nameInput.addEventListener("input", () => { if (!routeTouched) routeInput.value = `/${slug(nameInput.value)}`; });
    modal.querySelector("[data-create-page]").addEventListener("click", async (event) => {
      const name = nameInput.value.trim(); if (!name) return toast("Give the page a name", "error");
      const route = routeInput.value.trim() || `/${slug(name)}`;
      event.target.disabled = true;
      try { const page = await api.createDocument(projectId, { surface_id: surface?.id, name, key: name, route }); modal.close(); await load(page.id); toast(`Page created → ${page.route}`); }
      catch (error) { event.target.disabled = false; toast(error.message, "error"); }
    });
  });
}
async function renamePage() { const page = activeDocument(); const name = prompt("Page name", page.name); if (!name) return; try { await api.updateDocument(projectId, page.id, { name, route: page.route }); await load(page.id); toast("Page renamed"); } catch (error) { toast(error.message, "error"); } }
async function editPageRoute() { const page = activeDocument(); const route = prompt("Page route", page.route || `/${slug(page.name)}`); if (route === null) return; try { const updated = await api.updateDocument(projectId, page.id, { name: page.name, route: route.trim() }); await load(page.id); toast(`Route set to ${updated.route}`); } catch (error) { toast(error.message, "error"); } }
async function setHomepage() { const page = activeDocument(); if (page.route === "/") return toast("This page is already the home page", "info"); try { await api.updateDocument(projectId, page.id, { name: page.name, route: "/" }); await load(page.id); toast(`${page.name} is now the home page`); } catch (error) { toast(error.message, "error"); } }
function previewPage() { document.getElementById("ub-preview").click(); }

// Navigation links are stored on the node's `links` prop as newline-delimited "Label|target" lines
// (the existing runtime format). Targets are URLs/page routes, not stable page identities, so a
// page route change does not auto-propagate here — re-pick the page to refresh its target. A
// stable-identity layer would require a data-model change (§14/§15) and is intentionally not added.
function parseNavLinks(raw) {
  return String(raw || "").split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const index = line.indexOf("|");
    return index >= 0 ? { label: line.slice(0, index).trim(), target: line.slice(index + 1).trim() } : { label: line, target: "" };
  });
}
function serializeNavLinks(items) { return items.filter((item) => item.label || item.target).map((item) => `${item.label}|${item.target}`).join("\n"); }
function navigationEditor(node) {
  let items = parseNavLinks(node.props?.links);
  const pages = state.data.documents.filter((doc) => doc.status === "active" && doc.surface_id === activeSurface()?.id);
  const pageOptions = (selected) => `<option value="">— Page —</option>${pages.map((page) => `<option value="${esc(page.route)}" data-name="${esc(page.name)}" ${page.route === selected ? "selected" : ""}>${esc(page.name)} · ${esc(page.route)}</option>`).join("")}`;
  const render = () => showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Navigation</p><h2>Edit links</h2></div><button class="ub-icon-btn" data-close>×</button></div><p class="ub-issue">Choose a project page or type an external URL. Use the arrows to reorder — drag is never the only way.</p><div id="ub-nav-items">${items.map((item, index) => `<div class="ub-field-row" data-nav-row="${index}"><label class="ub-field">Label<input data-nav-label value="${esc(item.label)}" placeholder="About"></label><label class="ub-field">Page<select data-nav-page>${pageOptions(item.target)}</select></label><label class="ub-field">or URL<input data-nav-url value="${esc(item.target)}" placeholder="/about or https://…"></label><span class="ub-layer-item__actions"><button class="ub-icon-btn" data-nav-up title="Move up">↑</button><button class="ub-icon-btn" data-nav-down title="Move down">↓</button><button class="ub-icon-btn" data-nav-remove title="Remove">×</button></span></div>`).join("") || '<div class="ub-empty-panel"><strong>No links yet</strong><p>Add your first navigation item.</p></div>'}</div><div class="ub-dialog__actions"><button class="ub-btn" data-nav-add>+ Add link</button><button class="ub-btn ub-btn--primary" data-nav-save>Save navigation</button></div>`, () => {
    modal.querySelectorAll("[data-nav-row]").forEach((row) => {
      const label = row.querySelector("[data-nav-label]"); const page = row.querySelector("[data-nav-page]"); const url = row.querySelector("[data-nav-url]");
      label.addEventListener("input", () => { items[Number(row.dataset.navRow)].label = label.value; });
      page.addEventListener("change", () => { const index = Number(row.dataset.navRow); if (page.value) { items[index].target = page.value; url.value = page.value; if (!items[index].label) { items[index].label = page.selectedOptions[0]?.dataset.name || ""; label.value = items[index].label; } } });
      url.addEventListener("input", () => { const index = Number(row.dataset.navRow); items[index].target = url.value; page.value = pages.some((doc) => doc.route === url.value) ? url.value : ""; });
      row.querySelector("[data-nav-up]").addEventListener("click", () => { const index = Number(row.dataset.navRow); if (index > 0) { [items[index - 1], items[index]] = [items[index], items[index - 1]]; render(); } });
      row.querySelector("[data-nav-down]").addEventListener("click", () => { const index = Number(row.dataset.navRow); if (index < items.length - 1) { [items[index + 1], items[index]] = [items[index], items[index + 1]]; render(); } });
      row.querySelector("[data-nav-remove]").addEventListener("click", () => { items.splice(Number(row.dataset.navRow), 1); render(); });
    });
    modal.querySelector("[data-nav-add]").addEventListener("click", () => { items.push({ label: "", target: "" }); render(); });
    modal.querySelector("[data-nav-save]").addEventListener("click", async (event) => { event.target.disabled = true; try { await updateInline(node.key, "links", serializeNavLinks(items)); modal.close(); renderCanvasView(); toast("Navigation updated"); } catch (error) { event.target.disabled = false; toast(error.message, "error"); } });
  });
  render();
}
function selectParent() { const node = selectedNode(); if (!node?.parent_key) return toast("Already at the top level", "info"); selectNode(node.parent_key); }
function selectChild() { const node = selectedNode(); if (!node) return toast("Select a layer first", "info"); const child = state.nodes.filter((item) => item.parent_key === node.key).sort((a, b) => a.sort_order - b.sort_order)[0]; if (!child) return toast("No child to select", "info"); selectNode(child.key); }
async function archivePage() { const page = activeDocument(); if (!confirm(`Archive ${page.name}?`)) return; try { await api.deleteDocument(projectId, page.id); await load(); toast("Page archived"); } catch (error) { toast(error.message, "error"); } }
async function createSurface() { const name = prompt("Site name", "New site"); if (!name) return; const surface = await api.createSurface(projectId, { name, key: name, base_path: `/${slug(name)}` }); const page = await api.createDocument(projectId, { surface_id: surface.id, name: "Home", key: `${slug(name)}-home`, route: "/" }); await load(page.id); }
async function renameSurface() { const surface = activeSurface(); const name = prompt("Site name", surface.name); if (!name) return; await api.updateSurface(projectId, surface.id, { name }); await load(activeDocument().id); }

function renderFullMode() { renderOverlay(); }

function renderComponentsMode() {
  const definitions = state.data.component_definitions || [];
  fullMode.innerHTML = `<div class="ub-mode-page"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Creator System</p><h1>Components</h1><p>Build once, reuse everywhere, and publish your work to the community.</p></div><button class="ub-btn ub-btn--primary" data-back-build>Create from selected layer</button></div><div class="ub-market-grid">${definitions.map((item) => `<article class="ub-card ub-creator-card"><div><span class="ub-badge ${item.metadata?.category === "official" ? "ub-badge--official" : ""}">${esc(item.metadata?.category || "local")}</span><h2>${esc(item.name)}</h2><p>${esc(item.description || "Reusable project component")}</p><small>${item.usage_count || 0} instance${item.usage_count === 1 ? "" : "s"} · ${Object.keys(item.variants || {}).length} variants</small></div><div><button class="ub-btn ub-btn--primary" data-insert-component="${item.id}">Insert</button> <button class="ub-btn" data-edit-component="${item.id}">Edit</button> <button class="ub-btn" data-publish-component="${item.id}">Publish</button> <button class="ub-btn" data-usage-component="${item.id}">Usage</button></div></article>`).join("") || '<div class="ub-card ub-empty-panel"><strong>No reusable components</strong><p>Turn any section or group into a reusable component.</p></div>'}</div></div>`;
  fullMode.querySelector("[data-back-build]")?.addEventListener("click", () => { hideOverlay(); if (selectedNode()) createComponentDialog(); else toast("Select a layer first", "info"); });
  fullMode.querySelectorAll("[data-insert-component]").forEach((button) => button.addEventListener("click", async () => { const created = await api.createInstance(projectId, Number(button.dataset.insertComponent), { document_id: activeDocument().id, parent_key: state.nodes.find((node) => node.component_type === "section")?.key || null, order: state.nodes.length }); hideOverlay(); await load(activeDocument().id); selectNode(created.key); toast("Reusable component inserted"); }));
  fullMode.querySelectorAll("[data-edit-component]").forEach((button) => button.addEventListener("click", () => componentEditor(Number(button.dataset.editComponent))));
  fullMode.querySelectorAll("[data-publish-component]").forEach((button) => button.addEventListener("click", () => publishComponentDialog(Number(button.dataset.publishComponent))));
  fullMode.querySelectorAll("[data-usage-component]").forEach((button) => button.addEventListener("click", async () => { const { usage } = await api.componentUsage(projectId, Number(button.dataset.usageComponent)); showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Component usage</p><h2>${usage.length} instances</h2></div><button class="ub-icon-btn" data-close>×</button></div>${usage.map((item) => `<div class="ub-action-card"><strong>${esc(item.document_name)}</strong><small>Page: ${esc(item.document_name)}</small></div>`).join("") || '<p>This component is not used yet.</p>'}`); }));
}

function publishComponentDialog(id) {
  const definition = state.data.component_definitions.find((item) => item.id === id); if (!definition) return;
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Publish to Community</p><h2>${esc(definition.name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>Studio will package this Component, its Variants, Data Inputs and required Design Tokens into an immutable version.</p><div class="ub-field-row"><label class="ub-field">Creator name<input id="ub-publisher-name" value="My Creator Profile"></label><label class="ub-field">Creator handle<input id="ub-publisher-handle" placeholder="your-name"></label></div><label class="ub-field">Community name<input id="ub-package-name" value="${esc(definition.name)}"></label><label class="ub-field">Description<textarea id="ub-package-description">${esc(definition.description || "")}</textarea></label><div class="ub-field-row"><label class="ub-field">Version<input id="ub-package-version" value="1.0.0" pattern="\\d+\\.\\d+\\.\\d+"></label><label class="ub-field">Visibility<select id="ub-package-visibility"><option value="public">Public</option><option value="unlisted">Unlisted</option><option value="private">Private</option></select></label></div><label class="ub-field">Release notes<textarea id="ub-package-notes">Initial release</textarea></label><label class="ub-field"><span>Reuse permissions</span><span><input type="checkbox" data-package-right="remix" checked> Remix &nbsp; <input type="checkbox" data-package-right="fork" checked> Fork &nbsp; <input type="checkbox" data-package-right="commercial_use" checked> Commercial use</span></label><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-confirm-publish-component>Validate & publish</button></div>`, () => {
    modal.querySelector("[data-confirm-publish-component]").addEventListener("click", async (event) => {
      event.target.disabled = true; event.target.textContent = "Validating dependencies…";
      const usageRights = ["install", ...[...modal.querySelectorAll("[data-package-right]:checked")].map((item) => item.dataset.packageRight)];
      try {
        const result = await api.publishComponent(projectId, id, { name: document.getElementById("ub-package-name").value.trim(), description: document.getElementById("ub-package-description").value.trim(), version: document.getElementById("ub-package-version").value.trim(), visibility: document.getElementById("ub-package-visibility").value, release_notes: document.getElementById("ub-package-notes").value.trim(), creator_name: document.getElementById("ub-publisher-name").value.trim(), creator_handle: document.getElementById("ub-publisher-handle").value.trim(), usage_rights: usageRights });
        modal.close(); toast(`${result.name} v${result.version} published`); openCommunity();
      } catch (error) { event.target.disabled = false; event.target.textContent = "Validate & publish"; toast(error.message, "error"); }
    });
  });
}

function componentEditor(id) {
  const definition = state.data.component_definitions.find((item) => item.id === id); if (!definition) return;
  fullMode.innerHTML = `<div class="ub-mode-page"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Composition / Components / ${esc(definition.name)}</p><h1>${esc(definition.name)}</h1><p>Changes update every instance. Instance overrides remain intact.</p></div><button class="ub-btn" data-components-back>Done</button></div><div class="ub-data-layout"><section class="ub-card"><h2>Component layers</h2>${(definition.root_structure||[]).map((node)=>`<div class="ub-action-card"><div class="ub-action-card__head"><strong>${esc(node.metadata?.display_label||labelize(node.component_type))}</strong><button class="ub-btn" data-edit-definition-node="${esc(node.key)}">Edit</button></div><small>${esc(labelize(node.component_type))}</small></div>`).join("")}<h2>Exposed properties</h2>${Object.entries(definition.property_schema?.properties || {}).map(([key,value]) => `<div class="ub-action-card"><strong>${esc(value.label || labelize(key))}</strong><small>${esc(value.node_key)} · ${esc(value.property)}</small></div>`).join("") || '<div class="ub-empty-panel">Expose an internal property from Edit layer.</div>'}<h2>Slots</h2>${Object.entries(definition.slots || {}).map(([key,value]) => `<div class="ub-action-card"><strong>${esc(labelize(key))}</strong><small>Allows ${(value.accepts || []).join(", ")}</small></div>`).join("")}<button class="ub-btn" data-add-slot>+ Slot</button></section><section class="ub-card"><h2>Variants</h2>${Object.entries(definition.variants || {}).map(([key,value]) => `<div class="ub-action-card"><strong>${esc(value.label || labelize(key))}</strong><small>${Object.keys(value.overrides || {}).length} changed layers</small></div>`).join("")}<button class="ub-btn ub-btn--primary" data-add-variant>+ Variant</button><h2>Data inputs</h2><pre>${esc(JSON.stringify(definition.data_inputs || {}, null, 2))}</pre><h2>Events</h2><p>${(definition.events || []).map((item) => `<span class="ub-badge">${esc(item)}</span>`).join(" ") || "No exposed events"}</p></section></div></div>`;
  fullMode.querySelector("[data-components-back]").addEventListener("click", hideOverlay);
  fullMode.querySelector("[data-add-variant]").addEventListener("click", async () => { const name = prompt("Variant name", "Compact"); if (!name) return; const key = slug(name); await api.updateComponent(projectId, id, { variants: { ...definition.variants, [key]: { label: name, overrides: {} } } }); await load(activeDocument().id); showOverlay("component-editor", id); });
  fullMode.querySelector("[data-add-slot]").addEventListener("click",async()=>{const name=prompt("Slot name","actions");if(!name)return;await api.updateComponent(projectId,id,{slots:{...(definition.slots||{}),[slug(name).replaceAll("-","_")]:{accepts:["*"]}}});await load(activeDocument().id);showOverlay("component-editor", id);});
  fullMode.querySelectorAll("[data-edit-definition-node]").forEach((button)=>button.addEventListener("click",()=>definitionNodeDialog(definition,button.dataset.editDefinitionNode)));
}

function definitionNodeDialog(definition,nodeKey){const node=(definition.root_structure||[]).find((item)=>item.key===nodeKey);if(!node)return;const fields=state.registry.components[node.component_type]?.property_schema?.properties||{};showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Edit component layer</p><h2>${esc(labelize(node.component_type))}</h2></div><button class="ub-icon-btn" data-close>×</button></div>${Object.entries(fields).map(([key,schema])=>fieldControl(key,schema,node.props?.[key])).join("")}<label class="ub-field">Background / token<input id="ub-definition-background" value="${esc(node.styles?.background||"")}" list="ub-definition-tokens"><datalist id="ub-definition-tokens">${(state.data.design_tokens||[]).map((item)=>`<option value="token:${esc(item.token_key)}">`).join("")}</datalist></label><label class="ub-field">Expose property<select id="ub-expose-property"><option value="">Do not expose</option>${Object.keys(fields).map((key)=>`<option>${esc(key)}</option>`).join("")}</select></label><label class="ub-field">Exposed label<input id="ub-expose-label"></label><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-save-definition-node>Save for all instances</button></div>`,()=>modal.querySelector("[data-save-definition-node]").addEventListener("click",async()=>{const structure=structuredClone(definition.root_structure);const target=structure.find((item)=>item.key===nodeKey);modal.querySelectorAll("[data-prop]").forEach((input)=>{let value=input.value;if(input.tagName==="SELECT"&&["true","false"].includes(value))value=value==="true";target.props={...(target.props||{}),[input.dataset.prop]:value};});const background=document.getElementById("ub-definition-background").value;if(background)target.styles={...(target.styles||{}),background};const property=document.getElementById("ub-expose-property").value;const schema=structuredClone(definition.property_schema||{type:"object",properties:{}});if(property){const exposedKey=slug(document.getElementById("ub-expose-label").value||property).replaceAll("-","_");schema.properties[exposedKey]={label:document.getElementById("ub-expose-label").value||labelize(property),node_key:nodeKey,property,type:fields[property]?.type||"string",localized:true};}await api.updateComponent(projectId,definition.id,{root_structure:structure,property_schema:schema});modal.close();await load(activeDocument().id);showOverlay("component-editor",definition.id);}));}

function renderDesignMode() {
  const tokens = state.data.design_tokens || []; const variables = state.data.project_variables || [];
  fullMode.innerHTML = `<div class="ub-mode-page"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Shared foundation</p><h1>Design System</h1><p>Tokens and variables update every connected component.</p></div><div><button class="ub-btn" data-new-variable>+ Variable</button> <button class="ub-btn ub-btn--primary" data-new-token>+ Token</button></div></div><div class="ub-data-layout"><section class="ub-card"><h2>Design tokens</h2>${tokens.map((item) => `<div class="ub-token-row"><span class="ub-token-swatch" style="--swatch:${esc(item.values_json?.light || item.values_json?.default || "transparent")}"></span><div><strong>${esc(item.name)}</strong><small>${esc(item.token_key)} · ${esc(item.category)}</small></div><button class="ub-btn" data-edit-token="${esc(item.token_key)}">Edit</button></div>`).join("") || '<div class="ub-empty-panel"><strong>No design tokens</strong><p>Create shared colors, typography and spacing for your project.</p></div>'}</section><section class="ub-card"><h2>Project variables</h2>${variables.map((item) => `<div class="ub-action-card"><strong>${esc(item.name)}</strong><p>${esc(item.variable_key)} = ${esc(JSON.stringify(item.value_json))}</p></div>`).join("") || '<div class="ub-empty-panel">Create shared brand and configuration values.</div>'}</section></div></div>`;
  const tokenDialog = (key="") => { const item=tokens.find((token)=>token.token_key===key); showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Design token</p><h2>${item?"Edit":"Create"} token</h2></div><button class="ub-icon-btn" data-close>×</button></div><label class="ub-field">Name<input id="ub-token-name" value="${esc(item?.name||"")}"></label><label class="ub-field">Key<input id="ub-token-key" value="${esc(item?.token_key||"")}" ${item?"readonly":""}></label><label class="ub-field">Category<select id="ub-token-category">${["color","font_family","font_size","spacing","radius","border","shadow","duration","easing"].map((value)=>`<option ${item?.category===value?"selected":""}>${value}</option>`).join("")}</select></label><label class="ub-field">Light / default value<input id="ub-token-value" value="${esc(item?.values_json?.light||item?.values_json?.default||"")}"></label><label class="ub-field">Dark value<input id="ub-token-dark" value="${esc(item?.values_json?.dark||"")}"></label><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-save-token>Save</button></div>`,()=>modal.querySelector("[data-save-token]").addEventListener("click",async()=>{ const name=document.getElementById("ub-token-name").value.trim(); const tokenKey=document.getElementById("ub-token-key").value.trim()||slug(name).replaceAll("-","."); const light=document.getElementById("ub-token-value").value; const dark=document.getElementById("ub-token-dark").value; await api.saveToken(projectId,{key:tokenKey,name,category:document.getElementById("ub-token-category").value,values:dark?{light,dark}:{default:light}}); modal.close(); await load(activeDocument().id); showOverlay("design"); })); };
  fullMode.querySelector("[data-new-token]").addEventListener("click",()=>tokenDialog()); fullMode.querySelectorAll("[data-edit-token]").forEach((button)=>button.addEventListener("click",()=>tokenDialog(button.dataset.editToken)));
  fullMode.querySelector("[data-new-variable]").addEventListener("click",()=>showModal(`<div class="ub-dialog__head"><h2>New project variable</h2><button class="ub-icon-btn" data-close>×</button></div><label class="ub-field">Name<input id="ub-variable-name"></label><label class="ub-field">Key<input id="ub-variable-key" placeholder="brand.name"></label><label class="ub-field">Value<input id="ub-variable-value"></label><div class="ub-dialog__actions"><button class="ub-btn ub-btn--primary" data-save-variable>Save</button></div>`,()=>modal.querySelector("[data-save-variable]").addEventListener("click",async()=>{await api.saveVariable(projectId,{name:document.getElementById("ub-variable-name").value,key:document.getElementById("ub-variable-key").value,value:document.getElementById("ub-variable-value").value});modal.close();await load(activeDocument().id);showOverlay("design");})));
}

function renderDataMode(selectedModel = state.data.data_models[0]?.model_key) {
  const model = state.data.data_models.find((item) => item.model_key === selectedModel);
  const hasModels = state.data.data_models.length > 0;
  fullMode.innerHTML = `<div class="ub-mode-page"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Connected data</p><h1>Data</h1><p>Create collections to store real content — events, team members, products — then connect them to your pages.</p></div><button class="ub-btn ub-btn--primary" data-new-model>+ New collection</button></div><div class="ub-data-layout"><aside class="ub-card"><h3>Collections</h3>${state.data.data_models.map((item) => `<button class="ub-data-item ${item.model_key === selectedModel ? "is-active" : ""}" data-model="${esc(item.model_key)}"><span>▦</span><span>${esc(item.name)}</span><small>${Object.keys(item.schema?.properties || {}).length} fields</small></button>`).join("") || ''}</aside><section class="ub-card" id="ub-record-area">${model ? "Loading records…" : (hasModels ? '<div class="ub-empty-panel"><strong>Select a collection</strong><p>Choose a collection from the left to view and manage its records.</p></div>' : '<div class="ub-empty-panel"><strong>Create your first collection</strong><p>A collection stores real data for your website — like events, team members, or products. Each collection has fields you define, and records you fill in.</p><button class="ub-btn ub-btn--primary" data-empty-new-model>+ New collection</button></div>')}</section></div></div>`;
  fullMode.querySelector("[data-new-model]").addEventListener("click", newModelDialog);
  fullMode.querySelector("[data-empty-new-model]")?.addEventListener("click", newModelDialog);
  fullMode.querySelectorAll("[data-model]").forEach((button) => button.addEventListener("click", () => renderDataMode(button.dataset.model)));
  if (model) renderRecords(model);
}

async function renderRecords(model) {
  const area = document.getElementById("ub-record-area");
  try {
    const { records } = await api.records(projectId, model.model_key); state.recordCache[model.model_key] = records;
    const fields = Object.keys(model.schema?.properties || {});
    const renderTable = (filter = "") => {
      const query = filter.toLowerCase();
      const filtered = query ? records.filter((record) => Object.values(record.data || {}).some((v) => String(v ?? "").toLowerCase().includes(query))) : records;
      area.innerHTML = `<div class="ub-panel-title"><div><h2>${esc(model.name)}</h2><small>${fields.length} field${fields.length === 1 ? "" : "s"} · ${records.length} record${records.length === 1 ? "" : "s"}</small></div><div><button class="ub-btn" data-edit-fields>Edit fields</button> <button class="ub-btn ub-btn--primary" data-new-record>+ Record</button> <button class="ub-btn ub-btn--danger" data-delete-model title="Delete this collection and all its records">Delete collection</button></div></div>${records.length > 3 ? `<div class="ub-search-row"><input class="ub-search" data-search-records placeholder="Search records…" value="${esc(filter)}"></div>` : ""}<div style="overflow:auto"><table class="ub-table"><thead><tr>${fields.map((field) => `<th>${esc(labelize(field))}</th>`).join("")}<th></th></tr></thead><tbody>${filtered.length ? filtered.map((record) => `<tr>${fields.map((field) => `<td>${esc(String(record.data?.[field] ?? ""))}</td>`).join("")}<td><button class="ub-danger-link" data-edit-record="${esc(record.record_key)}">Edit</button> · <button class="ub-danger-link" data-delete-record="${esc(record.record_key)}">Delete</button></td></tr>`).join("") : `<tr><td colspan="${fields.length + 1}"><div class="ub-empty-panel">${query ? "<strong>No matching records</strong><p>Try a different search term.</p>" : "<strong>No records yet</strong><p>Add your first record to this collection.</p>"}</div></td></tr>`}</tbody></table></div>`;
      area.querySelector("[data-new-record]").addEventListener("click", () => recordDialog(model));
      area.querySelector("[data-edit-fields]").addEventListener("click", () => fieldsDialog(model));
      area.querySelector("[data-delete-model]")?.addEventListener("click", () => deleteModelDialog(model));
      area.querySelectorAll("[data-delete-record]").forEach((button) => button.addEventListener("click", async () => { await api.deleteRecord(projectId, model.model_key, button.dataset.deleteRecord); renderRecords(model); }));
      area.querySelectorAll("[data-edit-record]").forEach((button) => button.addEventListener("click", () => { const record = records.find((r) => r.record_key === button.dataset.editRecord); if (record) recordDialog(model, record); }));
      area.querySelector("[data-search-records]")?.addEventListener("input", (event) => renderTable(event.target.value));
    };
    renderTable();
  } catch (error) { area.innerHTML = `<div class="ub-empty-panel"><strong>Could not load records</strong><p>${esc(error.message)}</p></div>`; }
}

function deleteModelDialog(model) {
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Delete collection</p><h2>${esc(model.name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>This will permanently delete the <strong>${esc(model.name)}</strong> collection and all ${state.recordCache[model.model_key]?.length ?? "?"} records in it. Any bindings pointing to this collection will stop working.</p><p>This action cannot be undone.</p><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--danger" data-confirm-delete>Delete collection</button></div>`, () => {
    modal.querySelector("[data-confirm-delete]").addEventListener("click", async (event) => {
      event.target.disabled = true; event.target.textContent = "Deleting…";
      try {
        await api.deleteModel(projectId, model.model_key);
        modal.close(); await load(activeDocument().id); showOverlay("data");
        toast(`${model.name} deleted`);
      } catch (error) { event.target.disabled = false; event.target.textContent = "Delete collection"; toast(error.message, "error"); }
    });
  });
}

function newModelDialog() {
  const FIELD_TYPES = [
    { value: "string", label: "Text", hint: "Short or long text" },
    { value: "number", label: "Number", hint: "Integer or decimal" },
    { value: "boolean", label: "Yes / No", hint: "True or false" },
    { value: "date", label: "Date", hint: "Calendar date" },
    { value: "datetime", label: "Date & time", hint: "Full timestamp" },
    { value: "url", label: "Link", hint: "Web address" },
    { value: "json", label: "Structured data", hint: "Advanced — JSON object" },
  ];
  let fieldRows = [
    { name: "title", type: "string" },
    { name: "description", type: "string" },
  ];
  const renderFields = () => {
    const list = document.getElementById("ub-model-fields");
    if (!list) return;
    list.innerHTML = fieldRows.map((field, index) => `<div class="ub-model-field-row" data-index="${index}"><input class="ub-model-field-name" value="${esc(field.name)}" placeholder="field_name"><select class="ub-model-field-type">${FIELD_TYPES.map((t) => `<option value="${t.value}" ${field.type === t.value ? "selected" : ""}>${t.label}</option>`).join("")}</select><button class="ub-icon-btn" data-remove-field="${index}" ${fieldRows.length <= 1 ? "disabled" : ""} title="Remove field">×</button></div>`).join("");
    list.querySelectorAll("[data-remove-field]").forEach((btn) => btn.addEventListener("click", () => { fieldRows.splice(Number(btn.dataset.removeField), 1); renderFields(); }));
    list.querySelectorAll(".ub-model-field-name").forEach((input, i) => input.addEventListener("input", () => { fieldRows[i].name = input.value; }));
    list.querySelectorAll(".ub-model-field-type").forEach((select, i) => select.addEventListener("change", () => { fieldRows[i].type = select.value; }));
  };
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Data model</p><h2>Create a collection</h2></div><button class="ub-icon-btn" data-close>×</button></div><p class="ub-dialog__intro">A collection stores real Data for this composition — events, products, team members, anything. Define its shape by adding fields below.</p><label class="ub-field"><span>Collection name</span><input id="ub-model-name" placeholder="e.g. Events, Team, Products" autofocus></label><div class="ub-section-box"><div class="ub-panel-title"><h3>Fields</h3><button class="ub-btn" data-add-field>+ Add field</button></div><div id="ub-model-fields" class="ub-model-fields"></div><small class="ub-dialog__hint">Field names become column keys — use lowercase letters and underscores.</small></div><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-create-model>Create collection</button></div>`, () => {
    renderFields();
    modal.querySelector("[data-add-field]").addEventListener("click", () => { fieldRows.push({ name: "", type: "string" }); renderFields(); const inputs = modal.querySelectorAll(".ub-model-field-name"); inputs[inputs.length - 1]?.focus(); });
    const nameInput = document.getElementById("ub-model-name");
    modal.querySelector("[data-create-model]").addEventListener("click", async () => {
      const name = nameInput.value.trim();
      if (!name) { nameInput.focus(); return; }
      const validFields = fieldRows.filter((f) => f.name.trim());
      if (!validFields.length) { toast("Add at least one field", "error"); return; }
      const properties = {};
      for (const field of validFields) {
        const key = slug(field.name.trim()).replaceAll("-", "_") || slug(field.name.trim());
        properties[key] = { type: field.type };
      }
      const result = await api.createModel(projectId, { name, key: slug(name).replaceAll("-", "_"), schema: { type: "object", properties } });
      modal.close(); await load(activeDocument().id); showOverlay("data", result.key);
      toast(`${name} collection created`);
    });
  });
}

function fieldsDialog(model) {
  const FIELD_TYPES = [
    { value: "string", label: "Text" }, { value: "number", label: "Number" },
    { value: "boolean", label: "Yes / No" }, { value: "date", label: "Date" },
    { value: "datetime", label: "Date & time" }, { value: "url", label: "Link" },
    { value: "json", label: "Structured data" },
  ];
  const properties = model.schema?.properties || {};
  let fieldRows = Object.entries(properties).map(([key, schema]) => ({ name: key, type: schema.type || "string" }));
  if (!fieldRows.length) fieldRows.push({ name: "", type: "string" });
  const renderFields = () => {
    const list = document.getElementById("ub-fields-list");
    if (!list) return;
    list.innerHTML = fieldRows.map((field, index) => `<div class="ub-model-field-row" data-index="${index}"><span class="ub-model-field-handle" title="Drag to reorder">⠿</span><input class="ub-model-field-name" value="${esc(field.name)}" placeholder="field_name"><select class="ub-model-field-type">${FIELD_TYPES.map((t) => `<option value="${t.value}" ${field.type === t.value ? "selected" : ""}>${t.label}</option>`).join("")}</select><button class="ub-icon-btn" data-remove-field="${index}" ${fieldRows.length <= 1 ? "disabled" : ""} title="Remove field">×</button></div>`).join("");
    list.querySelectorAll("[data-remove-field]").forEach((btn) => btn.addEventListener("click", () => { fieldRows.splice(Number(btn.dataset.removeField), 1); renderFields(); }));
    list.querySelectorAll(".ub-model-field-name").forEach((input, i) => input.addEventListener("input", () => { fieldRows[i].name = input.value; }));
    list.querySelectorAll(".ub-model-field-type").forEach((select, i) => select.addEventListener("change", () => { fieldRows[i].type = select.value; }));
  };
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">${esc(model.name)}</p><h2>Fields</h2></div><button class="ub-icon-btn" data-close>×</button></div><p class="ub-dialog__intro">Fields define the shape of every record in this collection. Renaming a field key will break existing bindings that reference it.</p><div id="ub-fields-list" class="ub-model-fields"></div><button class="ub-btn" data-add-field>+ Add field</button><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-save-fields>Save fields</button></div>`, () => {
    renderFields();
    modal.querySelector("[data-add-field]").addEventListener("click", () => { fieldRows.push({ name: "", type: "string" }); renderFields(); const inputs = modal.querySelectorAll(".ub-model-field-name"); inputs[inputs.length - 1]?.focus(); });
    modal.querySelector("[data-save-fields]").addEventListener("click", async () => {
      const next = {};
      for (const row of fieldRows) {
        const key = row.name.trim();
        if (!key) continue;
        const safeKey = /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key) ? key : slug(key).replaceAll("-", "_");
        next[safeKey] = { type: row.type };
      }
      if (!Object.keys(next).length) { toast("Add at least one field", "error"); return; }
      await api.updateModel(projectId, model.model_key, { schema: { type: "object", properties: next } });
      modal.close(); await load(activeDocument().id); showOverlay("data", model.model_key);
      toast("Fields updated");
    });
  });
}

function recordDialog(model, existing = null) {
  const properties = model.schema?.properties || {};
  const isEdit = !!existing;
  const data = existing?.data || {};
  const inputFor = (key, schema) => {
    const value = data[key] ?? "";
    const common = `data-record-field="${esc(key)}"`;
    if (schema.type === "boolean") return `<label class="ub-field"><span><input type="checkbox" ${common} ${value ? "checked" : ""}> ${esc(labelize(key))}</span></label>`;
    if (schema.type === "number") return `<label class="ub-field"><span>${esc(labelize(key))}</span><input type="number" step="any" ${common} value="${esc(value)}"></label>`;
    if (schema.type === "date") return `<label class="ub-field"><span>${esc(labelize(key))}</span><input type="date" ${common} value="${esc(value)}"></label>`;
    if (schema.type === "datetime") return `<label class="ub-field"><span>${esc(labelize(key))}</span><input type="datetime-local" ${common} value="${esc(value)}"></label>`;
    if (schema.type === "url") return `<label class="ub-field"><span>${esc(labelize(key))}</span><input type="url" ${common} value="${esc(value)}" placeholder="https://"></label>`;
    if (schema.type === "json") return `<label class="ub-field"><span>${esc(labelize(key))}</span><textarea ${common} rows="3" placeholder="{}">${esc(typeof value === "object" ? JSON.stringify(value, null, 2) : value)}</textarea></label>`;
    return `<label class="ub-field"><span>${esc(labelize(key))}</span><input type="text" ${common} value="${esc(value)}"></label>`;
  };
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">${esc(model.name)}</p><h2>${isEdit ? "Edit" : "New"} record</h2></div><button class="ub-icon-btn" data-close>×</button></div>${Object.entries(properties).map(([key, schema]) => inputFor(key, schema)).join("") || '<div class="ub-empty-panel">This collection has no fields yet. Add fields first.</div>'}<div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-save-record>${isEdit ? "Save changes" : "Create record"}</button></div>`, () => {
    modal.querySelector("[data-save-record]").addEventListener("click", async () => {
      const recordData = {};
      modal.querySelectorAll("[data-record-field]").forEach((input) => {
        const key = input.dataset.recordField;
        const schema = properties[key] || {};
        if (schema.type === "boolean") recordData[key] = input.checked;
        else if (schema.type === "number") recordData[key] = input.value ? Number(input.value) : null;
        else if (schema.type === "json") { try { recordData[key] = JSON.parse(input.value || "null"); } catch { recordData[key] = input.value; } }
        else recordData[key] = input.value;
      });
      if (isEdit) await api.updateRecord(projectId, model.model_key, existing.record_key, { data: recordData });
      else await api.createRecord(projectId, model.model_key, { data: recordData });
      modal.close(); renderRecords(model);
      toast(isEdit ? "Record updated" : "Record created");
    });
  });
}

function summarizeAction(action) {
  const config = action.configuration || {};
  const keys = Object.keys(config);
  if (!keys.length) return "Configured in the inspector";
  const bits = keys.slice(0, 3).map((key) => {
    const value = config[key];
    if (value == null || value === "") return key;
    if (typeof value === "object") return key;
    return `${key}: ${String(value).slice(0, 40)}`;
  });
  return bits.join(" · ");
}

function openLayerInInspector(nodeKey, tab = "actions") {
  hideOverlay();
  if (nodeKey) {
    state.inspectorTab = tab;
    selectNode(nodeKey);
  } else {
    toast("Select an Interface layer first", "info");
  }
}

function addLogicActionFromGraph() {
  const node = selectedNode();
  if (!node) {
    toast("Select a layer on the Interface canvas, then add an action", "info");
    hideOverlay();
    return;
  }
  hideOverlay();
  state.inspectorTab = "actions";
  selectNode(node.key);
  actionDialog(node, state.actions.filter((item) => item.node_key === node.key).length);
}

function renderWorkflowsMode() {
  const actionCount = (state.actions || []).length;
  const condCount = (state.conditions || []).length;
  fullMode.innerHTML = `<div class="ub-mode-page ub-mode-page--graph"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Logic</p><h1>Composition Logic graph</h1><p>Each column is an Interface layer. Actions and visibility conditions are authored on the layer — click a node to edit them.</p></div><div class="ub-mode-page__actions"><button type="button" class="ub-btn" data-open-interface>Interface canvas</button><button type="button" class="ub-btn ub-btn--primary" data-add-logic-action>Add action</button></div></div><div id="ub-logic-graph" class="ub-graph-host"></div><div class="ub-section-box"><p><strong>${actionCount}</strong> action${actionCount === 1 ? "" : "s"} · <strong>${condCount}</strong> condition${condCount === 1 ? "" : "s"} on this page</p></div></div>`;
  fullMode.querySelectorAll("[data-open-interface]").forEach((button) => button.addEventListener("click", () => hideOverlay()));
  fullMode.querySelector("[data-add-logic-action]")?.addEventListener("click", addLogicActionFromGraph);
  const actionLabels = Object.fromEntries(
    Object.entries(state.registry?.actions || {}).map(([key, spec]) => [key, spec.label || key]),
  );
  renderLogicGraph(document.getElementById("ub-logic-graph"), {
    actions: state.actions || [],
    nodes: state.nodes || [],
    conditions: state.conditions || [],
    actionLabels,
    onEmptyAction: addLogicActionFromGraph,
    onSelect: (node) => {
      const raw = node.raw || {};
      if (raw.type === "condition") openLayerInInspector(raw.node_key, "visibility");
      else if (raw.type === "action" || raw.type === "layer") openLayerInInspector(raw.node_key, "actions");
      else if (raw.node_key) openLayerInInspector(raw.node_key, "actions");
    },
  });
}

async function toggleCapability(capabilityId, enable) {
  const current = new Set(state.data.enabled_capabilities || []);
  if (enable) current.add(capabilityId);
  else current.delete(capabilityId);
  // Keep core always on — composition shell depends on it.
  current.add("core");
  const result = await api.updateProject(projectId, { enabled_capabilities: [...current] });
  state.data.enabled_capabilities = result.enabled_capabilities || [...current];
  toast(enable ? `${labelize(capabilityId)} connected` : `${labelize(capabilityId)} disconnected`);
  showOverlay("connection");
}

async function renderConnectionMode() {
  fullMode.innerHTML = `<div class="ub-mode-page ub-mode-page--graph"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Connection</p><h1>Connection graph</h1><p>Enable capabilities on this composition and link Community packages. Credentials stay on the account — Studio only composes what is attached here.</p></div><div class="ub-mode-page__actions"><a class="ub-btn" href="/app/settings#account">Account</a><button type="button" class="ub-btn ub-btn--primary" data-open-community>Browse Community</button></div></div><div id="ub-connection-graph" class="ub-graph-host"><div class="ub-loading">Loading…</div></div><div id="ub-connection-body"></div></div>`;
  fullMode.querySelector("[data-open-community]")?.addEventListener("click", () => openCommunity());
  const enabled = new Set(state.data?.enabled_capabilities || []);
  const registry = state.data?.capability_registry || {};
  try {
    const { installations } = await api.installedPackages(projectId);
    renderConnectionGraph(document.getElementById("ub-connection-graph"), {
      capabilities: [...enabled],
      installations: installations || [],
      onSelect: (node) => {
        if (node.kind === "package" || node.raw?.type === "package") showOverlay("marketplace");
        if (node.kind === "capability" || node.raw?.type === "capability") {
          const id = node.raw?.value || node.title;
          const el = fullMode.querySelector(`[data-cap-id="${CSS.escape(String(id))}"]`);
          el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
          el?.classList.add("is-flash");
          setTimeout(() => el?.classList.remove("is-flash"), 900);
        }
      },
    });
    const catalog = Object.entries(registry)
      .filter(([id]) => id !== "core")
      .sort((a, b) => a[0].localeCompare(b[0]));
    const body = document.getElementById("ub-connection-body");
    body.innerHTML = `<div class="ub-data-layout ub-connection-layout" style="margin-top:16px">
      <section class="ub-section-box"><h3>Capabilities</h3><p class="ub-dialog__hint">Toggle what this composition can use. Core stays on.</p>
        <div class="ub-cap-list">${catalog.map(([id, spec]) => {
          const on = enabled.has(id);
          return `<div class="ub-cap-row${on ? " is-on" : ""}" data-cap-id="${esc(id)}"><div><strong>${esc(labelize(id))}</strong><small>${esc(spec.description || "")}</small></div><button type="button" class="ub-btn ${on ? "" : "ub-btn--primary"}" data-toggle-cap="${esc(id)}" data-enable="${on ? "0" : "1"}">${on ? "Disconnect" : "Connect"}</button></div>`;
        }).join("") || '<div class="ub-empty-panel"><p>Capability registry unavailable.</p></div>'}</div>
      </section>
      <section class="ub-section-box"><h3>Community packages</h3><p class="ub-dialog__hint">Import on the web Community, then manage installs here.</p>
        <p><strong>${(installations || []).length}</strong> installed</p>
        <div class="ub-dialog__actions"><button type="button" class="ub-btn" data-open-installed>Manage installed</button><button type="button" class="ub-btn ub-btn--primary" data-open-community-2>Open Community</button></div>
      </section>
    </div>`;
    body.querySelectorAll("[data-toggle-cap]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await toggleCapability(button.dataset.toggleCap, button.dataset.enable === "1");
        } catch (error) {
          button.disabled = false;
          toast(error.message, "error");
        }
      });
    });
    body.querySelector("[data-open-installed]")?.addEventListener("click", () => showOverlay("marketplace"));
    body.querySelector("[data-open-community-2]")?.addEventListener("click", () => openCommunity());
  } catch (error) {
    document.getElementById("ub-connection-graph").innerHTML = `<div class="ub-empty-panel"><strong>Could not load packages</strong><p>${esc(error.message)}</p></div>`;
  }
}

async function renderMarketplaceMode() {
  // Project-local installs only — browse/discover lives on the product Community page.
  fullMode.innerHTML = '<div class="ub-mode-page"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">This composition</p><h1>Installed packages</h1><p>Updates and removals for packages already linked to this composition. Browse and import from Community.</p></div><a class="ub-btn ub-btn--primary" href="#" data-open-community="1">Open Community</a></div><div id="ub-market-results"><div class="ub-loading">Loading packages…</div></div></div>';
  try {
    const { installations } = await api.installedPackages(projectId);
    const installed = new Map(installations.map((item) => [item.package_id, item]));
    const results = document.getElementById("ub-market-results");
    results.innerHTML = `<div class="ub-definition-stack">${installations.map((item) => `<article class="ub-card"><div class="ub-action-card__head"><div><span class="ub-badge">${esc(item.local_state)}</span><h2>${esc(item.package?.name || item.package_id)}</h2><p>Installed v${esc(item.version)}${item.update_available ? ` · v${esc(item.latest_version)} available` : " · Up to date"}</p></div><div><button class="ub-btn" data-package-detail="${esc(item.package_id)}">View</button> ${item.update_available ? `<button class="ub-btn ub-btn--primary" data-package-update="${esc(item.package_id)}">Review update</button>` : ""} <button class="ub-danger-link" data-package-remove="${esc(item.package_id)}">Remove</button></div></div></article>`).join("") || '<div class="ub-card ub-empty-panel"><strong>No installed packages</strong><p>Browse Community to import a template or component into this composition.</p><p><a class="ub-btn ub-btn--primary" href="#" data-open-community="1">Open Community</a></p></div>'}</div>`;
    results.querySelectorAll("[data-package-detail]").forEach((button) => button.addEventListener("click", () => marketplaceDetail(button.dataset.packageDetail, installed.get(button.dataset.packageDetail))));
    results.querySelectorAll("[data-package-update]").forEach((button) => button.addEventListener("click", () => marketplaceDetail(button.dataset.packageUpdate, installed.get(button.dataset.packageUpdate), true)));
    results.querySelectorAll("[data-package-remove]").forEach((button) => button.addEventListener("click", () => removePackageFlow(button.dataset.packageRemove)));
  } catch (error) {
    document.getElementById("ub-market-results").innerHTML = `<div class="ub-card ub-empty-panel"><strong>Could not load installed packages</strong><p>${esc(error.message)}</p></div>`;
  }
}

async function marketplaceDetail(packageId, installation = null, updating = false) {
  showModal('<div class="ub-loading">Checking package and dependencies…</div>');
  try {
    const item = await api.marketplacePackage(packageId);
    if (item.package_type === "template" && !installation) {
      modal.querySelector("#ub-modal-content").innerHTML = `<div class="ub-dialog__head"><div><p class="ub-eyebrow">Template · v${esc(item.version)}</p><h2>${esc(item.name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>${esc(item.description)}</p><div class="ub-package-preview"><strong>Immutable template preview</strong><p>Creates a normal editable Universal Project. The original stays unchanged and lineage is preserved.</p></div><div class="ub-dialog__actions"><button class="ub-danger-link" data-report>Report</button><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-remix-market>Remix into new Project</button></div>`;
      modal.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => modal.close())); modal.querySelector("[data-report]").addEventListener("click", () => reportPackageDialog(packageId, item.name)); modal.querySelector("[data-remix-market]").addEventListener("click", async (event) => { event.target.disabled = true; event.target.textContent = "Creating remix…"; try { const result = await api.remixPackage(packageId, { name: `My ${item.name}` }); location.href = `${studioBase()}/p/${result.project_id}`; } catch (error) { event.target.disabled = false; event.target.textContent = "Remix into new Project"; toast(error.message, "error"); } }); return;
    }
    const preview = await api.installPreview(projectId, packageId); const permissions = preview.permissions || [];
    const canFork = !updating && item.package_type !== "template" && (item.usage_rights || []).includes("fork");
    modal.querySelector("#ub-modal-content").innerHTML = `<div class="ub-dialog__head"><div><p class="ub-eyebrow">${esc(labelize(item.package_type))} · v${esc(preview.version)}</p><h2>${updating ? "Update " : ""}${esc(item.name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>${esc(item.description)}</p><div class="ub-data-layout"><section class="ub-card"><h3>Resources</h3><p>${preview.resources.components} Component · ${preview.resources.tokens} Design Tokens</p><h3>Dependencies</h3><p>${preview.dependencies.length ? preview.dependencies.map((value) => `${esc(value.package_id)} v${esc(value.version)}`).join("<br>") : "No package dependencies"}</p><h3>Capabilities</h3><p>${(item.required_capabilities || []).map(esc).join(" · ") || "No extra capabilities"}</p></section><section class="ub-card"><h3>Permissions</h3>${permissions.length ? permissions.map((value) => `<label class="ub-field"><span><input type="checkbox" data-grant="${esc(value)}"> Allow ${esc(labelize(value))}</span></label>`).join("") : "<p>No privileged permissions requested.</p>"}<p><small>This affects the Draft only. Your current Published version stays unchanged.</small></p></section></div><div class="ub-dialog__actions"><button class="ub-danger-link" data-report>Report</button><button class="ub-btn" data-close>Cancel</button>${canFork ? '<button class="ub-btn" data-fork>Fork</button>' : ""}<button class="ub-btn ub-btn--primary" data-confirm-market>${updating ? "Create checkpoint & update" : "Install into Project"}</button></div>`;
    modal.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => modal.close())); modal.querySelector("[data-report]")?.addEventListener("click", () => reportPackageDialog(packageId, item.name)); modal.querySelector("[data-fork]")?.addEventListener("click", () => forkPackageFlow(packageId, item.name)); modal.querySelector("[data-confirm-market]").addEventListener("click", async (event) => { const granted = [...modal.querySelectorAll("[data-grant]:checked")].map((input) => input.dataset.grant); event.target.disabled = true; event.target.textContent = updating ? "Updating safely…" : "Installing atomically…"; try { const result = updating ? await api.updatePackage(projectId, packageId, { granted_permissions: granted.length ? granted : installation?.granted_permissions || [] }) : await api.marketplaceInstall(projectId, packageId, { granted_permissions: granted }); modal.close(); await load(activeDocument().id); showOverlay("marketplace"); toast(result.message); } catch (error) { event.target.disabled = false; event.target.textContent = updating ? "Create checkpoint & update" : "Install into Project"; toast(error.message, "error"); } });
  } catch (error) { modal.querySelector("#ub-modal-content").innerHTML = `<div class="ub-dialog__head"><h2>Cannot use this package</h2><button class="ub-icon-btn" data-close>×</button></div><div class="ub-issue ub-issue--error">${esc(error.message)}</div>`; modal.querySelector("[data-close]").addEventListener("click", () => modal.close()); }
}

function showModal(html, afterRender) { document.getElementById("ub-modal-content").innerHTML = html; modal.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => modal.close())); modal.showModal(); afterRender?.(); }

async function removePackageFlow(packageId) {
  try {
    await api.removePackage(projectId, packageId);
    toast("Package removed"); await load(activeDocument().id); showOverlay("marketplace");
  } catch (error) {
    const payload = error.payload || {};
    if (error.status === 409 && (payload.options || []).includes("detach_local_resources")) {
      const instances = payload.component_instances || 0; const dependents = (payload.dependent_packages || []).length;
      showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Still in use</p><h2>Keep a local copy?</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>This package can't be removed cleanly yet${instances ? ` — ${instances} Component instance${instances === 1 ? "" : "s"} still use it` : ""}${dependents ? `${instances ? " and" : ""} ${dependents} other package${dependents === 1 ? "" : "s"} depend on it` : ""}.</p><p>You can detach instead: your Project keeps the resources as plain local copies and stops tracking Community package updates. Nothing is deleted.</p><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-detach>Detach &amp; keep local copy</button></div>`, () => {
        modal.querySelector("[data-detach]").addEventListener("click", async (event) => { event.target.disabled = true; event.target.textContent = "Detaching…"; try { await api.removePackage(projectId, packageId, { resolution: "detach_local_resources" }); modal.close(); toast("Detached — kept as a local copy"); await load(activeDocument().id); showOverlay("marketplace"); } catch (err) { event.target.disabled = false; event.target.textContent = "Detach & keep local copy"; toast(err.message, "error"); } });
      });
    } else { toast(error.message, "error"); }
  }
}

function forkPackageFlow(packageId, name) {
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Fork creation</p><h2>${esc(name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>Forking creates your own independent copy with a new identity. Attribution and lineage back to the original are preserved, and future updates to the original won't overwrite your fork.</p><label class="ub-field">Your fork's name<input id="ub-fork-name" value="${esc(name)} Remix"></label><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-confirm-fork>Create fork</button></div>`, () => {
    modal.querySelector("[data-confirm-fork]").addEventListener("click", async (event) => { event.target.disabled = true; event.target.textContent = "Forking…"; try { const result = await api.forkPackage(projectId, packageId, { name: document.getElementById("ub-fork-name").value.trim() }); modal.close(); await load(activeDocument().id); showOverlay("marketplace"); toast(`${result.package.name} v${result.package.version} forked`); } catch (error) { event.target.disabled = false; event.target.textContent = "Create fork"; toast(error.message, "error"); } });
  });
}

function reportPackageDialog(packageId, name) {
  const reasons = [["spam", "Spam"], ["malicious", "Malicious package"], ["copyright", "Copyright issue"], ["misleading", "Misleading content"], ["unsafe", "Unsafe content"], ["privacy", "Privacy / data exposure"], ["broken", "Broken package"]];
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Report</p><h2>${esc(name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div><p>Reports go to moderation with the package's evidence and status. A single report never removes content automatically.</p><label class="ub-field">Reason<select id="ub-report-reason">${reasons.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label><label class="ub-field">Details (optional)<textarea id="ub-report-details" placeholder="Add anything that helps moderators"></textarea></label><div class="ub-dialog__actions"><button class="ub-btn" data-close>Cancel</button><button class="ub-btn ub-btn--primary" data-confirm-report>Submit report</button></div>`, () => {
    modal.querySelector("[data-confirm-report]").addEventListener("click", async (event) => { event.target.disabled = true; event.target.textContent = "Submitting…"; try { await api.reportPackage(packageId, { reason: document.getElementById("ub-report-reason").value, details: document.getElementById("ub-report-details").value.trim() }); modal.close(); toast("Report submitted for review"); } catch (error) { event.target.disabled = false; event.target.textContent = "Submit report"; toast(error.message, "error"); } });
  });
}

function setBreakpoint(breakpoint) { document.querySelector(`[data-breakpoint="${breakpoint}"]`)?.click(); }
function goHome() { const surfaceId = activeSurface()?.id; const home = state.data.documents.find((item) => item.status === "active" && item.route === "/" && item.surface_id === surfaceId); if (home) return load(home.id); toast("No page owns / on this site yet. Use Make homepage (or set a page's route to /) to create one.", "info"); }
function openWorkflows() { showOverlay("workflows"); }

function showCommandPalette(){const commands=[["Add button",()=>addComponent("button",bestParent())],["Add text",()=>addComponent("text",bestParent())],["Add section",()=>addComponent("section",null)],["Create page",createPage],["Edit page route",editPageRoute],["Go to home",goHome],["Create component",()=>selectedNode()?createComponentDialog():toast("Select a layer first")],["Create data model",()=>{showOverlay("data");newModelDialog();}],["Add workflow",openWorkflows],["Open Components",()=>{state.panel="components";renderLeft();}],["Open Design System",()=>{showOverlay("design");}],["Change theme",()=>{showOverlay("design");}],["Open Data",()=>{showOverlay("data");}],["Open Community",()=>openCommunity()],["Preview desktop",()=>setBreakpoint("desktop")],["Preview tablet",()=>setBreakpoint("tablet")],["Preview mobile",()=>setBreakpoint("mobile")],["Preview page",()=>document.getElementById("ub-preview").click()],["Publish",()=>openPrimitive("publish")]];showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Command palette</p><h2>Go anywhere</h2></div><button class="ub-icon-btn" data-close>×</button></div><input class="ub-search" id="ub-command-search" autofocus placeholder="Search commands"><div id="ub-command-list">${commands.map(([label],index)=>`<button class="ub-data-item" data-command="${index}">${esc(label)}</button>`).join("")}</div>`,()=>{const paint=()=>{const query=document.getElementById("ub-command-search").value.toLowerCase();modal.querySelectorAll("[data-command]").forEach((button)=>button.classList.toggle("hidden",!button.textContent.toLowerCase().includes(query)));};document.getElementById("ub-command-search").addEventListener("input",paint);modal.querySelectorAll("[data-command]").forEach((button)=>button.addEventListener("click",()=>{modal.close();commands[Number(button.dataset.command)][1]();}));});}

async function saveVersion() { const note = prompt("Version note", "Manual version"); if (note === null) return; await api.revision(projectId, note); toast("Version saved"); }
async function showHistory() { const { revisions } = await api.revisions(projectId); showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Project history</p><h2>Versions</h2></div><button class="ub-icon-btn" data-close>×</button></div>${revisions.map((item) => `<div class="ub-action-card"><div class="ub-action-card__head"><strong>Version ${item.revision_number} ${item.kind === "published" ? "· Published" : ""}</strong><button class="ub-btn" data-restore="${item.id}">Restore as draft</button></div><p>${esc(item.note || "Saved version")}</p><small>${esc(item.created_at)}</small></div>`).join("")}`, () => modal.querySelectorAll("[data-restore]").forEach((button) => button.addEventListener("click", async () => { if (!confirm("Restore this version as the current draft? A backup of your current draft will be created.")) return; await api.restore(projectId, Number(button.dataset.restore)); modal.close(); await load(); toast("Version restored as draft"); })) ); }

function validatePublish() {
  const issues = []; const keys = new Set(state.nodes.map((node) => node.key));
  if (state.data.legacy_source_type === "workspace_system") issues.push({ level: "info", message: "Native and hybrid pages will publish while unmigrated routes keep their existing compatible implementation." });
  state.nodes.forEach((node) => { if (node.parent_key && !keys.has(node.parent_key)) issues.push({ level: "error", message: `${node.metadata?.display_label || state.registry.components[node.component_type]?.label || node.component_type} has a missing parent` }); const required = state.registry.components[node.component_type]?.required_capabilities || []; required.forEach((cap) => { if (!(state.data.enabled_capabilities || []).includes(cap)) issues.push({ level: "error", message: `${state.registry.components[node.component_type].label} needs ${cap}` }); }); });
  state.bindings.forEach((binding) => { if (binding.source_type === "collection" && !state.data.data_models.some((model) => model.model_key === binding.source_config?.model_key)) issues.push({ level: "error", message: `A data connection points to a missing collection` }); });
  state.bindings.forEach((binding) => { if (binding.source_type === "domain" && !state.data.data_source_registry?.[binding.source_config?.source_id]) issues.push({ level: "error", message: `A data connection points to an unavailable app data source` }); });
  state.actions.forEach((action) => { const fields = state.registry.actions[action.action_type]?.fields || {}; Object.keys(fields).forEach((key) => { if (!action.configuration?.[key]) issues.push({ level: "warning", message: `${state.registry.actions[action.action_type].label} may need ${labelize(key)}` }); }); });
  if (!state.nodes.length) issues.push({ level: "warning", message: "This page is empty" }); return issues;
}

async function renderPublishMode() {
  const issues = validatePublish();
  const errors = issues.filter((item) => item.level === "error");
  const warnings = issues.filter((item) => item.level === "warning");
  const infos = issues.filter((item) => item.level === "info");
  let revisions = [];
  try {
    const payload = await api.revisions(projectId);
    revisions = payload.revisions || [];
  } catch {
    revisions = [];
  }
  const recent = revisions.slice(0, 8);
  const channels = [
    { id: "web", label: "Web", status: "active", note: "Immutable public revision" },
    { id: "qr", label: "QR", status: "active", note: "Same web surface via QR entry" },
    { id: "pwa", label: "PWA", status: "planned", note: "Installable shell via Connection" },
    { id: "api", label: "API", status: "active", note: "Published data endpoints where enabled" },
    { id: "firmware", label: "Firmware", status: "planned", note: "Device adapters later" },
    { id: "model_api", label: "Model API", status: "planned", note: "Model adapters later" },
  ];
  fullMode.innerHTML = `<div class="ub-mode-page"><div class="ub-mode-page__head"><div><p class="ub-eyebrow">Publish</p><h1>Ship this composition</h1><p>Preflight checks, then publish an immutable web revision. Draft editing stays separate. Community packaging stays on the web.</p></div><div class="ub-mode-page__actions"><button type="button" class="ub-btn" id="ub-publish-checkpoint">Save checkpoint</button><button type="button" class="ub-btn ub-btn--primary" id="ub-publish-now" ${errors.length ? "disabled" : ""}>Publish web revision</button></div></div>
    <div class="ub-data-layout ub-publish-layout">
      <section class="ub-section-box"><h3>Preflight</h3>${
        issues.length
          ? issues.map((item) => `<div class="ub-issue ub-issue--${item.level}">${esc(item.message)}</div>`).join("")
          : '<div class="ub-issue ub-issue--info">No issues — ready to publish.</div>'
      }<p class="ub-dialog__hint" style="margin-top:10px">${errors.length} error${errors.length === 1 ? "" : "s"} · ${warnings.length} warning${warnings.length === 1 ? "" : "s"}${infos.length ? ` · ${infos.length} note${infos.length === 1 ? "" : "s"}` : ""}</p></section>
      <section class="ub-section-box"><h3>Channels</h3><ul class="ub-list ub-publish-channels">${channels.map((c) => `<li><strong>${esc(c.label)}</strong> <span class="ub-badge ${c.status === "active" ? "ub-badge--official" : ""}">${esc(c.status)}</span><br><small>${esc(c.note)}</small></li>`).join("")}</ul></section>
    </div>
    <div class="ub-section-box"><h3>Revision history</h3>${
      recent.length
        ? recent.map((item) => `<div class="ub-action-card"><div class="ub-action-card__head"><strong>Version ${esc(item.revision_number)}${item.kind === "published" ? " · Published" : ""}</strong><button type="button" class="ub-btn" data-restore="${item.id}">Restore as draft</button></div><p>${esc(item.note || "Saved version")}</p><small>${esc(item.created_at || "")}</small></div>`).join("")
        : "<p>No revisions yet. Publish or save a checkpoint to create the first one.</p>"
    }</div>
    <div class="ub-section-box"><h3>Community</h3><p>Browse packages on the web Community, then import into this composition. Community never runs inside the editor shell.</p><button type="button" class="ub-btn" data-open-community>Open Community in browser</button></div></div>`;
  fullMode.querySelector("#ub-publish-now")?.addEventListener("click", () => publishProject());
  fullMode.querySelector("#ub-publish-checkpoint")?.addEventListener("click", async () => {
    try {
      await api.revision(projectId, "Manual checkpoint from Publish");
      toast("Checkpoint saved");
      showOverlay("publish");
    } catch (error) {
      toast(error.message, "error");
    }
  });
  fullMode.querySelector("[data-open-community]")?.addEventListener("click", () => openCommunity());
  fullMode.querySelectorAll("[data-restore]").forEach((button) => button.addEventListener("click", async () => {
    if (!confirm("Restore this version as the current draft? A backup of your current draft will be created.")) return;
    try {
      await api.restore(projectId, Number(button.dataset.restore));
      await load();
      toast("Version restored as draft");
      showOverlay("publish");
    } catch (error) {
      toast(error.message, "error");
    }
  }));
}

async function publishProject() {
  const issues = validatePublish();
  const errors = issues.filter((item) => item.level === "error");
  if (errors.length) {
    showOverlay("publish");
    return showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Publish check</p><h2>Fix these issues first</h2></div><button class="ub-icon-btn" data-close>×</button></div>${issues.map((item) => `<div class="ub-issue ub-issue--${item.level}">${esc(item.message)}</div>`).join("")}`);
  }
  const result = await api.publish(projectId, "Published from Studio");
  const liveUrl = isOfficialSystem() && isNativeDocument() ? activeDocument().route : `${result.public_url}/${activeDocument().key}`;
  showModal(`<div class="ub-dialog__head"><div><p class="ub-eyebrow">Published</p><h2>Your composition is live</h2></div><button class="ub-icon-btn" data-close>×</button></div>${issues.map((item) => `<div class="ub-issue">${esc(item.message)}</div>`).join("")}<p>Draft editing remains separate from this published revision.</p><div class="ub-dialog__actions"><a class="ub-btn ub-btn--primary" href="${esc(liveUrl)}" target="_blank" rel="noopener">Open published page</a><button type="button" class="ub-btn" data-back-publish>Back to Publish</button></div>`);
  modal.querySelector("[data-back-publish]")?.addEventListener("click", () => { modal.close(); showOverlay("publish"); });
}

async function undo() { const entry = state.undo.pop(); if (!entry) return; if (entry.type === "patch") { state.redo.push(entry); await applyNodePatch(entry.key, entry.before, { quiet: true }); } else toast("This change can be restored from version history", "info"); updateHistoryButtons(); }
async function redo() { const entry = state.redo.pop(); if (!entry) return; if (entry.type === "patch") { state.undo.push(entry); await applyNodePatch(entry.key, entry.after, { quiet: true }); } updateHistoryButtons(); }

document.querySelectorAll("[data-primitive]").forEach((button) => button.addEventListener("click", () => openPrimitive(button.dataset.primitive)));
document.querySelectorAll("[data-panel]").forEach((button) => button.addEventListener("click", () => { state.panel = button.dataset.panel; renderLeft(); }));
document.querySelectorAll("[data-breakpoint]").forEach((button) => button.addEventListener("click", () => { state.breakpoint = button.dataset.breakpoint; document.querySelectorAll("[data-breakpoint]").forEach((item) => item.classList.toggle("is-active", item === button)); renderCanvasView(); if (state.inspectorTab === "responsive") renderInspector(); }));
document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", async () => {
  const newMode = button.dataset.mode;
  if (newMode === "freeform" && state.mode !== "freeform") {
    await captureStructuredPositions();
  }
  state.mode = newMode;
  document.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("is-active", item === button));
  renderCanvasView();
  if (state.panel === "layers") renderLayersPanel();
  renderInspector();
  toast(`Switched to ${state.mode} mode`, "info");
}));
const surfaceSelect = document.getElementById("ub-surface-select");
if (surfaceSelect) surfaceSelect.addEventListener("change", async (event) => { if (event.target.value === "new") return createSurface(); const page = state.data.documents.find((item) => item.surface_id === Number(event.target.value) && item.status === "active"); if (page) await load(page.id); });
const pageSelect = document.getElementById("ub-page-select");
if (pageSelect) pageSelect.addEventListener("change", (event) => event.target.value === "new" ? createPage() : load(Number(event.target.value)));
document.getElementById("ub-project-name").addEventListener("change", async (event) => { await api.updateProject(projectId, { name: event.target.value.trim() }); state.data.name = event.target.value.trim(); toast("Composition renamed"); });
document.getElementById("ub-undo").addEventListener("click", undo); document.getElementById("ub-redo").addEventListener("click", redo);
document.getElementById("ub-preview").addEventListener("click", () => {
  const page = activeDocument();
  if (isOfficialSystem() && !isNativeDocument() && page?.route?.startsWith("/") && !page.route.includes("{") && !page.route.includes("*")) return window.open(page.route, "_blank", "noopener");
  window.open(`/api/builder-core/projects/${projectId}/preview/${encodeURIComponent(page.key)}?lang=${state.locale === "base" ? (document.documentElement.lang || "en") : state.locale}`, "_blank", "noopener");
});
document.getElementById("ub-publish").addEventListener("click", () => openPrimitive("publish"));
document.getElementById("ub-open-community")?.addEventListener("click", (event) => {
  event.preventDefault();
  openCommunity();
});
(function bindAccountMenu() {
  const btn = document.getElementById("ub-account-btn");
  const menu = document.getElementById("ub-account-menu");
  if (!btn || !menu) return;
  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = menu.classList.toggle("hidden") === false;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("click", () => {
    menu.classList.add("hidden");
    btn.setAttribute("aria-expanded", "false");
  });
  menu.addEventListener("click", (event) => event.stopPropagation());
  menu.querySelector("[data-open-design-menu]")?.addEventListener("click", () => {
    menu.classList.add("hidden");
    showOverlay("design");
  });
})();
canvas.addEventListener("click", (event) => { if (event.target === canvas) selectNode(null); });
document.addEventListener("keydown", (event) => {
  const meta = event.metaKey || event.ctrlKey; const key = event.key.toLowerCase();
  if (meta && key === "k") { event.preventDefault(); showCommandPalette(); return; }
  if (event.key === "Escape") { if (modal.open) { modal.close(); return; } if (state.overlay) { hideOverlay(); return; } if (state.selectedKeys.length) { selectNode(null); } return; }
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.target.isContentEditable) return;
  if (meta && key === "a") { event.preventDefault(); selectAllNodes(); return; }
  if (meta && key === "p") { event.preventDefault(); document.getElementById("ub-preview").click(); return; }
  if (meta && key === "u") { event.preventDefault(); openPrimitive("publish"); return; }
  if (meta && key === "z") { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
  if (meta && key === "d") { event.preventDefault(); duplicateSelected(); return; }
  if (meta && key === "s") { event.preventDefault(); saveVersion(); return; }
  if (!meta && event.key === "Enter" && state.selectedKey) { const node = selectedNode(); if (node && canNest(state, "text", node.key)) { enterComponent(node.key); return; } }
  if (!meta && event.key === "[") { selectParent(); return; }
  if (!meta && event.key === "]") { selectChild(); return; }
  if ((event.key === "Delete" || event.key === "Backspace") && selectedNode()) deleteSelected();
});

function labelize(value) { return String(value).replace(/([A-Z])/g, " $1").replaceAll("_", " ").replace(/^./, (char) => char.toUpperCase()); }
function slug(value) { return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "page"; }

load();

document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-open-community]");
  if (!link) return;
  event.preventDefault();
  openCommunity(link.dataset.package || "");
});
