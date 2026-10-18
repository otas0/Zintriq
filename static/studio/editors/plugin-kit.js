(function (root) {
  function escapeHtml(value) {
    return String(value == null ? "" : value)
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

  function childrenOf(visual, id) {
    return ((visual && visual.edges) || [])
      .filter(function (edge) {
        return edge.source === id;
      })
      .map(function (edge) {
        return { label: edge.label || "", node: nodeById(visual, edge.target) };
      })
      .filter(function (item) {
        return item.node;
      });
  }

  function coerce(typeName, raw) {
    const text = String(raw);
    if (typeName === "int") {
      const n = parseInt(text, 10);
      return Number.isFinite(n) ? n : 0;
    }
    if (typeName === "float") {
      const n = parseFloat(text);
      return Number.isFinite(n) ? n : 0;
    }
    if (typeName === "bool") return text === "true" || text === "1";
    if (typeName === "null") return null;
    return text;
  }

  function unusedId(visual, prefix) {
    const used = {};
    ((visual && visual.nodes) || []).forEach(function (node) {
      used[node.id] = true;
    });
    ((visual && visual.edges) || []).forEach(function (edge) {
      used[edge.id] = true;
    });
    let n = 1;
    while (used[prefix + n]) n += 1;
    return prefix + n;
  }

  function walk(visual, startId, dotted) {
    if (!dotted) return nodeById(visual, startId);
    const parts = String(dotted).split(".");
    let id = startId;
    for (let i = 0; i < parts.length; i += 1) {
      const child = childrenOf(visual, id).find(function (item) {
        return item.label === parts[i];
      });
      if (!child) return null;
      id = child.node.id;
    }
    return nodeById(visual, id);
  }

  function domainRoot(visual, spec) {
    const wanted = spec && spec.kindValue;
    const edges = (visual && visual.edges) || [];
    const nodes = (visual && visual.nodes) || [];
    if (wanted) {
      for (let i = 0; i < nodes.length; i += 1) {
        const node = nodes[i];
        if (node.kind !== "literal") continue;
        if ((node.properties || {}).value !== wanted) continue;
        const edge = edges.find(function (item) {
          return item.target === node.id && item.label === "kind";
        });
        if (edge) return nodeById(visual, edge.source);
      }
    }
    return nodeById(visual, visual && visual.root);
  }

  function commitLiteral(ctx, visual, nodeId, typeName, raw) {
    const next = cloneVisual(visual);
    next.nodes = (next.nodes || []).map(function (node) {
      if (node.id !== nodeId || node.kind !== "literal") return node;
      const stored = typeName === "area" ? (node.properties || {}).type || "string" : typeName || (node.properties || {}).type || "string";
      const props = Object.assign({}, node.properties || {}, {
        has_value: true,
        type: stored,
        value: coerce(stored, raw),
      });
      return Object.assign({}, node, { properties: props });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
  }

  function commitView(ctx, visual, nodeId, viewPatch) {
    const next = cloneVisual(visual);
    next.nodes = (next.nodes || []).map(function (node) {
      if (node.id !== nodeId) return node;
      const props = Object.assign({}, node.properties || {});
      const view = Object.assign({}, props.view || {}, viewPatch || {});
      if (view.marks && typeof view.marks === "string") {
        view.marks = view.marks
          .split(",")
          .map(function (item) {
            return item.trim();
          })
          .filter(Boolean);
      }
      props.view = view;
      return Object.assign({}, node, { properties: props });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
  }

  function labelOf(node) {
    const props = (node && node.properties) || {};
    if (node.kind === "literal" && props.has_value) return String(props.value);
    if (node.kind === "literal") return props.type || "literal";
    if (node.kind === "record") return (props.fields || []).join(", ") || "record";
    if (node.kind === "array") return "array · " + (props.length || 0);
    if (node.kind === "map") return "map";
    return (node && node.kind) || "";
  }

  function inputFor(typeName, value, attrs, options) {
    const v = value == null ? "" : value;
    if (options && options.length) {
      return (
        "<select " +
        attrs +
        ">" +
        options
          .map(function (opt) {
            const val = typeof opt === "object" ? opt.value : opt;
            const label = typeof opt === "object" ? opt.label || opt.value : opt;
            return (
              '<option value="' +
              escapeHtml(val) +
              '"' +
              (String(v) === String(val) ? " selected" : "") +
              ">" +
              escapeHtml(label) +
              "</option>"
            );
          })
          .join("") +
        "</select>"
      );
    }
    if (typeName === "bool") {
      const on = v === true || v === "true" || v === "1" || v === 1;
      return '<input type="checkbox" ' + attrs + (on ? " checked" : "") + ">";
    }
    if (typeName === "range") {
      const min = options && options.min != null ? options.min : 0;
      const max = options && options.max != null ? options.max : 1;
      const step = options && options.step != null ? options.step : 0.01;
      return (
        '<span class="me-plugin-range"><input type="range" min="' +
        min +
        '" max="' +
        max +
        '" step="' +
        step +
        '" ' +
        attrs +
        ' value="' +
        escapeHtml(v) +
        '"><input type="number" step="' +
        step +
        '" ' +
        attrs +
        ' value="' +
        escapeHtml(v) +
        '"></span>'
      );
    }
    if (typeName === "int" || typeName === "float") {
      return '<input type="number" step="' + (typeName === "int" ? "1" : "any") + '" ' + attrs + ' value="' + escapeHtml(v) + '">';
    }
    if (typeName === "area") {
      return "<textarea " + attrs + ">" + escapeHtml(v) + "</textarea>";
    }
    if (typeName === "color") {
      return '<input type="color" ' + attrs + ' value="' + escapeHtml(String(v || "#888888").slice(0, 7)) + '">';
    }
    return '<input type="text" ' + attrs + ' value="' + escapeHtml(v) + '">';
  }

  function drawSheet(visual, root, sheet) {
    if (!root) return "";
    const groups = {};
    const order = [];
    (sheet || []).forEach(function (field) {
      const group = field.group || "Fields";
      if (!groups[group]) {
        groups[group] = [];
        order.push(group);
      }
      groups[group].push(field);
    });
    return order
      .map(function (group) {
        return (
          '<section class="me-plugin-section"><h3 class="me-plugin-section-title">' +
          escapeHtml(group) +
          "</h3><div class=\"me-plugin-fields\">" +
          groups[group]
            .map(function (field) {
              const node = walk(visual, root.id, field.key);
              const typeName = field.type || (node && node.properties && node.properties.type) || "string";
              const value = node && node.properties && node.properties.has_value ? node.properties.value : "";
              const attrs = node ? 'data-field-id="' + escapeHtml(node.id) + '" data-field-type="' + escapeHtml(typeName) + '"' : "disabled";
              const widget = field.widget || typeName;
              const extra = widget === "range" ? { min: field.min, max: field.max, step: field.step } : field.options;
              return (
                "<label><span class=\"me-plugin-field-label\">" +
                escapeHtml(field.label || field.key) +
                "</span>" +
                inputFor(widget, value, attrs, extra) +
                "</label>"
              );
            })
            .join("") +
          "</div></section>"
        );
      })
      .join("");
  }

  const easeChoices = [
    { value: "linear", label: "linear" },
    { value: "ease-in", label: "ease-in" },
    { value: "ease-out", label: "ease-out" },
    { value: "ease-in-out", label: "ease-in-out" },
    { value: "cubic", label: "cubic" },
  ];

  function drawTable(visual, arrayNode, fieldOptions, tableKey, selectedId) {
    const wrapOpen = '<div class="me-plugin-table-wrap" data-table-key="' + escapeHtml(tableKey || "") + '">';
    if (!arrayNode) return wrapOpen + "<p class=\"me-plugin-empty\">No rows yet.</p></div>";
    const rows = childrenOf(visual, arrayNode.id);
    if (!rows.length) return wrapOpen + '<p class="me-plugin-empty">Empty table. Use Insert row.</p></div>';
    const headers = [];
    childrenOf(visual, rows[0].node.id).forEach(function (cell) {
      if (headers.indexOf(cell.label) < 0) headers.push(cell.label);
    });
    const optionsFor = fieldOptions || {};
    return (
      wrapOpen +
      '<table class="me-plugin-table"><thead><tr>' +
      headers
        .map(function (name) {
          return "<th>" + escapeHtml(name) + "</th>";
        })
        .join("") +
      '<th class="me-plugin-table-actions"></th></tr></thead><tbody>' +
      rows
        .map(function (row) {
          const cells = childrenOf(visual, row.node.id);
          return (
            '<tr data-row-id="' +
            escapeHtml(row.node.id) +
            '"' +
            (selectedId && selectedId === row.node.id ? ' class="is-selected"' : "") +
            ">" +
            headers
              .map(function (name) {
                const cell = cells.find(function (item) {
                  return item.label === name;
                });
                const node = cell && cell.node;
                const typeName = (node && node.properties && node.properties.type) || "string";
                const value = node && node.properties && node.properties.has_value ? node.properties.value : "";
                const attrs = node
                  ? 'data-field-id="' + escapeHtml(node.id) + '" data-field-type="' + escapeHtml(typeName) + '"'
                  : "disabled";
                const choices = optionsFor[name] || (name === "easing" ? easeChoices : null);
                return "<td>" + inputFor(typeName, value, attrs, choices) + "</td>";
              })
              .join("") +
            '<td><button type="button" class="me-btn me-btn--ghost" data-plugin-del-row="' +
            escapeHtml(row.node.id) +
            '">Delete</button></td></tr>'
          );
        })
        .join("") +
      "</tbody></table></div>"
    );
  }

  function drawKeepoutCounts(visual, domain) {
    const arr = walk(visual, domain.id, "keepout");
    if (!arr) return "";
    const by = {};
    childrenOf(visual, arr.id).forEach(function (row) {
      let layer = 0;
      let holes = 0;
      childrenOf(visual, row.node.id).forEach(function (cell) {
        if (cell.label === "layer") layer = Number((cell.node.properties || {}).value) || 0;
        if (cell.label === "holes") holes = childrenOf(visual, cell.node.id).length;
      });
      by[layer] = by[layer] || { polys: 0, holes: 0 };
      by[layer].polys += 1;
      by[layer].holes += holes;
    });
    const parts = Object.keys(by)
      .sort()
      .map(function (key) {
        return "L" + key + " polys " + by[key].polys + " holes " + by[key].holes;
      });
    return '<p class="me-plugin-hint" data-keepout-counts>' + escapeHtml(parts.join(" · ") || "L0 polys 0 holes 0") + "</p>";
  }

  function drawEaseHandles() {
    return (
      '<div class="me-ease-handles-wrap">' +
      '<p class="me-plugin-field-label">Cubic handles</p>' +
      '<canvas class="me-ease-handles" width="200" height="120" data-ease-handles></canvas>' +
      "</div>"
    );
  }

  function bindEaseHandles(host, spec, ctx, visual, rootNode) {
    const canvas = host.querySelector("[data-ease-handles]");
    if (!canvas || !spec.dopesheet || !rootNode) return;
    const arrayNode = walk(visual, rootNode.id, spec.dopesheet.table);
    if (!arrayNode) return;
    const g = canvas.getContext("2d");
    if (!g) return;
    let target = null;
    const selectedId = host.getAttribute("data-ease-row") || "";
    const rows = childrenOf(visual, arrayNode.id);
    rows.forEach(function (row) {
      const fields = {};
      childrenOf(visual, row.node.id).forEach(function (cell) {
        fields[cell.label] = cell.node;
      });
      fields._rowId = row.node.id;
      if (fields.c1x && fields.c1y && fields.c2x && fields.c2y) {
        if (selectedId && row.node.id === selectedId) target = fields;
        else if (!selectedId && !target) target = fields;
      }
    });
    if (!target && rows.length) {
      const fields = {};
      childrenOf(visual, rows[0].node.id).forEach(function (cell) {
        fields[cell.label] = cell.node;
      });
      if (fields.c1x) target = fields;
    }
    if (!target) return;
    if (target._rowId) host.setAttribute("data-ease-row", target._rowId);
    const table = host.querySelector('[data-table-key="' + (spec.dopesheet.table || "keyframes") + '"]');
    function markRows() {
      if (!table) return;
      table.querySelectorAll("tr[data-row-id]").forEach(function (tr) {
        tr.classList.toggle("is-selected", tr.getAttribute("data-row-id") === host.getAttribute("data-ease-row"));
      });
    }
    markRows();
    const pad = 20;
    const box = 80;
    function read() {
      function num(node, fallback) {
        const n = Number(node && node.properties ? node.properties.value : fallback);
        return Number.isFinite(n) ? n : fallback;
      }
      return {
        c1x: num(target.c1x, 0.25),
        c1y: num(target.c1y, 0.1),
        c2x: num(target.c2x, 0.25),
        c2y: num(target.c2y, 1),
      };
    }
    function toPx(x, y) {
      return [pad + x * box, pad + box - y * box];
    }
    function fromPx(px, py) {
      return {
        x: Math.max(0, Math.min(1, (px - pad) / box)),
        y: Math.max(0, Math.min(1, (pad + box - py) / box)),
      };
    }
    function paint(ctrl) {
      g.clearRect(0, 0, 200, 120);
      g.fillStyle = "#f7f7f4";
      g.fillRect(0, 0, 200, 120);
      g.strokeStyle = "#ccc";
      g.strokeRect(pad, pad, box, box);
      const a = toPx(0, 0);
      const b = toPx(ctrl.c1x, ctrl.c1y);
      const c = toPx(ctrl.c2x, ctrl.c2y);
      const d = toPx(1, 1);
      g.strokeStyle = "#888";
      g.beginPath();
      g.moveTo(a[0], a[1]);
      g.lineTo(b[0], b[1]);
      g.moveTo(d[0], d[1]);
      g.lineTo(c[0], c[1]);
      g.stroke();
      g.strokeStyle = "#36a";
      g.beginPath();
      g.moveTo(a[0], a[1]);
      g.bezierCurveTo(b[0], b[1], c[0], c[1], d[0], d[1]);
      g.stroke();
      g.fillStyle = "#c33";
      g.beginPath();
      g.arc(b[0], b[1], 5, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = "#3a6";
      g.beginPath();
      g.arc(c[0], c[1], 5, 0, Math.PI * 2);
      g.fill();
    }
    let ctrl = read();
    paint(ctrl);
    let drag = null;
    canvas.addEventListener("pointerdown", function (ev) {
      const runtime = host.querySelector("[data-runtime]");
      if (runtime && runtime.getAttribute("data-playing") === "1") return;
      const rect = canvas.getBoundingClientRect();
      const x = ((ev.clientX - rect.left) / rect.width) * 200;
      const y = ((ev.clientY - rect.top) / rect.height) * 120;
      const p1 = toPx(ctrl.c1x, ctrl.c1y);
      const p2 = toPx(ctrl.c2x, ctrl.c2y);
      if (Math.hypot(x - p1[0], y - p1[1]) <= 10) drag = "c1";
      else if (Math.hypot(x - p2[0], y - p2[1]) <= 10) drag = "c2";
      if (drag) canvas.setPointerCapture(ev.pointerId);
    });
    canvas.addEventListener("pointermove", function (ev) {
      if (!drag) return;
      const runtime = host.querySelector("[data-runtime]");
      if (runtime && runtime.getAttribute("data-playing") === "1") return;
      const rect = canvas.getBoundingClientRect();
      const pt = fromPx(((ev.clientX - rect.left) / rect.width) * 200, ((ev.clientY - rect.top) / rect.height) * 120);
      if (drag === "c1") {
        ctrl.c1x = pt.x;
        ctrl.c1y = pt.y;
      } else {
        ctrl.c2x = pt.x;
        ctrl.c2y = pt.y;
      }
      paint(ctrl);
    });
    canvas.addEventListener("pointerup", function () {
      if (!drag) return;
      const runtime = host.querySelector("[data-runtime]");
      if (!(runtime && runtime.getAttribute("data-playing") === "1")) {
        const next = cloneVisual(visual);
        const ids = {};
        ids[target.c1x.id] = ctrl.c1x;
        ids[target.c1y.id] = ctrl.c1y;
        ids[target.c2x.id] = ctrl.c2x;
        ids[target.c2y.id] = ctrl.c2y;
        next.nodes = (next.nodes || []).map(function (node) {
          if (!ids.hasOwnProperty(node.id) || node.kind !== "literal") return node;
          return Object.assign({}, node, {
            properties: Object.assign({}, node.properties || {}, { has_value: true, type: "float", value: coerce("float", ids[node.id]) }),
          });
        });
        if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
      }
      drag = null;
    });
    if (table && table.getAttribute("data-ease-rows") !== "1") {
      table.setAttribute("data-ease-rows", "1");
      table.addEventListener("click", function (ev) {
        if (ev.target && ev.target.closest && ev.target.closest("button")) return;
        const tr = ev.target.closest ? ev.target.closest("tr[data-row-id]") : null;
        if (!tr) return;
        host.setAttribute("data-ease-row", tr.getAttribute("data-row-id") || "");
        const sid = host.getAttribute("data-ease-row") || "";
        target = null;
        rows.forEach(function (row) {
          if (row.node.id !== sid) return;
          const fields = {};
          childrenOf(visual, row.node.id).forEach(function (cell) {
            fields[cell.label] = cell.node;
          });
          fields._rowId = row.node.id;
          if (fields.c1x) target = fields;
        });
        markRows();
        if (!target) return;
        ctrl = read();
        paint(ctrl);
      });
    }
  }

  function drawTextList(visual, node) {
    if (!node) return "";
    if (node.kind === "literal") {
      const value = node.properties && node.properties.has_value ? node.properties.value : "";
      return (
        '<label class="me-plugin-text-one"><span class="me-plugin-field-label">Source</span><textarea data-field-id="' +
        escapeHtml(node.id) +
        '" data-field-type="area">' +
        escapeHtml(value) +
        "</textarea></label>"
      );
    }
    const items = childrenOf(visual, node.id);
    return (
      '<div class="me-plugin-text">' +
      items
        .map(function (item, index) {
          const value = item.node.properties && item.node.properties.has_value ? item.node.properties.value : labelOf(item.node);
          return (
            "<label><span class=\"me-plugin-field-label\">" +
            escapeHtml(item.label || String(index)) +
            '</span><textarea data-field-id="' +
            escapeHtml(item.node.id) +
            '" data-field-type="area">' +
            escapeHtml(value) +
            "</textarea></label>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function drawOutline(visual, root) {
    if (!root) return "";
    const rows = childrenOf(visual, root.id);
    function rowHtml(item, depth) {
      const kids = item.node.kind === "record" || item.node.kind === "array" ? childrenOf(visual, item.node.id) : [];
      return (
        "<li>" +
        '<button type="button" class="me-plugin-outline-item" data-outline-label="' +
        escapeHtml((item.label || "").toLowerCase()) +
        '" data-node-id="' +
        escapeHtml(item.node.id) +
        '" style="padding-left:' +
        (8 + depth * 12) +
        'px">' +
        escapeHtml(item.label || item.node.id) +
        " · " +
        escapeHtml(labelOf(item.node).slice(0, 28)) +
        "</button>" +
        (kids.length && depth < 2
          ? "<ul>" +
            kids
              .map(function (child) {
                return rowHtml(child, depth + 1);
              })
              .join("") +
            "</ul>"
          : "") +
        "</li>"
      );
    }
    return (
      '<nav class="me-plugin-outline" aria-label="Hierarchy">' +
      '<input type="search" class="me-plugin-outline-filter" placeholder="Filter hierarchy" data-outline-filter>' +
      "<ul>" +
      rows
        .map(function (item) {
          return rowHtml(item, 0);
        })
        .join("") +
      "</ul></nav>"
    );
  }

  function drawTimeline(visual, root, spec) {
    if (!spec.timeline || !root) return "";
    const duration = Number((walk(visual, root.id, spec.timeline.durationKey || "duration") || {}).properties && walk(visual, root.id, spec.timeline.durationKey || "duration").properties.value) || 1;
    const fpsNode = walk(visual, root.id, spec.timeline.fpsKey || "fps");
    const fps = Number(fpsNode && fpsNode.properties && fpsNode.properties.value) || 24;
    const table = spec.timeline.table || spec.table;
    const rows = table ? childrenOf(visual, (walk(visual, root.id, table) || {}).id || "") : [];
    const markers = rows
      .map(function (row) {
        const tNode = childrenOf(visual, row.node.id).find(function (cell) {
          return cell.label === "time" || cell.label === "t" || cell.label === "in";
        });
        const t = Number(tNode && tNode.node.properties && tNode.node.properties.value) || 0;
        const pct = Math.max(0, Math.min(100, (t / Math.max(0.001, duration)) * 100));
        return '<button type="button" class="me-timeline-mark" data-node-id="' + escapeHtml(row.node.id) + '" style="left:' + pct + '%" title="' + escapeHtml(String(t)) + 's"></button>';
      })
      .join("");
    return (
      '<section class="me-timeline" data-timeline="1"><div class="me-timeline-meta">' +
      duration.toFixed(2) +
      "s · " +
      fps +
      " fps · " +
      rows.length +
      ' keys</div><div class="me-timeline-track">' +
      '<span class="me-timeline-playhead" style="left:0"></span>' +
      markers +
      "</div></section>"
    );
  }

  function wrapViewport(inner, spec) {
    if (!spec.viewport) return inner;
    return (
      '<div class="me-viewport" data-viewport="1">' +
      '<div class="me-viewport-chrome"><span>Scene</span><label><input type="checkbox" data-viewport-grid checked> Grid</label><label><input type="checkbox" data-viewport-gizmo checked> Gizmo</label></div>' +
      '<div class="me-viewport-stage">' +
      inner +
      "</div></div>"
    );
  }

  function drawGraph(visual, root) {
    const nodes = [root].concat(
      childrenOf(visual, root && root.id).map(function (item) {
        return item.node;
      })
    );
    const boxes = nodes.filter(Boolean).map(function (node, i) {
      const view = (node.properties && node.properties.view) || {};
      const transform = view.transform || {};
      return {
        id: node.id,
        node: node,
        x: Number(transform.x) || 24 + (i % 3) * 176,
        y: Number(transform.y) || 24 + Math.floor(i / 3) * 92,
        w: 156,
        h: 56,
      };
    });
    const width = Math.max(360, 200 + boxes.length * 40);
    const height = Math.max(200, 80 + Math.ceil(boxes.length / 3) * 92);
    const lines = ((visual && visual.edges) || [])
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
          '" stroke="currentColor" />'
        );
      })
      .join("");
    const shapes = boxes
      .map(function (box) {
        const marks = (((box.node.properties || {}).view || {}).marks || []).join(" ");
        return (
          '<g class="me-diagram-node" data-node-id="' +
          escapeHtml(box.id) +
          '"><rect x="' +
          box.x +
          '" y="' +
          box.y +
          '" width="' +
          box.w +
          '" height="' +
          box.h +
          '" fill="none" stroke="currentColor" rx="6" /><text x="' +
          (box.x + 8) +
          '" y="' +
          (box.y + 32) +
          '" font-size="11" fill="currentColor">' +
          escapeHtml(labelOf(box.node).slice(0, 22)) +
          "</text>" +
          (marks
            ? '<text x="' +
              (box.x + 8) +
              '" y="' +
              (box.y + 48) +
              '" font-size="9" fill="currentColor" opacity="0.7">' +
              escapeHtml(marks) +
              "</text>"
            : "") +
          "</g>"
        );
      })
      .join("");
    return {
      html:
        '<div class="me-diagram-canvas"><svg viewBox="0 0 ' +
        width +
        " " +
        height +
        '" width="' +
        width +
        '" height="' +
        height +
        '">' +
        lines +
        shapes +
        "</svg></div>",
      boxes: boxes,
    };
  }

  function toolbarHtml(spec, ready) {
    const tools = (spec.tools || []).slice();
    if (ready && spec.dopesheet) {
      tools.push({ id: "insert-key", label: "Insert key" });
      tools.push({ id: "copy-ease", label: "Copy cubic" });
      tools.push({ id: "paste-ease", label: "Paste cubic" });
    }
    if (ready && spec.tables && spec.tables.some(function (row) { return row.key === "vias"; })) {
      tools.push({ id: "insert-via", label: "Insert via" });
    }
    if (ready && spec.tables && spec.tables.some(function (row) { return row.key === "keepout"; })) {
      tools.push({ id: "insert-keepout", label: "Insert keepout" });
    }
    if (ready && spec.table) tools.push({ id: "insert-row", label: "Insert row" });
    if (ready && spec.table) tools.push({ id: "duplicate-row", label: "Duplicate row" });
    if (ready && spec.text) tools.push({ id: "insert-line", label: "Insert line" });
    if (ready && spec.viewport) {
      tools.push({ id: "move", label: "Move" });
      tools.push({ id: "rotate", label: "Rotate" });
      tools.push({ id: "scale", label: "Scale" });
      tools.push({ id: "paint", label: "Paint" });
    }
    if (ready && spec.timeline) tools.push({ id: "razor", label: "Razor" });
    if (ready && spec.layout === "graph") tools.push({ id: "route", label: "Route" });
    if (ready && (spec.runtime || spec.timeline)) {
      tools.push({ id: "play", label: "Play" });
      tools.push({ id: "pause", label: "Pause" });
      tools.push({ id: "frame", label: "Frame" });
    }
    if (ready) tools.push({ id: "focus-runtime", label: "Preview" });
    const toolButtons = tools
      .map(function (tool) {
        return (
          '<button type="button" class="me-btn me-btn--ghost" data-plugin-tool="' +
          escapeHtml(tool.id) +
          '">' +
          escapeHtml(tool.label || tool.id) +
          "</button>"
        );
      })
      .join("");
    return (
      '<header class="me-plugin-toolbar">' +
      '<div class="me-plugin-toolbar-title"><strong>' +
      escapeHtml(spec.name) +
      "</strong><span>" +
      escapeHtml(spec.hint || "") +
      "</span></div>" +
      '<div class="me-plugin-toolbar-actions">' +
      '<button type="button" class="me-btn" data-plugin-merge>Add to description</button>' +
      '<button type="button" class="me-btn" data-plugin-replace>Replace document</button>' +
      toolButtons +
      "</div></header>"
    );
  }

  function statusHtml(spec, ready, visual, root) {
    const selected = root && window.ZintriqEngine ? window.ZintriqEngine.selection.primary() : "";
    const fields = root ? childrenOf(visual, root.id).length : 0;
    return (
      '<footer class="me-plugin-status">' +
      "<span>kind " +
      escapeHtml(spec.kindValue || "") +
      "</span><span>" +
      (ready ? "live" : "empty") +
      "</span><span>" +
      fields +
      " fields</span><span>sel " +
      escapeHtml(selected || "—") +
      "</span><span>" +
      escapeHtml(spec.industry || spec.hint || "") +
      "</span></footer>"
    );
  }

  function insertArrayRow(ctx, visual, arrayNode, templateFields) {
    if (!arrayNode) return;
    const next = cloneVisual(visual);
    const rowId = unusedId(next, "n");
    const fields = templateFields && templateFields.length ? templateFields : ["name", "value"];
    const fieldNames = [];
    const newNodes = [{ id: rowId, kind: "record", properties: { fields: fields.slice() } }];
    const newEdges = [];
    fields.forEach(function (name, index) {
      const litId = unusedId(next, "n") + "x" + index;
      fieldNames.push(name);
      const typeName =
        name === "easing"
          ? "string"
          : /layer|track/.test(name)
            ? "int"
            : /^(t|time|px|py|pz|x|y|in|out|duration|value|c1|c2|c1x|c1y|c2x|c2y|x0|y0|x1|y1|x2|y2|x3|y3)$/.test(name)
              ? "float"
              : "string";
      const seed =
        name === "easing"
          ? "linear"
          : name === "c1x" || name === "c2x" || name === "c1"
            ? 0.25
            : name === "c1y"
              ? 0.1
              : name === "c2y"
                ? 1
                : name === "c2"
                  ? 0.75
              : typeName === "float" || typeName === "int"
                ? 0
                : name === "value"
                  ? "0"
                  : name;
      newNodes.push({
        id: litId,
        kind: "literal",
        properties: { type: typeName, has_value: true, value: seed },
      });
      newEdges.push({ id: unusedId(next, "e") + "r" + index, source: rowId, target: litId, label: name });
    });
    newNodes[0].properties.fields = fieldNames;
    next.nodes = (next.nodes || []).concat(newNodes);
    const edgeId = unusedId(next, "e");
    const length = childrenOf(next, arrayNode.id).length;
    next.edges = (next.edges || []).concat([{ id: edgeId, source: arrayNode.id, target: rowId, label: String(length) }].concat(newEdges));
    next.nodes = next.nodes.map(function (node) {
      if (node.id !== arrayNode.id) return node;
      return Object.assign({}, node, { properties: Object.assign({}, node.properties || {}, { length: length + 1 }) });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
  }

  function deleteArrayRow(ctx, visual, arrayNode, rowId) {
    if (!arrayNode || !rowId) return;
    const next = cloneVisual(visual);
    const remove = {};
    remove[rowId] = true;
    childrenOf(next, rowId).forEach(function (item) {
      remove[item.node.id] = true;
    });
    next.edges = (next.edges || []).filter(function (edge) {
      return !remove[edge.source] && !remove[edge.target] && !(edge.source === arrayNode.id && edge.target === rowId);
    });
    next.nodes = (next.nodes || []).filter(function (node) {
      return !remove[node.id];
    });
    const remaining = childrenOf(next, arrayNode.id);
    remaining.forEach(function (item, index) {
      next.edges = next.edges.map(function (edge) {
        if (edge.source === arrayNode.id && edge.target === item.node.id) {
          return Object.assign({}, edge, { label: String(index) });
        }
        return edge;
      });
    });
    next.nodes = next.nodes.map(function (node) {
      if (node.id !== arrayNode.id) return node;
      return Object.assign({}, node, { properties: Object.assign({}, node.properties || {}, { length: remaining.length }) });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
  }

  function duplicateArrayRow(ctx, visual, arrayNode) {
    if (!arrayNode) return;
    const rows = childrenOf(visual, arrayNode.id);
    if (!rows.length) {
      insertArrayRow(ctx, visual, arrayNode, null);
      return;
    }
    const last = rows[rows.length - 1].node;
    const cells = childrenOf(visual, last.id);
    const next = cloneVisual(visual);
    const rowId = unusedId(next, "n");
    const fieldNames = [];
    const newNodes = [{ id: rowId, kind: "record", properties: { fields: [] } }];
    const newEdges = [];
    cells.forEach(function (cell, index) {
      const name = cell.label || String(index);
      fieldNames.push(name);
      const litId = unusedId(next, "n") + "d" + index;
      const props = Object.assign({}, cell.node.properties || {});
      newNodes.push({ id: litId, kind: cell.node.kind || "literal", properties: props });
      newEdges.push({ id: unusedId(next, "e") + "d" + index, source: rowId, target: litId, label: name });
    });
    newNodes[0].properties.fields = fieldNames;
    next.nodes = (next.nodes || []).concat(newNodes);
    const length = rows.length;
    next.edges = (next.edges || []).concat([{ id: unusedId(next, "e"), source: arrayNode.id, target: rowId, label: String(length) }].concat(newEdges));
    next.nodes = next.nodes.map(function (node) {
      if (node.id !== arrayNode.id) return node;
      return Object.assign({}, node, { properties: Object.assign({}, node.properties || {}, { length: length + 1 }) });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
  }

  function insertTextLine(ctx, visual, textNode) {
    if (!textNode) return;
    if (textNode.kind === "literal") return;
    const next = cloneVisual(visual);
    const litId = unusedId(next, "n");
    const length = childrenOf(next, textNode.id).length;
    next.nodes = (next.nodes || []).concat([
      { id: litId, kind: "literal", properties: { type: "string", has_value: true, value: "" } },
    ]);
    next.edges = (next.edges || []).concat([{ id: unusedId(next, "e"), source: textNode.id, target: litId, label: String(length) }]);
    next.nodes = next.nodes.map(function (node) {
      if (node.id !== textNode.id) return node;
      return Object.assign({}, node, { properties: Object.assign({}, node.properties || {}, { length: length + 1 }) });
    });
    if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
  }

  function bindFields(host, spec, ctx, visual, rootNode) {
    function onField(el) {
      const id = el.getAttribute("data-field-id");
      if (!id) return;
      const raw = el.type === "checkbox" ? (el.checked ? "true" : "false") : el.value;
      commitLiteral(ctx, visual, id, el.getAttribute("data-field-type"), raw);
    }
    host.querySelectorAll("[data-field-id]").forEach(function (el) {
      el.addEventListener("change", function () {
        onField(el);
      });
      if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
        el.addEventListener("blur", function () {
          onField(el);
        });
      }
    });
    host.querySelectorAll("[data-view-field]").forEach(function (el) {
      el.addEventListener("change", function () {
        const id = el.getAttribute("data-view-node");
        if (!id) return;
        const patch = {};
        patch[el.getAttribute("data-view-field")] = el.value;
        if (el.getAttribute("data-view-field") === "tx" || el.getAttribute("data-view-field") === "ty") {
          commitView(ctx, visual, id, {
            transform: {
              x: Number(host.querySelector('[data-view-node="' + id + '"][data-view-field="tx"]').value) || 0,
              y: Number(host.querySelector('[data-view-node="' + id + '"][data-view-field="ty"]').value) || 0,
            },
          });
          return;
        }
        commitView(ctx, visual, id, patch);
      });
    });
    const mergeBtn = host.querySelector("[data-plugin-merge]");
    if (mergeBtn) {
      mergeBtn.addEventListener("click", function () {
        if (typeof ctx.applyCode === "function") ctx.applyCode(spec.seed, { merge: true, field: spec.id });
      });
    }
    const replaceBtn = host.querySelector("[data-plugin-replace]");
    if (replaceBtn) {
      replaceBtn.addEventListener("click", function () {
        if (typeof ctx.applyCode === "function") ctx.applyCode(spec.seed);
      });
    }
    host.querySelectorAll("[data-plugin-tool]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const tool = btn.getAttribute("data-plugin-tool");
        if (tool === "insert-row" && rootNode && spec.table) {
          insertArrayRow(ctx, visual, walk(visual, rootNode.id, spec.table), spec.rowFields);
        } else if (tool === "insert-key" && rootNode && spec.dopesheet) {
          insertArrayRow(ctx, visual, walk(visual, rootNode.id, spec.dopesheet.table), spec.dopesheet.rowFields);
        } else if ((tool === "copy-ease" || tool === "paste-ease") && rootNode && spec.dopesheet) {
          const runtime = host.querySelector("[data-runtime]");
          if (runtime && runtime.getAttribute("data-playing") === "1") return;
          const sid = host.getAttribute("data-ease-row") || "";
          if (!sid) return;
          const fields = {};
          childrenOf(visual, sid).forEach(function (cell) {
            fields[cell.label] = cell.node;
          });
          function cubicNum(node, fallback) {
            const n = Number(node && node.properties ? node.properties.value : fallback);
            return Number.isFinite(n) ? n : fallback;
          }
          if (tool === "copy-ease" && fields.c1x && fields.c1y && fields.c2x && fields.c2y) {
            host._easeCopy = {
              c1x: cubicNum(fields.c1x, 0.25),
              c1y: cubicNum(fields.c1y, 0.1),
              c2x: cubicNum(fields.c2x, 0.25),
              c2y: cubicNum(fields.c2y, 1),
            };
            return;
          }
          if (tool === "paste-ease" && host._easeCopy && fields.c1x && fields.c1y && fields.c2x && fields.c2y) {
            const copy = host._easeCopy;
            const next = cloneVisual(visual);
            const ids = {};
            ids[fields.c1x.id] = copy.c1x;
            ids[fields.c1y.id] = copy.c1y;
            ids[fields.c2x.id] = copy.c2x;
            ids[fields.c2y.id] = copy.c2y;
            next.nodes = (next.nodes || []).map(function (node) {
              if (!ids.hasOwnProperty(node.id) || node.kind !== "literal") return node;
              return Object.assign({}, node, {
                properties: Object.assign({}, node.properties || {}, { has_value: true, type: "float", value: coerce("float", ids[node.id]) }),
              });
            });
            if (typeof ctx.applyVisual === "function") ctx.applyVisual(next);
          }
        } else if (tool === "insert-via" && rootNode) {
          insertArrayRow(ctx, visual, walk(visual, rootNode.id, "vias"), ["net", "x", "y", "from_layer", "to_layer"]);
        } else if (tool === "insert-keepout" && rootNode) {
          insertArrayRow(ctx, visual, walk(visual, rootNode.id, "keepout"), ["layer", "x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"]);
        } else if (tool === "duplicate-row" && rootNode && spec.table) {
          duplicateArrayRow(ctx, visual, walk(visual, rootNode.id, spec.table));
        } else if (tool === "insert-line" && rootNode && spec.text) {
          insertTextLine(ctx, visual, walk(visual, rootNode.id, spec.text));
        } else if (tool === "move" || tool === "rotate" || tool === "scale" || tool === "razor" || tool === "route" || tool === "paint") {
          host.setAttribute("data-tool", tool);
          const mount = host.querySelector("[data-runtime]");
          if (mount) mount.setAttribute("data-tool", tool);
        } else if (tool === "play") {
          host.setAttribute("data-playing", "1");
          const mount = host.querySelector("[data-runtime]");
          if (mount) mount.setAttribute("data-playing", "1");
        } else if (tool === "pause") {
          host.setAttribute("data-playing", "0");
          const mount = host.querySelector("[data-runtime]");
          if (mount) mount.setAttribute("data-playing", "0");
        } else if (tool === "frame") {
          const mount = host.querySelector("[data-runtime]");
          if (mount) mount.scrollIntoView({ block: "nearest" });
        } else if (tool === "focus-runtime") {
          const mount = host.querySelector("[data-runtime]");
          if (mount) mount.scrollIntoView({ block: "nearest" });
        } else if (typeof spec.onTool === "function") {
          spec.onTool(tool, { ctx: ctx, visual: visual, root: rootNode, walk: walk });
        }
      });
    });
    host.querySelectorAll("[data-plugin-del-row]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!rootNode) return;
        const wrap = btn.closest("[data-table-key]");
        const key = (wrap && wrap.getAttribute("data-table-key")) || spec.table;
        if (!key) return;
        deleteArrayRow(ctx, visual, walk(visual, rootNode.id, key), btn.getAttribute("data-plugin-del-row"));
      });
    });
    host.querySelectorAll(".me-plugin-outline-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const id = btn.getAttribute("data-node-id");
        if (id && window.ZintriqEngine) window.ZintriqEngine.selection.set([id]);
      });
    });
    const filter = host.querySelector("[data-outline-filter]");
    if (filter) {
      filter.addEventListener("input", function () {
        const q = String(filter.value || "").toLowerCase();
        host.querySelectorAll(".me-plugin-outline-item").forEach(function (item) {
          const label = item.getAttribute("data-outline-label") || item.textContent.toLowerCase();
          item.parentNode.hidden = q && label.indexOf(q) < 0;
        });
      });
    }
  }

  function makePlugin(spec) {
    const state = { boxes: [], visual: null, unsub: null };

    function registerCommands() {
      if (!window.ZintriqEngine || !window.ZintriqEngine.command) return;
      window.ZintriqEngine.command.unregisterOwner(spec.id);
      window.ZintriqEngine.command.register(
        "plugin." + spec.id + ".replace",
        function () {
          if (typeof state._applyCode === "function") state._applyCode(spec.seed);
        },
        { plugin: spec.id, title: "Replace with " + spec.name },
        spec.id
      );
      if (spec.table) {
        window.ZintriqEngine.command.register(
          "plugin." + spec.id + ".insertRow",
          function () {
            if (!state.visual || !state.root) return;
            insertArrayRow(state._ctx || {}, state.visual, walk(state.visual, state.root.id, spec.table), spec.rowFields);
          },
          { plugin: spec.id, title: "Insert row" },
          spec.id
        );
      }
    }

    return {
      id: spec.id,
      name: spec.name,
      surfaces: spec.surfaces || ["describe"],
      pane: "plugin",
      deactivate: function () {
        state.boxes = [];
        if (state._rafHost && state._rafHost._raf) {
          root.cancelAnimationFrame(state._rafHost._raf);
          state._rafHost._raf = 0;
        }
      },
      dispose: function () {
        state.boxes = [];
        state.visual = null;
        state.root = null;
        if (window.ZintriqEngine) window.ZintriqEngine.command.unregisterOwner(spec.id);
        if (state.unsub) {
          state.unsub();
          state.unsub = null;
        }
      },
      activate: function () {
        registerCommands();
      },
      syncCommands: registerCommands,
      render: function (host, ctx) {
        state.visual = ctx.visual || state.visual;
        state._ctx = ctx;
        state._applyCode = ctx.applyCode;
        const visual = state.visual;
        const domain = domainRoot(visual, spec);
        state.root = domain;
        const ready = !!(
          domain &&
          spec.kindValue &&
          walk(visual, domain.id, "kind") &&
          (walk(visual, domain.id, "kind").properties || {}).value === spec.kindValue
        );
        let body = "";
        state.boxes = [];
        if (ready) {
          body += '<div class="me-plugin-layout">';
          body += '<aside class="me-plugin-side">' + drawOutline(visual, domain) + "</aside>";
          body += '<div class="me-plugin-main">';
          if (spec.sheet) body += drawSheet(visual, domain, spec.sheet);
          if (spec.tables && spec.tables.some(function (table) { return table.key === "keepout"; })) {
            body += drawKeepoutCounts(visual, domain);
          }
          if (spec.tables && spec.tables.length) {
            spec.tables.forEach(function (table) {
              body += drawTable(visual, walk(visual, domain.id, table.key), table.fieldOptions || spec.fieldOptions, table.key);
            });
          } else if (spec.table) {
            body += drawTable(visual, walk(visual, domain.id, spec.table), spec.fieldOptions, spec.table);
          }
          if (spec.dopesheet) {
            body += drawTable(
              visual,
              walk(visual, domain.id, spec.dopesheet.table),
              spec.dopesheet.fieldOptions || spec.fieldOptions,
              spec.dopesheet.table,
              host.getAttribute("data-ease-row") || ""
            );
            body += drawEaseHandles();
          }
          if (spec.text) body += drawTextList(visual, walk(visual, domain.id, spec.text));
          if (spec.timeline) body += drawTimeline(visual, domain, spec);
          if (spec.layout === "graph") {
            const graph = drawGraph(visual, domain);
            body += graph.html;
            state.boxes = graph.boxes;
          }
          if (spec.runtime) body += wrapViewport('<div class="me-plugin-runtime" data-runtime="' + escapeHtml(spec.runtime) + '"></div>', spec);
          body += "</div></div>";
        } else {
          body +=
            '<p class="me-plugin-empty">This description has no <strong>' +
            escapeHtml(spec.name) +
            "</strong> object yet. Add it, or replace the document with one.</p>";
        }
        host.innerHTML = toolbarHtml(spec, ready) + body + statusHtml(spec, ready, visual, domain);
        bindFields(host, spec, ctx, visual, domain);
        if (ready && spec.dopesheet) bindEaseHandles(host, spec, ctx, visual, domain);
        registerCommands();
        if (ready && spec.runtime && window.ZintriqEditorRuntimes && window.ZintriqEditorRuntimes[spec.runtime]) {
          const mount = host.querySelector("[data-runtime]");
          if (mount) {
            state._rafHost = mount;
            window.ZintriqEditorRuntimes[spec.runtime](mount, visual, spec, ctx, walk, domainRoot);
          }
        }
      },
      hitTest: function (event, ctx) {
        if (event.target && event.target.closest && event.target.closest("button, input, textarea, select, label")) return null;
        const host = ctx.host;
        const svg = host && host.querySelector("svg");
        if (!svg || !state.boxes.length) {
          const row = event.target && event.target.closest ? event.target.closest("[data-node-id]") : null;
          if (!row) return null;
          const id = row.getAttribute("data-node-id");
          const box = state.boxes.find(function (item) {
            return item.id === id;
          });
          return box ? { id: box.id, node: box.node } : { id: id, node: null };
        }
        if (!svg.createSVGPoint || !svg.getScreenCTM) return null;
        const ctm = svg.getScreenCTM();
        if (!ctm) return null;
        const pt = svg.createSVGPoint();
        pt.x = event.clientX;
        pt.y = event.clientY;
        const loc = pt.matrixTransform(ctm.inverse());
        for (let i = state.boxes.length - 1; i >= 0; i -= 1) {
          const box = state.boxes[i];
          if (loc.x >= box.x && loc.x <= box.x + box.w && loc.y >= box.y && loc.y <= box.y + box.h) {
            return { id: box.id, node: box.node };
          }
        }
        return null;
      },
      edit: function (op, ctx) {
        if (!op) return;
        if (op.type === "set" && op.id && state.visual) {
          commitLiteral(ctx || state._ctx || {}, state.visual, op.id, op.fieldType, op.value);
          return;
        }
        if (op.type === "view" && op.id && state.visual) {
          const panel = op.panel;
          if (op.field === "tx" || op.field === "ty") {
            const tx = panel ? panel.querySelector('[data-view-node="' + op.id + '"][data-view-field="tx"]') : null;
            const ty = panel ? panel.querySelector('[data-view-node="' + op.id + '"][data-view-field="ty"]') : null;
            commitView(ctx || state._ctx || {}, state.visual, op.id, {
              transform: { x: Number(tx && tx.value) || 0, y: Number(ty && ty.value) || 0 },
            });
            return;
          }
          const patch = {};
          patch[op.field] = op.value;
          commitView(ctx || state._ctx || {}, state.visual, op.id, patch);
          return;
        }
        if (op.id && window.ZintriqEngine) window.ZintriqEngine.selection.set([op.id]);
      },
      getPropertyPanel: function (ctx) {
        const visual = (ctx && ctx.visual) || state.visual;
        const id = window.ZintriqEngine ? window.ZintriqEngine.selection.primary() : "";
        const node = ((visual && visual.nodes) || []).find(function (item) {
          return item.id === id;
        });
        if (!node) return "<p class='me-props-empty'>Select a field or graph node</p>";
        const props = node.properties || {};
        const value = props.has_value ? props.value : "";
        const view = props.view || {};
        const transform = view.transform || {};
        const marks = (view.marks || []).join(", ");
        let html =
          "<form class='me-props' data-props='1'><p class='me-props-id'>" +
          escapeHtml(node.kind + " · " + node.id) +
          "</p>";
        if (node.kind === "literal") {
          html +=
            "<label>Value" +
            inputFor(props.type || "string", value, 'data-field-id="' + escapeHtml(node.id) + '" data-field-type="' + escapeHtml(props.type || "string") + '"') +
            "</label>";
        }
        html +=
          "<fieldset class='me-props-view'><legend>View marks</legend>" +
          '<label>x<input type="number" data-view-node="' +
          escapeHtml(node.id) +
          '" data-view-field="tx" value="' +
          escapeHtml(transform.x || 0) +
          '"></label>' +
          '<label>y<input type="number" data-view-node="' +
          escapeHtml(node.id) +
          '" data-view-field="ty" value="' +
          escapeHtml(transform.y || 0) +
          '"></label>' +
          '<label>marks<input type="text" data-view-node="' +
          escapeHtml(node.id) +
          '" data-view-field="marks" value="' +
          escapeHtml(marks) +
          '"></label></fieldset></form>';
        return html;
      },
    };
  }

  root.ZintriqEditorKit = {
    makePlugin: makePlugin,
    domainRoot: domainRoot,
    walk: walk,
    insertArrayRow: insertArrayRow,
    deleteArrayRow: deleteArrayRow,
    duplicateArrayRow: duplicateArrayRow,
  };
})(window);
