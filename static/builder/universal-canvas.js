const esc = (value = "") => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

export function effectiveStyles(node, breakpoint) {
  return { ...(node.styles || {}), ...((node.responsive || {})[breakpoint] || {}) };
}

function styleText(node, breakpoint) {
  const allowed = { background: "background", color: "color", padding: "padding", margin: "margin", gap: "gap", fontSize: "font-size", fontWeight: "font-weight", textAlign: "text-align", borderRadius: "border-radius", display: "display", width: "width", minHeight: "min-height", opacity: "opacity", flexDirection: "flex-direction", alignItems: "align-items", justifyContent: "justify-content" };
  return Object.entries(effectiveStyles(node, breakpoint)).filter(([key]) => allowed[key]).map(([key, value]) => `${allowed[key]}:${String(value).startsWith("token:") ? `var(--ub-token-${String(value).slice(6).replaceAll(".", "-")})` : String(value).replaceAll(";", "")}`).join(";");
}

function previewRecords(state, modelKey) {
  return state.recordCache?.[modelKey] || [];
}

function bindingFor(state, key, property) {
  return state.bindings.find((item) => item.node_key === key && item.binding_key === property);
}

function boundPreview(state, node, property, fallback) {
  const binding = bindingFor(state, node.key, property);
  if (!binding) return fallback;
  if (binding.source_type === "literal") return binding.source_config?.value ?? fallback;
  if (binding.source_type === "collection") return previewRecords(state, binding.source_config?.model_key);
  if (binding.source_type === "domain") return previewRecords(state, binding.source_config?.source_id);
  if (binding.source_type === "item") return `{{ current item.${binding.source_config?.path || "field"} }}`;
  return `{{ ${binding.source_config?.path || binding.source_config?.key || "data"} }}`;
}

function reusablePreview(state, definition, instance) {
  const structure = structuredClone(definition?.root_structure || []); const children = new Map();
  const variant = definition?.variants?.[instance?.variant] || {}; const exposed = definition?.property_schema?.properties || {};
  structure.forEach((node) => { const patch = variant.overrides?.[node.key] || {}; node.props = { ...(node.props || {}), ...(patch.props || {}) }; node.styles = { ...(node.styles || {}), ...(patch.styles || {}) }; if (patch.visibility) node.visibility = patch.visibility; });
  Object.entries(instance?.overrides || {}).forEach(([key, value]) => { const exposure = exposed[key]; const node = structure.find((item) => item.key === exposure?.node_key); if (!node) return; if (exposure.property === "visibility") node.visibility = value ? "visible" : "hidden"; else node.props[exposure.property] = value; });
  structure.forEach((node) => { const key = node.parent_key || "__root__"; if (!children.has(key)) children.set(key, []); children.get(key).push(node); });
  const render = (node) => { if (node.visibility === "hidden") return ""; const props = node.props || {}; const nested = (children.get(node.key) || []).sort((a,b)=>(a.order||0)-(b.order||0)).map(render).join(""); const style = styleText(node, state.breakpoint);
    if (node.component_type === "heading") return `<div class="ub-render-heading" style="${style}">${esc(props.text || "Heading")}</div>`;
    if (node.component_type === "text") return `<p style="${style}">${esc(props.body || "Text")}</p>`;
    if (node.component_type === "image") return props.src ? `<img class="ub-render-image" src="${esc(props.src)}" alt="${esc(props.alt || "")}" style="${style}">` : '<div class="ub-render-placeholder">Product image</div>';
    if (node.component_type === "button") return `<span class="ub-render-button" style="${style}">${esc(props.label || "Continue")}</span>`;
    if (node.component_type === "navigation") return `<div class="ub-render-navigation" style="${style}"><strong>${esc(props.brand||"Brand")}</strong><span>${esc(props.links||"").split("\n").map((line)=>line.split("|")[0]).join(" · ")}</span></div>${nested}`;
    if (node.component_type === "header") return `<div style="${style}"><div class="ub-render-heading">${esc(props.title||"Header")}</div><p>${esc(props.subtitle||"")}</p>${nested}</div>`;
    if (node.component_type === "app_module") return `<div class="ub-render-module"><span>App Module</span><strong>${esc(props.title||"Module")}</strong><p>${esc(props.module_id||"")}</p></div>`;
    if (node.component_type === "app_shell") return `<div class="ub-render-app-shell"><strong>Reusable Business App Shell</strong><p>Controlled shell slots</p></div>${nested}`;
    return `<div class="ub-definition-${esc(node.component_type)}" style="${style}">${nested}</div>`;
  };
  return (children.get("__root__") || []).map(render).join("");
}

