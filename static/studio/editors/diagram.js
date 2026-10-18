(function (root) {
  if (!root.ZintriqEditorViews) return;

  let boxes = [];
  let selectedId = "";
  let visualCopy = null;

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function cloneVisual(visual) {
    return JSON.parse(JSON.stringify(visual || { form: "visual", nodes: [], edges: [], root: "" }));
  }

  function nodeById(visual, id) {
    return ((visual && visual.nodes) || []).find(function (item) {
      return item.id === id;
    });
  }

  function labelOf(node) {
    const props = (node && node.properties) || {};
    if (node.kind === "literal" && props.has_value) return String(props.value);
    if (node.kind === "literal") return props.type || "literal";
    if (node.kind === "record") return (props.fields || []).join(", ") || "record";
    if (node.kind === "array") return "array · " + (props.length || 0);
    if (node.kind === "map") return "map";
    if (node.kind === "reference") return String(props.ref || "ref");
    return node.kind || node.id;
  }

  function layout(visual) {
    const nodes = (visual && visual.nodes) || [];
    const cols = Math.max(1, Math.ceil(Math.sqrt(Math.max(nodes.length, 1))));
    const cellW = 176;
    const cellH = 92;
    boxes = nodes.map(function (node, i) {
      const view = (node.properties && node.properties.view) || {};
      const transform = view.transform || {};
      const x = Number.isFinite(Number(transform.x)) ? Number(transform.x) : 24 + (i % cols) * cellW;
      const y = Number.isFinite(Number(transform.y)) ? Number(transform.y) : 56 + Math.floor(i / cols) * cellH;
      return { id: node.id, node: node, x: x, y: y, w: 156, h: 56, marks: view.marks || [] };
    });
    const maxX = boxes.reduce(function (acc, box) {
      return Math.max(acc, box.x + box.w);
    }, 360);
    const maxY = boxes.reduce(function (acc, box) {
      return Math.max(acc, box.y + box.h);
    }, 220);
    return {
      width: Math.max(360, maxX + 24, cols * cellW + 24),
      height: Math.max(220, maxY + 24, Math.ceil(nodes.length / cols) * cellH + 72),
    };
  }

  function svgPoint(host, event) {
    const svg = host.querySelector("svg");
    if (!svg || !svg.createSVGPoint || !svg.getScreenCTM) {
      const rect = host.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }
    const pt = svg.createSVGPoint();
    pt.x = event.clientX;
    pt.y = event.clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM().inverse());
    return { x: loc.x, y: loc.y };
  }

  function hitAt(host, event) {
    const pt = svgPoint(host, event);
    for (let i = boxes.length - 1; i >= 0; i -= 1) {
      const box = boxes[i];
      if (pt.x >= box.x && pt.x <= box.x + box.w && pt.y >= box.y && pt.y <= box.y + box.h) return box;
    }
    return null;
  }

  function coerce(typeName, raw) {
    const text = String(raw);
    if (typeName === "int") return parseInt(text, 10);
    if (typeName === "float") return parseFloat(text);
    if (typeName === "bool") return text === "true" || text === "1";
    if (typeName === "null") return null;
    return text;
  }

  function commitValue(ctx, nodeId, raw) {
    const visual = cloneVisual(ctx.visual || visualCopy);
    visual.nodes = (visual.nodes || []).map(function (node) {
      if (node.id !== nodeId) return node;
      const props = Object.assign({}, node.properties || {});
      if (node.kind !== "literal") return node;
      props.has_value = true;
      props.value = coerce(props.type, raw);
      return Object.assign({}, node, { properties: props });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(visual);
  }

  root.ZintriqEditorViews.register({
    id: "diagram",
    name: "Diagram",
    surfaces: ["describe"],
    pane: "diagram",
    render: function (host, ctx) {
      visualCopy = ctx.visual || visualCopy;
      const visual = visualCopy;
      const size = layout(visual);
      const selected = selectedId;
      const current = nodeById(visual, selected);
      const editable = current && current.kind === "literal";
      const value = editable && current.properties && current.properties.has_value ? current.properties.value : "";
      const edges = ((visual && visual.edges) || [])
        .map(function (edge) {
          const a = boxes.find(function (box) {
            return box.id === edge.source;
          });
          const b = boxes.find(function (box) {
            return box.id === edge.target;
          });
          if (!a || !b) return "";
          return (
            '<line x1="' +
            (a.x + a.w / 2) +
            '" y1="' +
            (a.y + a.h / 2) +
            '" x2="' +
            (b.x + b.w / 2) +
            '" y2="' +
            (b.y + b.h / 2) +
            '" stroke="currentColor" stroke-width="1" />'
          );
        })
        .join("");
      const nodes = boxes
        .map(function (box) {
          const on = box.id === selected ? " is-current" : "";
          return (
            '<g class="me-diagram-node' +
            on +
            '" data-node-id="' +
            escapeHtml(box.id) +
            '">' +
            '<rect x="' +
            box.x +
            '" y="' +
            box.y +
            '" width="' +
            box.w +
            '" height="' +
            box.h +
            '" fill="none" stroke="currentColor" rx="6" />' +
            '<text x="' +
            (box.x + 8) +
            '" y="' +
            (box.y + 22) +
            '" font-size="11" fill="currentColor">' +
            escapeHtml(box.node.kind + " · " + box.id) +
            "</text>" +
            '<text x="' +
            (box.x + 8) +
            '" y="' +
            (box.y + 42) +
            '" font-size="11" fill="currentColor">' +
            escapeHtml(labelOf(box.node).slice(0, 22)) +
            "</text>" +
            (box.marks && box.marks.length
              ? '<text x="' +
                (box.x + 8) +
                '" y="' +
                (box.y + 52) +
                '" font-size="9" fill="currentColor" opacity="0.7">' +
                escapeHtml(box.marks.join(", ")) +
                "</text>"
              : "") +
            "</g>"
          );
        })
        .join("");
      host.innerHTML =
        '<header class="me-plugin-toolbar"><div class="me-plugin-toolbar-title"><strong>Diagram</strong><span>UIR graph over Desc — still a view plugin.</span></div>' +
        '<div class="me-plugin-toolbar-actions"><span class="me-plugin-status-inline">' +
        boxes.length +
        " nodes</span></div></header>" +
        '<label class="me-diagram-edit">Literal' +
        '<input id="me-diagram-value" type="text" ' +
        (editable ? "" : "disabled ") +
        'value="' +
        escapeHtml(value) +
        '"></label>' +
        '<div class="me-diagram-canvas"><svg viewBox="0 0 ' +
        size.width +
        " " +
        size.height +
        '" width="' +
        size.width +
        '" height="' +
        size.height +
        '">' +
        edges +
        nodes +
        "</svg></div>";
      const input = host.querySelector("#me-diagram-value");
      if (input) {
        input.addEventListener("change", function () {
          if (!selectedId) return;
          commitValue(ctx, selectedId, input.value);
        });
        input.addEventListener("keydown", function (event) {
          if (event.key === "Enter") {
            event.preventDefault();
            input.blur();
          }
        });
      }
    },
    hitTest: function (event, ctx) {
      const host = ctx.host;
      if (!host) return null;
      const hit = hitAt(host, event);
      if (!hit) return null;
      return { id: hit.id, node: hit.node };
    },
    getPropertyPanel: function (ctx) {
      const visual = ctx.visual || visualCopy;
      const id = (root.ZintriqEngine && root.ZintriqEngine.selection.primary()) || selectedId;
      const current = nodeById(visual, id);
      if (!current) return "<p class='me-props-empty'>Select a node</p>";
      const editable = current.kind === "literal";
      const value = editable && current.properties && current.properties.has_value ? current.properties.value : "";
      return (
        "<p>" +
        escapeHtml(current.kind + " · " + current.id) +
        "</p><input id='me-diagram-value' type='text' " +
        (editable ? "" : "disabled ") +
        'value="' +
        escapeHtml(value) +
        '">'
      );
    },
    edit: function (op, ctx) {
      if (!op || !op.id) return;
      if (root.ZintriqEngine) root.ZintriqEngine.selection.set([op.id]);
      selectedId = op.id;
      if (op.type === "open") {
        const input = ctx.host && ctx.host.querySelector("#me-diagram-value");
        if (input && !input.disabled) {
          input.focus();
          input.select();
        }
      }
    },
  });
})(window);
