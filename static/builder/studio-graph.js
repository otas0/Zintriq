/**
 * Studio Logic / Connection graph canvas (vanilla SVG).
 * Logic: layers → ordered actions (real project data).
 * Connection: project root → capabilities / installed packages.
 */

const NODE_W = 188;
const NODE_H = 64;
const COL_GAP = 56;
const ROW_GAP = 40;

function esc(value = "") {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function layoutGrid(items, columns = 3) {
  return items.map((item, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    return {
      ...item,
      x: 40 + col * (NODE_W + COL_GAP),
      y: 40 + row * (NODE_H + ROW_GAP),
    };
  });
}

function edgePath(a, b) {
  const x1 = a.x + NODE_W / 2;
  const y1 = a.y + NODE_H;
  const x2 = b.x + NODE_W / 2;
  const y2 = b.y;
  const mid = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`;
}

function edgePathHorizontal(a, b) {
  const x1 = a.x + NODE_W;
  const y1 = a.y + NODE_H / 2;
  const x2 = b.x;
  const y2 = b.y + NODE_H / 2;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

/**
 * Build a truthful Logic graph from Interface layers + their actions/conditions.
 */
export function renderLogicGraph(
  container,
  {
    actions = [],
    nodes = [],
    conditions = [],
    actionLabels = {},
    onSelect,
    onEmptyAction,
  } = {},
) {
  const nodeByKey = new Map(nodes.map((n) => [n.key, n]));
  const conditionById = new Map(conditions.map((c) => [c.id, c]));
  const byLayer = new Map();

  for (const action of actions) {
    const key = action.node_key || action.target_node_key;
    if (!key) continue;
    if (!byLayer.has(key)) byLayer.set(key, { actions: [], condition: null });
    byLayer.get(key).actions.push(action);
  }

  for (const layer of nodes) {
    if (!layer.condition_id) continue;
    const cond = conditionById.get(layer.condition_id);
    if (!cond) continue;
    if (!byLayer.has(layer.key)) byLayer.set(layer.key, { actions: [], condition: null });
    byLayer.get(layer.key).condition = cond;
  }

  const layers = [...byLayer.entries()].map(([key, bag]) => {
    const layer = nodeByKey.get(key);
    const title =
      layer?.metadata?.display_label ||
      layer?.component_type ||
      key;
    bag.actions.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    return {
      key,
      title: String(title),
      subtitle: layer?.component_type ? String(layer.component_type) : "layer",
      actions: bag.actions,
      condition: bag.condition,
    };
  });

  if (!layers.length) {
    paint(container, [], [], {
      emptyTitle: "No Logic on this page yet",
      emptyBody:
        "Actions and visibility conditions live on Interface layers. Add an action on a selected layer, or open Interface and use the Actions tab.",
      emptyActionLabel: onEmptyAction ? "Add action on selected layer" : null,
      onEmptyAction,
      onSelect,
    });
    return;
  }

  const graphNodes = [];
  const edges = [];

  layers.forEach((layer, col) => {
    const x = 40 + col * (NODE_W + COL_GAP);
    let row = 0;
    const layerNode = {
      id: `layer-${layer.key}`,
      x,
      y: 40 + row * (NODE_H + ROW_GAP),
      title: layer.title,
      subtitle: layer.subtitle,
      kind: "layer",
      raw: { type: "layer", node_key: layer.key },
    };
    graphNodes.push(layerNode);
    let prev = layerNode;
    row += 1;

    if (layer.condition) {
      const condNode = {
        id: `cond-${layer.condition.id}`,
        x,
        y: 40 + row * (NODE_H + ROW_GAP),
        title: layer.condition.name || "Visibility",
        subtitle: "condition",
        kind: "condition",
        raw: { type: "condition", node_key: layer.key, condition: layer.condition },
      };
      graphNodes.push(condNode);
      edges.push([prev, condNode]);
      prev = condNode;
      row += 1;
    }

    layer.actions.forEach((action) => {
      const label = actionLabels[action.action_type] || action.action_type || "action";
      const actionNode = {
        id: `action-${action.id || action.action_key}`,
        x,
        y: 40 + row * (NODE_H + ROW_GAP),
        title: String(label),
        subtitle: action.event_type || "click",
        kind: "logic",
        raw: { type: "action", node_key: layer.key, action },
      };
      graphNodes.push(actionNode);
      edges.push([prev, actionNode]);
      prev = actionNode;
      row += 1;
    });
  });

  paint(container, graphNodes, edges, {
    emptyTitle: "No Logic graph yet",
    emptyBody: "Actions attached on Interface layers appear here.",
    onSelect,
    verticalEdges: true,
  });
}

export function renderConnectionGraph(container, { capabilities = [], installations = [], onSelect } = {}) {
  const nodes = layoutGrid([
    { id: "project", title: "This project", subtitle: "composition root", kind: "root" },
    ...capabilities.map((cap, i) => ({
      id: `cap-${i}`,
      title: String(cap),
      subtitle: "capability",
      kind: "capability",
      raw: { type: "capability", value: cap },
    })),
    ...installations.map((item, i) => ({
      id: `pkg-${item.package_id || i}`,
      title: item.package?.name || item.package_id || "package",
      subtitle: `v${item.version || "—"}`,
      kind: "package",
      raw: { type: "package", installation: item },
    })),
  ]);
  const root = nodes[0];
  const edges = nodes.slice(1).map((n) => [root, n]);
  paint(container, nodes, edges, {
    emptyTitle: "No Connection graph yet",
    emptyBody: "Installed packages and enabled capabilities attach here. Import adapters from Community on the web.",
    onSelect,
    verticalEdges: false,
  });
}

function paint(container, nodes, edges, { emptyTitle, emptyBody, emptyActionLabel, onEmptyAction, onSelect, verticalEdges = true }) {
  if (!container) return;
  if (!nodes.length) {
    container.innerHTML = `<div class="ub-card ub-empty-panel"><strong>${esc(emptyTitle)}</strong><p>${esc(emptyBody)}</p>${
      emptyActionLabel
        ? `<p style="margin-top:12px"><button type="button" class="ub-btn ub-btn--primary" data-graph-empty-action>${esc(emptyActionLabel)}</button></p>`
        : ""
    }</div>`;
    container.querySelector("[data-graph-empty-action]")?.addEventListener("click", () => onEmptyAction?.());
    return;
  }
  const width = Math.max(720, ...nodes.map((n) => n.x + NODE_W + 40));
  const height = Math.max(320, ...nodes.map((n) => n.y + NODE_H + 40));
  const pathFn = verticalEdges ? edgePath : edgePathHorizontal;
  const edgeSvg = edges
    .map(([a, b]) => `<path class="ub-graph__edge" d="${pathFn(a, b)}" fill="none" />`)
    .join("");
  const nodeSvg = nodes
    .map(
      (n) => `<g class="ub-graph__node ub-graph__node--${esc(n.kind)}" data-node-id="${esc(n.id)}" transform="translate(${n.x},${n.y})">
      <rect width="${NODE_W}" height="${NODE_H}" rx="10" ry="10"></rect>
      <text x="14" y="28" class="ub-graph__title">${esc(n.title)}</text>
      <text x="14" y="48" class="ub-graph__sub">${esc(n.subtitle)}</text>
    </g>`,
    )
    .join("");
  container.innerHTML = `<div class="ub-graph-shell"><svg class="ub-graph" viewBox="0 0 ${width} ${height}" width="100%" height="${Math.min(height, 520)}">${edgeSvg}${nodeSvg}</svg></div>`;
  container.querySelectorAll("[data-node-id]").forEach((el) => {
    el.addEventListener("click", () => {
      const node = nodes.find((n) => n.id === el.dataset.nodeId);
      if (node && onSelect) onSelect(node);
    });
  });
}