function componentBody(state, node) {
  const props = { ...(node.props || {}), ...(state.locale !== "base" ? ((node.translations || {})[state.locale] || {}) : {}) };
  switch (node.component_type) {
    case "component_instance": { const instance = (state.data?.component_instances || []).find((item) => item.node_key === node.key); const definition = (state.data?.component_definitions || []).find((item) => item.id === instance?.component_definition_id); return definition ? `<div class="ub-render-reusable"><span class="ub-badge">Reusable · ${esc(definition.name)} · ${esc(instance.variant)}</span>${reusablePreview(state, definition, instance)}</div>` : '<div class="ub-render-placeholder">Missing reusable component</div>'; }
    case "stack": return `<div style="display:flex;flex-direction:${esc(props.direction || "column")};gap:${esc(props.gap || "16px")}"></div>`;
    case "grid": return `<div style="display:grid;grid-template-columns:repeat(${Number(props.columns || 3)},1fr);gap:${esc(props.gap || "16px")}"></div>`;
    case "overlay": return '<div class="ub-render-placeholder">Overlay layout</div>';
    case "navigation": return `<div class="ub-render-navigation"><strong data-inline-property="brand">${esc(props.brand || "Brand")}</strong><span>${esc(props.links || "Home|/").split("\n").map((line) => line.split("|")[0]).join(" · ")}</span></div>`;
    case "hero": return `<div class="ub-render-hero"><small data-inline-property="eyebrow">${esc(props.eyebrow || "WELCOME")}</small><div class="ub-render-heading" data-inline-property="title">${esc(props.title || "Build something meaningful")}</div><p data-inline-property="body">${esc(props.body || "Add your message")}</p></div>`;
    case "heading": return `<div class="ub-render-heading" data-inline-property="text">${esc(boundPreview(state, node, "text", props.text || "New heading"))}</div>`;
    case "header": return `<div><div class="ub-render-heading" data-inline-property="title">${esc(props.title || "Header")}</div><p data-inline-property="subtitle">${esc(props.subtitle || "Add a subtitle")}</p></div>`;
    case "text": return `<p class="ub-render-text" data-inline-property="body">${esc(boundPreview(state, node, "body", props.body || "Add your text"))}</p>`;
    case "info": return `<div><strong data-inline-property="title">${esc(props.title || "Information")}</strong><p data-inline-property="body">${esc(props.body || "Add details")}</p></div>`;
    case "button": return `<span class="ub-render-button" data-inline-property="label">${esc(props.label || "Continue")}</span>`;
    case "image": return props.src ? `<img class="ub-render-image" src="${esc(props.src)}" alt="${esc(props.alt || "")}">` : '<div class="ub-render-placeholder">Choose an image</div>';
    case "booking": return `<div class="ub-render-placeholder"><strong data-inline-property="title">${esc(props.title || "Book your visit")}</strong><p>Booking form · Existing Booking capability</p><button class="ub-render-button" type="button">Request booking</button></div>`;
    case "survey": return `<div class="ub-render-placeholder"><strong>${esc(props.title || "Survey")}</strong><p>${esc(props.body || "Collect responses")}</p></div>`;
    case "shop": return `<div class="ub-render-placeholder"><strong>Storefront</strong><p>${esc(props.subtitle || "Products and checkout")}</p></div>`;
    case "repeater": {
      const items = boundPreview(state, node, "items", []);
      return Array.isArray(items) && items.length ? `<div class="ub-render-grid">${items.slice(0, 6).map((record) => `<article class="ub-render-card">${Object.entries(record.data || record).map(([key, value]) => `<p><strong>${esc(key)}</strong>: ${esc(value)}</p>`).join("")}</article>`).join("")}</div>` : `<div class="ub-render-placeholder">${esc(props.empty_text || "Connect a data collection")}</div>`;
    }
    case "store_grid": {
      const items = boundPreview(state, node, "items", []);
      return `<div><strong data-inline-property="title">${esc(props.title || "Stores")}</strong>${Array.isArray(items) && items.length ? `<div class="ub-render-grid">${items.slice(0, Number(props.limit || 6)).map((record) => `<article class="ub-render-card"><strong>${esc(record.name || "Store")}</strong><p>${esc(record.description || "")}</p></article>`).join("")}</div>` : `<div class="ub-render-placeholder">${esc(props.empty_text || "Connect Commerce · Stores")}</div>`}</div>`;
    }
    case "app_shell": return '<div class="ub-render-app-shell"><strong>Native Business App Shell</strong><p>Drop navigation, headers and App Modules into named shell slots.</p></div>';
    case "app_module": { const module = state.data?.app_module_registry?.[props.module_id]; return `<div class="ub-render-module"><span>App Module</span><strong>${esc(props.title || module?.name || props.module_id)}</strong><p>${esc(module?.legacy_adapter || "Controlled module host")}</p>${module?.manager_url ? `<a href="${esc(module.manager_url)}" target="_blank">Open manager</a>` : ""}</div>`; }
    case "form": {
      const model = (state.data?.data_models || []).find((m) => m.model_key === props.target_model);
      const modelLabel = model ? model.name : (props.target_model || "No collection");
      return `<div class="ub-render-placeholder ub-render-form"><strong data-inline-property="title">${esc(props.title || "Submit")}</strong><p>Collect data → ${esc(modelLabel)}</p><div class="ub-render-form__fields"><em>Form fields appear below</em></div><button class="ub-render-button" type="button">${esc(props.submit_label || "Submit")}</button></div>`;
    }
    case "form_field": {
      const typeLabel = { text: "Text input", email: "Email input", number: "Number input", date: "Date picker", textarea: "Text area", checkbox: "Checkbox", select: "Dropdown" };
      return `<div class="ub-render-form-field"><label>${esc(props.label || "Field")}</label><small>${esc(typeLabel[props.field_type] || "Text input")}${props.required ? " · required" : ""}</small></div>`;
    }
    case "section": return "";
    default: return `<div class="ub-render-placeholder">${esc(state.registry.components[node.component_type]?.label || node.component_type)}</div>`;
  }
}

export function canNest(state, childType, parentKey) {
  if (!parentKey) return true;
  const parent = state.nodes.find((item) => item.key === parentKey);
  if (!parent) return false;
  const parentSpec = state.registry.components[parent.component_type] || {};
  const childSpec = state.registry.components[childType] || {};
  const allowsChildren = (parentSpec.allowed_children || []).includes("*") || (parentSpec.allowed_children || []).includes(childType);
  const allowsParent = (childSpec.allowed_parents || []).includes("root") || (childSpec.allowed_parents || []).includes(parent.component_type);
  return allowsChildren && allowsParent;
}

export function getBreakpointPosition(node, breakpoint) {
  const position = node.position || {};
  if (position.desktop || position.tablet || position.mobile) {
    return position[breakpoint] || position.desktop || { x: 0, y: 0, z: 1 };
  }
  return { x: position.x || 0, y: position.y || 0, z: position.z || 1 };
}

export function setBreakpointPosition(node, breakpoint, newPos) {
  const position = node.position || {};
  if (position.desktop || position.tablet || position.mobile || position.x !== undefined) {
    const perBreakpoint = {
      desktop: position.desktop || { x: position.x || 0, y: position.y || 0, z: position.z || 1 },
      tablet: position.tablet || position.desktop || { x: position.x || 0, y: position.y || 0, z: position.z || 1 },
      mobile: position.mobile || position.desktop || { x: position.x || 0, y: position.y || 0, z: position.z || 1 },
    };
    perBreakpoint[breakpoint] = newPos;
    return perBreakpoint;
  }
  return { [breakpoint]: newPos };
}

export function renderCanvas(canvas, state, handlers) {
  const children = new Map();
  state.nodes.forEach((node) => { const key = node.parent_key || "__root__"; if (!children.has(key)) children.set(key, []); children.get(key).push(node); });
  children.forEach((items) => items.sort((a, b) => a.order - b.order));
  const isFreeform = state.mode === "freeform";
  const renderNode = (node) => {
    const nested = (children.get(node.key) || []).map(renderNode).join("");
    const selected = (state.selectedKeys?.length ? state.selectedKeys.includes(node.key) : state.selectedKey === node.key) ? " is-selected" : "";
    const hidden = node.visibility === "hidden" ? "opacity:.45;" : "";
    const label = state.registry.components[node.component_type]?.label || node.component_type;
    const emptyContainer = node.component_type === "section" && !nested ? '<div class="ub-render-placeholder">Drop components here</div>' : "";
    const pos = getBreakpointPosition(node, state.breakpoint);
    const freeformStyle = isFreeform ? `position:absolute;left:${pos.x}px;top:${pos.y}px;z-index:${pos.z};` : "";
    return `<div class="ub-node${selected}" draggable="true" tabindex="0" data-node-key="${esc(node.key)}" data-component="${esc(node.component_type)}" style="${hidden}${freeformStyle}${styleText(node, state.breakpoint)}"><span class="ub-node__tag">${esc(label)}</span><div class="${node.component_type === "section" && !isFreeform ? "ub-render-section" : ""}">${componentBody(state, node)}${nested}${emptyContainer}</div></div>`;
  };
  const roots = children.get("__root__") || [];
  canvas.innerHTML = roots.length ? roots.map(renderNode).join("") : '<div class="ub-canvas-empty"><div><strong>Add your first section</strong><p>Choose a component from Add or drag it here.</p></div></div>';
  if (isFreeform) canvas.style.position = "relative"; else canvas.style.position = "";
  canvas.querySelectorAll("[data-node-key]").forEach((element) => {
    element.addEventListener("click", (event) => { event.stopPropagation(); handlers.select(element.dataset.nodeKey, event); });
    element.addEventListener("dblclick", (event) => {
      event.stopPropagation();
      const nodeKey = element.dataset.nodeKey;
      const node = state.nodes.find((n) => n.key === nodeKey);
      if (!node) return;
      const textProps = { text: "heading", body: "text", label: "button", title: "header", subtitle: "header", eyebrow: "hero" };
      const propToEdit = textProps[node.component_type];
      if (propToEdit) {
        const editable = element.querySelector(`[data-inline-property="${propToEdit}"]`);
        if (editable) {
          editable.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
          return;
        }
      }
      if (canNest(state, "text", nodeKey)) {
        handlers.enter?.(nodeKey);
      }
    });
    element.addEventListener("dragstart", (event) => { event.stopPropagation(); event.dataTransfer.setData("application/x-ub-node", element.dataset.nodeKey); event.dataTransfer.effectAllowed = "move"; });
    element.addEventListener("dragover", (event) => { const type = event.dataTransfer.types.includes("application/x-ub-component") ? event.dataTransfer.getData("application/x-ub-component") : state.nodes.find((item) => item.key === event.dataTransfer.getData("application/x-ub-node"))?.component_type; if (type && canNest(state, type, element.dataset.nodeKey)) { event.preventDefault(); element.classList.add("is-drag-over"); } });
    element.addEventListener("dragleave", () => element.classList.remove("is-drag-over"));
    element.addEventListener("drop", (event) => { event.preventDefault(); event.stopPropagation(); element.classList.remove("is-drag-over"); handlers.drop(event, element.dataset.nodeKey); });
    element.querySelectorAll("[data-inline-property]").forEach((editable) => editable.addEventListener("dblclick", (event) => {
      event.stopPropagation(); editable.contentEditable = "true"; editable.focus(); document.execCommand?.("selectAll", false);
      const finish = () => { editable.contentEditable = "false"; editable.removeEventListener("blur", finish); handlers.inlineEdit(element.dataset.nodeKey, editable.dataset.inlineProperty, editable.textContent.trim()); };
      editable.addEventListener("blur", finish); editable.addEventListener("keydown", (keyEvent) => { if (keyEvent.key === "Enter" && editable.tagName !== "P") { keyEvent.preventDefault(); editable.blur(); } if (keyEvent.key === "Escape") { editable.contentEditable = "false"; handlers.refresh(); } });
    }));
  });
  if (isFreeform) setupFreeformDrag(canvas, state, handlers);
}

function setupFreeformDrag(canvas, state, handlers) {
  canvas.querySelectorAll("[data-node-key]").forEach((element) => {
    let isDragging = false, startX, startY, origX, origY;
    element.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      const node = state.nodes.find((n) => n.key === element.dataset.nodeKey);
      if (!node) return;
      isDragging = true;
      startX = event.clientX; startY = event.clientY;
      const pos = getBreakpointPosition(node, state.breakpoint);
      origX = pos.x; origY = pos.y;
      event.preventDefault();
    });
    document.addEventListener("mousemove", (event) => {
      if (!isDragging) return;
      const dx = event.clientX - startX, dy = event.clientY - startY;
      element.style.left = `${origX + dx}px`; element.style.top = `${origY + dy}px`;
    });
    document.addEventListener("mouseup", async (event) => {
      if (!isDragging) return;
      isDragging = false;
      const dx = event.clientX - startX, dy = event.clientY - startY;
      if (Math.abs(dx) < 5 && Math.abs(dy) < 5) return;
      const node = state.nodes.find((n) => n.key === element.dataset.nodeKey);
      if (!node) return;
      const currentPos = getBreakpointPosition(node, state.breakpoint);
      const position = setBreakpointPosition(node, state.breakpoint, { ...currentPos, x: origX + dx, y: origY + dy });
      await handlers.updatePosition?.(node.key, position);
    });
  });
}

export function renderLayers(state, handlers) {
  const options = typeof handlers === "object" && !handlers.select ? handlers : {};
  const isFreeform = options.freeform || state.mode === "freeform";
  const breakpoint = options.breakpoint || state.breakpoint;
  const children = new Map(); state.nodes.forEach((node) => { const key = node.parent_key || "__root__"; if (!children.has(key)) children.set(key, []); children.get(key).push(node); });
  children.forEach((items) => items.sort((a, b) => a.order - b.order));
  const branch = (parent = "__root__") => (children.get(parent) || []).map((node) => {
    const pos = isFreeform ? getBreakpointPosition(node, breakpoint) : null;
    const zBadge = isFreeform ? `<span class="ub-layer-z" title="z-index: ${pos?.z || 1}">z:${pos?.z || 1}</span>` : "";
    const zControls = isFreeform ? `<span class="ub-layer-z-controls"><button data-z-up="${esc(node.key)}" title="Bring forward">↑</button><button data-z-down="${esc(node.key)}" title="Send backward">↓</button></span>` : "";
    return `<div class="ub-layer"><button class="ub-layer-item ${(state.selectedKeys?.length ? state.selectedKeys.includes(node.key) : state.selectedKey === node.key) ? "is-active" : ""}" data-layer="${esc(node.key)}" data-hidden="${node.visibility === "hidden"}"><span>▦</span><span>${esc(node.metadata?.display_label || state.registry.components[node.component_type]?.label || node.component_type)}</span>${zBadge}<span class="ub-layer-item__actions">${zControls}${node.visibility === "hidden" ? "◌" : "◉"}</span></button>${children.has(node.key) ? `<div class="ub-layer-children">${branch(node.key)}</div>` : ""}</div>`;
  }).join("");
  return branch() || '<div class="ub-empty-panel"><strong>No components yet</strong><p>Add your first section.</p></div>';
}
