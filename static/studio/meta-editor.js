(function () {
  const codeEl = document.getElementById("me-code");
  function codeLang() {
    const el = document.querySelector('input[name="me-code-lang"]:checked');
    return (el && el.value) || "json";
  }
  const visualEl = document.getElementById("me-visual");
  const pageEl = document.getElementById("me-page");
  const pagesEl = document.getElementById("me-pages");
  const copyEl = document.getElementById("me-copy");
  const titleEl = document.getElementById("me-page-title");
  const siteTitleWrap = document.getElementById("me-site-title-wrap");
  const siteTitleEl = document.getElementById("me-site-title");
  const systemTitleWrap = document.getElementById("me-system-title-wrap");
  const systemTitleEl = document.getElementById("me-system-title");
  const pageKeyWrap = document.getElementById("me-page-key-wrap");
  const pageKeyEl = document.getElementById("me-page-key");
  const boundFields = document.getElementById("me-bound-fields");
  const boundIdEl = document.getElementById("me-bound-id");
  const boundSurfaceEl = document.getElementById("me-bound-surface");
  const boundTargetEl = document.getElementById("me-bound-target");
  const boundLevelEl = document.getElementById("me-bound-level");
  const blocksEl = document.getElementById("me-blocks");
  const blockAddEl = document.getElementById("me-block-add");
  const assetsEl = document.getElementById("me-assets");
  const themeEl = document.getElementById("me-theme");
  const themeAccentEl = document.getElementById("me-theme-accent");
  const themeBgEl = document.getElementById("me-theme-background");
  const themeFgEl = document.getElementById("me-theme-color");
  const themeMeasureEl = document.getElementById("me-theme-measure");
  const themeSpaceEl = document.getElementById("me-theme-space");
  const slugEl = document.getElementById("me-slug");
  try {
    if (slugEl && slugEl.value) sessionStorage.setItem("zintriq-draft-slug", slugEl.value);
  } catch (_err) {
    /* ignore */
  }
  const eventsEl = document.getElementById("me-events");
  const statusEl = document.getElementById("me-status");
  const openEl = document.getElementById("me-open");
  const zipEl = document.getElementById("me-zip");
  let timer = 0;
  let lastStamped = codeEl ? codeEl.value : "";
  let lastPackId = "";

  const simEl = document.getElementById("me-sim");
  const stateEl = document.getElementById("me-state");
  const eventBtns = document.getElementById("me-event-btns");
  const FORMS = {
    atom: '{\n  "form": "atom",\n  "type": "string",\n  "value": ""\n}',
    struct: '{\n  "form": "struct",\n  "fields": {\n    "name": {\n      "form": "atom",\n      "type": "string",\n      "value": ""\n    }\n  }\n}',
    sequence: '{\n  "form": "sequence",\n  "items": []\n}',
    mapping: '{\n  "form": "mapping",\n  "entries": {}\n}',
    page:
      '{\n  "fields": {\n    "body": {\n      "form": "sequence",\n      "items": [\n        { "form": "atom", "type": "string", "value": "First paragraph." }\n      ]\n    },\n    "kind": { "form": "atom", "type": "string", "value": "software.page" },\n    "theme": {\n      "form": "struct",\n      "fields": {\n        "accent": { "form": "atom", "type": "string", "value": "#06c" },\n        "background": { "form": "atom", "type": "string", "value": "#fff" },\n        "color": { "form": "atom", "type": "string", "value": "#111" },\n        "measure": { "form": "atom", "type": "int", "value": 40 },\n        "space": { "form": "atom", "type": "int", "value": 24 }\n      }\n    },\n    "title": { "form": "atom", "type": "string", "value": "Untitled" }\n  },\n  "form": "struct"\n}',
    site:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "software.site" },\n    "pages": {\n      "form": "sequence",\n      "items": [\n        {\n          "fields": {\n            "body": { "form": "sequence", "items": [{ "form": "atom", "type": "string", "value": "Welcome." }] },\n            "key": { "form": "atom", "type": "string", "value": "home" },\n            "title": { "form": "atom", "type": "string", "value": "Home" }\n          },\n          "form": "struct"\n        },\n        {\n          "fields": {\n            "body": { "form": "sequence", "items": [{ "form": "atom", "type": "string", "value": "About this system." }] },\n            "key": { "form": "atom", "type": "string", "value": "about" },\n            "title": { "form": "atom", "type": "string", "value": "About" }\n          },\n          "form": "struct"\n        }\n      ]\n    },\n    "theme": {\n      "form": "struct",\n      "fields": {\n        "accent": { "form": "atom", "type": "string", "value": "#06c" },\n        "background": { "form": "atom", "type": "string", "value": "#fff" },\n        "color": { "form": "atom", "type": "string", "value": "#111" },\n        "measure": { "form": "atom", "type": "int", "value": 40 },\n        "space": { "form": "atom", "type": "int", "value": 24 }\n      }\n    },\n    "title": { "form": "atom", "type": "string", "value": "Site" }\n  },\n  "form": "struct"\n}',
    machine:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "state_machine" },\n    "state": { "form": "atom", "type": "string", "value": "idle" },\n    "transitions": { "form": "sequence", "items": [] }\n  },\n  "form": "struct"\n}',
    boundary:
      '{\n  "fields": {\n    "id": { "form": "atom", "type": "string", "value": "software.custom" },\n    "kind": { "form": "atom", "type": "string", "value": "meta.boundary" },\n    "meta_level": { "form": "atom", "type": "int", "value": 0 },\n    "name": { "form": "atom", "type": "string", "value": "Custom software" },\n    "surface": { "form": "atom", "type": "string", "value": "software" },\n    "target": { "form": "atom", "type": "string", "value": "web_build" }\n  },\n  "form": "struct"\n}',
    hardware:
      '{\n  "fields": {\n    "act": { "form": "atom", "type": "string", "value": "none" },\n    "display": { "form": "atom", "type": "string", "value": "none" },\n    "kind": { "form": "atom", "type": "string", "value": "hardware.module" },\n    "sense": { "form": "atom", "type": "string", "value": "presence" },\n    "title": { "form": "atom", "type": "string", "value": "Module" }\n  },\n  "form": "struct"\n}',
    os:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "os.surface" },\n    "title": { "form": "atom", "type": "string", "value": "Host" }\n  },\n  "form": "struct"\n}',
    system:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "meta.system" },\n    "parts": {\n      "form": "sequence",\n      "items": [\n        {\n          "fields": {\n            "key": { "form": "atom", "type": "string", "value": "home" },\n            "of": {\n              "fields": {\n                "body": { "form": "sequence", "items": [{ "form": "atom", "type": "string", "value": "A part of the system." }] },\n                "kind": { "form": "atom", "type": "string", "value": "software.page" },\n                "title": { "form": "atom", "type": "string", "value": "Home" }\n              },\n              "form": "struct"\n            },\n            "title": { "form": "atom", "type": "string", "value": "Home" }\n          },\n          "form": "struct"\n        },\n        {\n          "fields": {\n            "key": { "form": "atom", "type": "string", "value": "gate" },\n            "of": {\n              "fields": {\n                "id": { "form": "atom", "type": "string", "value": "software.custom" },\n                "kind": { "form": "atom", "type": "string", "value": "meta.boundary" },\n                "meta_level": { "form": "atom", "type": "int", "value": 0 },\n                "name": { "form": "atom", "type": "string", "value": "Custom software" },\n                "surface": { "form": "atom", "type": "string", "value": "software" },\n                "target": { "form": "atom", "type": "string", "value": "web_build" }\n              },\n              "form": "struct"\n            },\n            "title": { "form": "atom", "type": "string", "value": "Gate" }\n          },\n          "form": "struct"\n        }\n      ]\n    },\n    "title": { "form": "atom", "type": "string", "value": "System" }\n  },\n  "form": "struct"\n}',
    scene:
      '{\n  "fields": {\n    "camera": { "form": "struct", "fields": { "x": { "form": "atom", "type": "float", "value": 0 }, "y": { "form": "atom", "type": "float", "value": 0 }, "z": { "form": "atom", "type": "float", "value": 8 } } },\n    "kind": { "form": "atom", "type": "string", "value": "scene" },\n    "mesh": { "form": "atom", "type": "string", "value": "cube" },\n    "title": { "form": "atom", "type": "string", "value": "Scene" }\n  },\n  "form": "struct"\n}',
    cad:
      '{\n  "fields": {\n    "depth": { "form": "atom", "type": "float", "value": 2 },\n    "height": { "form": "atom", "type": "float", "value": 2 },\n    "kind": { "form": "atom", "type": "string", "value": "cad.solid" },\n    "mesh": { "form": "atom", "type": "string", "value": "box" },\n    "title": { "form": "atom", "type": "string", "value": "Solid" },\n    "width": { "form": "atom", "type": "float", "value": 2 }\n  },\n  "form": "struct"\n}',
    checkout:
      '{\n  "fields": {\n    "currency": { "form": "atom", "type": "string", "value": "usd" },\n    "items": { "form": "sequence", "items": [{ "form": "struct", "fields": { "name": { "form": "atom", "type": "string", "value": "Item" }, "price": { "form": "atom", "type": "float", "value": 10 } } }] },\n    "kind": { "form": "atom", "type": "string", "value": "commerce.checkout" },\n    "title": { "form": "atom", "type": "string", "value": "Checkout" }\n  },\n  "form": "struct"\n}',
    channel:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "social.channel" },\n    "messages": { "form": "sequence", "items": [{ "form": "atom", "type": "string", "value": "channel opened" }] },\n    "name": { "form": "atom", "type": "string", "value": "general" },\n    "title": { "form": "atom", "type": "string", "value": "Channel" }\n  },\n  "form": "struct"\n}',
    broadcast:
      '{\n  "fields": {\n    "clips": { "form": "sequence", "items": [{ "form": "atom", "type": "string", "value": "pilot" }] },\n    "kind": { "form": "atom", "type": "string", "value": "media.channel" },\n    "name": { "form": "atom", "type": "string", "value": "studio" },\n    "title": { "form": "atom", "type": "string", "value": "Broadcast" }\n  },\n  "form": "struct"\n}',
    ai:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "ai" },\n    "model": { "form": "atom", "type": "string", "value": "local.json" },\n    "prompt": { "form": "atom", "type": "string", "value": "Hello" },\n    "title": { "form": "atom", "type": "string", "value": "Session" }\n  },\n  "form": "struct"\n}',
    world:
      '{\n  "fields": {\n    "kind": { "form": "atom", "type": "string", "value": "world.place" },\n    "title": { "form": "atom", "type": "string", "value": "Place" }\n  },\n  "form": "struct"\n}',
  };

  function http() {
    return window.zintriq.http;
  }

  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = "me-status" + (kind ? " is-" + kind : "");
  }

  async function stampConsistency() {
    if (!slugEl) return;
    let extra = "";
    const dirty = codeEl && codeEl.value !== lastStamped;
    const slug = slugEl.value;
    if (dirty) {
      extra = "未盖章";
      setStatus(extra);
      if (window.zintriqDesktop && window.zintriqDesktop.setDirty) window.zintriqDesktop.setDirty(true);
    }
    try {
      const res = await http().get("/api/plugin?slug=" + encodeURIComponent(slug));
      const data = await res.json().catch(function () {
        return {};
      });
      const bound = ((data && data.packs) || []).find(function (row) {
        return row && row.draft_slug === slug;
      });
      if (bound && bound.id) lastPackId = bound.id;
      if (!dirty && bound && bound.installed && !bound.draft_matches) {
        extra = "草稿不是这份包";
        setStatus(extra, "err");
      } else if (!dirty && bound && bound.installed && bound.draft_matches) {
        extra = "盖章一致";
      }
      if (window.ZintriqWorkbench) window.ZintriqWorkbench._timeline = data.timeline || [];
    } catch {
      /* local host */
    }
    const bar = document.getElementById("me-statusbar");
    if (bar) bar.setAttribute("data-stamp", extra);
    if (window.ZintriqWorkbench && window.ZintriqWorkbench.paintStatus) window.ZintriqWorkbench.paintStatus();
  }

  function renderVisual(visual) {
    lastVisual = visual || null;
    if (!visualEl) return;
    const nodes = (visual && visual.nodes) || [];
    if (!nodes.length) {
      visualEl.textContent = "No nodes";
      return;
    }
    visualEl.innerHTML = nodes
      .map(function (node) {
        const props = JSON.stringify(node.properties || {});
        const current = node.id === selectedNodeId ? " is-current" : "";
        return (
          '<button type="button" class="me-node' +
          current +
          '" data-node-id="' +
          escapeHtml(node.id || "") +
          '"><strong>' +
          escapeHtml(node.kind || "") +
          "</strong> " +
          escapeHtml(node.id || "") +
          "<div>" +
          escapeHtml(props) +
          "</div></button>"
        );
      })
      .join("");
    visualEl.querySelectorAll("[data-node-id]").forEach(function (node) {
      node.addEventListener("click", function () {
        selectedNodeId = node.getAttribute("data-node-id") || "";
        showInspect(selectedNodeId);
        visualEl.querySelectorAll(".me-node").forEach(function (item) {
          item.classList.toggle("is-current", item === node);
        });
      });
    });
    if (selectedNodeId) showInspect(selectedNodeId);
  }

  function showInspect(nodeId) {
    const inspect = document.getElementById("me-visual-inspect");
    const idEl = document.getElementById("me-visual-id");
    const propsEl = document.getElementById("me-visual-props");
    const applyBtn = document.getElementById("me-visual-apply");
    const node = ((lastVisual && lastVisual.nodes) || []).find(function (item) {
      return item.id === nodeId;
    });
    if (!inspect) return;
    inspect.hidden = false;
    if (!node) {
      if (idEl) idEl.textContent = "Select a node";
      if (propsEl) propsEl.hidden = true;
      if (applyBtn) applyBtn.hidden = true;
      return;
    }
    if (idEl) idEl.textContent = (node.kind || "") + " · " + node.id;
    if (propsEl) {
      propsEl.hidden = false;
      propsEl.value = JSON.stringify(node.properties || {}, null, 2);
    }
    if (applyBtn) applyBtn.hidden = false;
  }

  function renderGraph(visual) {
    const graphEl = document.getElementById("me-graph");
    if (!graphEl) return;
    const nodes = (visual && visual.nodes) || [];
    const edges = (visual && visual.edges) || [];
    if (!nodes.length && !edges.length) {
      graphEl.textContent = "No graph";
      return;
    }
    const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
    const cellW = 168;
    const cellH = 88;
    const width = Math.max(360, cols * cellW + 48);
    const height = Math.max(220, Math.ceil(nodes.length / cols) * cellH + 48);
    const pos = {};
    nodes.forEach(function (node, i) {
      pos[node.id] = {
        x: 28 + (i % cols) * cellW + 70,
        y: 28 + Math.floor(i / cols) * cellH + 28,
      };
    });
    const lines = edges
      .map(function (edge) {
        const a = pos[edge.source];
        const b = pos[edge.target];
        if (!a || !b) return "";
        return (
          '<line x1="' +
          a.x +
          '" y1="' +
          a.y +
          '" x2="' +
          b.x +
          '" y2="' +
          b.y +
          '" stroke="currentColor" stroke-width="1.25" />'
        );
      })
      .join("");
    const boxes = nodes
      .map(function (node) {
        const p = pos[node.id] || { x: 40, y: 40 };
        const current = node.id === selectedNodeId ? " is-current" : "";
        const label = ((node.kind || "") + " " + (node.id || "")).trim().slice(0, 22);
        return (
          '<g class="me-graph-node' +
          current +
          '" data-node-id="' +
          escapeHtml(node.id || "") +
          '">' +
          '<rect x="' +
          (p.x - 58) +
          '" y="' +
          (p.y - 18) +
          '" width="116" height="36" fill="none" stroke="currentColor" rx="6" />' +
          '<text x="' +
          p.x +
          '" y="' +
          (p.y + 5) +
          '" text-anchor="middle" font-size="11" fill="currentColor">' +
          escapeHtml(label) +
          "</text></g>"
        );
      })
      .join("");
    graphEl.innerHTML =
      '<div class="me-graph-canvas"><svg viewBox="0 0 ' +
      width +
      " " +
      height +
      '" width="' +
      width +
      '" height="' +
      height +
      '">' +
      lines +
      boxes +
      "</svg></div>";
    graphEl.querySelectorAll("[data-node-id]").forEach(function (node) {
      node.addEventListener("click", function () {
        selectedNodeId = node.getAttribute("data-node-id") || "";
        showInspect(selectedNodeId);
        graphEl.querySelectorAll(".me-graph-node").forEach(function (item) {
          item.classList.toggle("is-current", item === node);
        });
      });
    });
  }

  function renderSpaceDoc(data) {
    const el = document.getElementById("me-space-doc");
    if (!el) return;
    const parts = (data && data.space_parts) || [];
    const isSpace = !!(data && data.space);
    if (!isSpace && !parts.length) {
      el.innerHTML = "<p>Open Meta space to edit boundaries as the document.</p>";
      return;
    }
    const body = parts
      .map(function (part) {
        const current = part.key === currentPageKey ? " is-current" : "";
        const kind = part.kind || "part";
        const bound = part.boundary || {};
        const extra = bound.id ? " · " + bound.id : "";
        return (
          '<button type="button" class="me-space-part' +
          current +
          '" data-space-key="' +
          escapeHtml(part.key || "") +
          '"><h3>' +
          escapeHtml(part.title || part.key || "") +
          "</h3><p>" +
          escapeHtml(kind + extra) +
          "</p></button>"
        );
      })
      .join("");
    const actions =
      '<div class="me-space-actions">' +
      '<button type="button" class="me-btn" data-part-kind="boundary">Add boundary</button>' +
      '<button type="button" class="me-btn" data-part-kind="hardware">Add hardware</button>' +
      '<button type="button" class="me-btn" data-part-kind="os">Add os</button>' +
      (data && data.can_remove_part
        ? '<button type="button" class="me-btn" data-part-remove>Remove</button>'
        : "") +
      "</div>";
    el.innerHTML = body + actions;
    el.querySelectorAll("[data-space-key]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        preview(btn.getAttribute("data-space-key"));
      });
    });
    el.querySelectorAll("[data-part-kind]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        mutateSystemPart("add", { kind: btn.getAttribute("data-part-kind") || "boundary" });
      });
    });
    const removeBtn = el.querySelector("[data-part-remove]");
    if (removeBtn) {
      removeBtn.addEventListener("click", function () {
        mutateSystemPart("remove");
      });
    }
  }

  function renderUir(uir) {
    const uirEl = document.getElementById("me-uir");
    if (!uirEl || !uir) return;
    uirEl.value = JSON.stringify(uir, null, 2);
  }

  async function applyUir(quiet) {
    const uirEl = document.getElementById("me-uir");
    if (!uirEl) return;
    let uir;
    try {
      uir = JSON.parse(uirEl.value || "{}");
    } catch (_err) {
      if (!quiet) setStatus("UIR must be JSON", "err");
      return;
    }
    const res = await http().post("/api/builder-core/meta/preview", {
      uir: uir,
      slug: slugEl.value,
      page_key: currentPageKey,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "UIR apply failed", "err");
      return;
    }
    applyPreview(data, "uir");
  }

  async function applyVisual() {
    if (!lastVisual) {
      setStatus("No visual tree", "err");
      return;
    }
    const propsEl = document.getElementById("me-visual-props");
    if (selectedNodeId && propsEl && !propsEl.hidden) {
      let props;
      try {
        props = JSON.parse(propsEl.value || "{}");
      } catch (_err) {
        setStatus("Visual properties must be JSON", "err");
        return;
      }
      lastVisual.nodes = (lastVisual.nodes || []).map(function (node) {
        if (node.id !== selectedNodeId) return node;
        return Object.assign({}, node, { properties: props });
      });
    }
    const res = await http().post("/api/builder-core/meta/preview", {
      visual: lastVisual,
      slug: slugEl.value,
      page_key: currentPageKey,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Visual apply failed", "err");
      return;
    }
    applyPreview(data, "visual");
  }

  async function applyVisualTree(visual) {
    if (!visual) {
      setStatus("No visual tree", "err");
      return;
    }
    lastVisual = visual;
    const res = await http().post("/api/builder-core/meta/preview", {
      visual: visual,
      slug: slugEl.value,
      page_key: currentPageKey,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Diagram apply failed", "err");
      return;
    }
    applyPreview(data, "diagram");
  }

  let currentPageKey = "";
  let lastPreview = {};
  let lastVisual = null;
  let selectedNodeId = "";
  let history = [];
  let historyIndex = -1;
  let applyingHistory = false;

  function snapshot() {
    return {
      code: codeEl.value,
      slug: slugEl.value,
      events: eventsEl.value,
    };
  }

  function pushHistory() {
    if (window.ZintriqEngine) {
      if (window.ZintriqEngine.history.applying) return;
      window.ZintriqEngine.store.set({
        code: codeEl.value,
        events: eventsEl.value,
        preview: lastPreview,
        slug: slugEl.value,
        visual: lastVisual,
      });
      window.ZintriqEngine.history.push();
      return;
    }
    if (applyingHistory) return;
    const next = snapshot();
    const prev = history[historyIndex];
    if (prev && prev.code === next.code && prev.slug === next.slug && prev.events === next.events) return;
    history = history.slice(0, historyIndex + 1);
    history.push(next);
    if (history.length > 40) history.shift();
    historyIndex = history.length - 1;
  }

  function restoreHistory(delta) {
    if (window.ZintriqEngine) {
      const entry = delta < 0 ? window.ZintriqEngine.history.undo() : window.ZintriqEngine.history.redo();
      if (!entry) return;
      window.ZintriqEngine.history.applying = true;
      codeEl.value = entry.code;
      slugEl.value = entry.slug;
      eventsEl.value = entry.events;
      preview().finally(function () {
        window.ZintriqEngine.history.applying = false;
      });
      return;
    }
    const index = historyIndex + delta;
    if (index < 0 || index >= history.length) return;
    historyIndex = index;
    const entry = history[index];
    applyingHistory = true;
    codeEl.value = entry.code;
    slugEl.value = entry.slug;
    eventsEl.value = entry.events;
    preview().finally(function () {
      applyingHistory = false;
    });
  }

  function renderPage(html) {
    if (!pageEl) return;
    pageEl.srcdoc = html || "";
  }

  window.addEventListener("message", function (ev) {
    if (!pageEl || ev.source !== pageEl.contentWindow) return;
    const data = ev.data || {};
    if (data.source !== "zintriq-meta") return;
    const key = String(data.page || "").trim();
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(key)) return;
    preview(key);
  });

  function renderPageTabs(pages, active, meta) {
    if (!pagesEl) return;
    if (!pages || !pages.length) {
      pagesEl.hidden = true;
      pagesEl.innerHTML = "";
      currentPageKey = "";
      return;
    }
    pagesEl.hidden = false;
    currentPageKey = active || pages[0].key || "";
    const isSystem = meta && meta.kind === "meta.system";
    const canPage = meta && meta.can_page_ops;
    pagesEl.innerHTML = pages
      .map(function (item) {
        const pressed = item.key === currentPageKey ? "true" : "false";
        return (
          '<button type="button" class="me-btn me-btn--tiny" data-page-key="' +
          escapeHtml(item.key) +
          '" aria-pressed="' +
          pressed +
          '">' +
          escapeHtml(item.title || item.key) +
          "</button>"
        );
      })
      .join("") +
      (canPage ? '<button type="button" class="me-btn me-btn--tiny" data-page-add>Add page</button>' : "") +
      (canPage ? '<button type="button" class="me-btn me-btn--tiny" data-page-duplicate>Duplicate page</button>' : "") +
      (canPage && pages.length > 1
        ? '<button type="button" class="me-btn me-btn--tiny" data-page-remove>Remove page</button>' +
          '<button type="button" class="me-btn me-btn--tiny" data-page-move="-1">Move left</button>' +
          '<button type="button" class="me-btn me-btn--tiny" data-page-move="1">Move right</button>'
        : "") +
      (isSystem ? '<button type="button" class="me-btn me-btn--tiny" data-part-add>Add part</button>' : "") +
      (isSystem ? '<button type="button" class="me-btn me-btn--tiny" data-part-kind="boundary">Add boundary</button>' : "") +
      (isSystem ? '<button type="button" class="me-btn me-btn--tiny" data-part-kind="hardware">Add hardware</button>' : "") +
      (isSystem ? '<button type="button" class="me-btn me-btn--tiny" data-part-kind="os">Add os</button>' : "") +
      (isSystem ? '<button type="button" class="me-btn me-btn--tiny" data-part-duplicate>Duplicate part</button>' : "") +
      (isSystem && meta.can_remove_part
        ? '<button type="button" class="me-btn me-btn--tiny" data-part-remove>Remove part</button>'
        : "") +
      (isSystem && meta.can_move_part
        ? '<button type="button" class="me-btn me-btn--tiny" data-part-move="-1">Move part left</button>' +
          '<button type="button" class="me-btn me-btn--tiny" data-part-move="1">Move part right</button>'
        : "");
    pagesEl.querySelectorAll("[data-page-key]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        preview(btn.getAttribute("data-page-key"));
      });
    });
    const addBtn = pagesEl.querySelector("[data-page-add]");
    if (addBtn) {
      addBtn.addEventListener("click", function () {
        mutateSitePage("add");
      });
    }
    const dupBtn = pagesEl.querySelector("[data-page-duplicate]");
    if (dupBtn) {
      dupBtn.addEventListener("click", function () {
        mutateSitePage("duplicate", currentPageKey);
      });
    }
    const removeBtn = pagesEl.querySelector("[data-page-remove]");
    if (removeBtn) {
      removeBtn.addEventListener("click", function () {
        mutateSitePage("remove", currentPageKey);
      });
    }
    pagesEl.querySelectorAll("[data-page-move]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        mutateSitePage("move", currentPageKey, { delta: Number(btn.getAttribute("data-page-move")) });
      });
    });
    const addPartBtn = pagesEl.querySelector("[data-part-add]");
    if (addPartBtn) {
      addPartBtn.addEventListener("click", function () {
        mutateSystemPart("add", { kind: meta && meta.space ? "boundary" : "page" });
      });
    }
    pagesEl.querySelectorAll("[data-part-kind]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        mutateSystemPart("add", { kind: btn.getAttribute("data-part-kind") || "page" });
      });
    });
    const dupPartBtn = pagesEl.querySelector("[data-part-duplicate]");
    if (dupPartBtn) {
      dupPartBtn.addEventListener("click", function () {
        mutateSystemPart("duplicate");
      });
    }
    const removePartBtn = pagesEl.querySelector("[data-part-remove]");
    if (removePartBtn) {
      removePartBtn.addEventListener("click", function () {
        mutateSystemPart("remove");
      });
    }
    pagesEl.querySelectorAll("[data-part-move]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        mutateSystemPart("move", { delta: Number(btn.getAttribute("data-part-move")) });
      });
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function saveDraft() {
    const res = await http().post("/api/builder-core/meta/drafts", {
      slug: slugEl.value,
      code: codeEl.value,
      events: eventsEl.value,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Draft not saved", "err");
      return false;
    }
    setStatus("Saved locally " + (data.updated_at || ""), "ok");
    pushCollab();
    return true;
  }

  async function preview(pageKey, source) {
    await saveDraft();
    const res = await http().post("/api/builder-core/meta/preview", {
      code: codeEl.value,
      language: codeLang(),
      slug: slugEl.value,
      page_key: pageKey || currentPageKey,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Preview failed", "err");
      return false;
    }
    applyPreview(data, source || "code");
    return true;
  }

  function currentView() {
    return document.body.getAttribute("data-meta-view") || "describe";
  }

  function applyPreview(data, source) {
    lastPreview = data || {};
    if (source !== "code") {
      if (codeLang() === "yaml" && data.yaml) codeEl.value = data.yaml;
      else if (data.code) codeEl.value = data.code;
    }
    if (source !== "visual") renderVisual(data.visual);
    else lastVisual = data.visual || lastVisual;
    renderGraph(data.visual);
    if (source !== "uir") renderUir(data.uir);
    renderSpaceDoc(data);
    renderPageTabs(data.pages, data.page_key, data);
    renderPage(data.page_html);
    renderCanvasTree(data.canvas);
    fillCopy(data);
    fillTheme(data);
    const uirOk = data.equivalent_uir !== false;
    const ok = data.equivalent && uirOk;
    setStatus(ok ? "visual ≡ code ≡ uir" : "not equivalent", ok ? "ok" : "err");
    renderSimulation(data.simulation);
    if (currentView() === "instantiate") loadExistingArtifact();
    pushHistory();
    if (window.ZintriqEditorViews && typeof window.ZintriqEditorViews.sync === "function") {
      window.ZintriqEditorViews.sync();
    }
  }

  function fillCopy(data) {
    if (!copyEl) return;
    if (typeof data.page_title !== "string") {
      copyEl.hidden = true;
      return;
    }
    copyEl.hidden = false;
    if (titleEl) titleEl.value = data.page_title;
    if (siteTitleWrap) {
      if (typeof data.site_title === "string") {
        siteTitleWrap.hidden = false;
        if (siteTitleEl) siteTitleEl.value = data.site_title;
      } else {
        siteTitleWrap.hidden = true;
      }
    }
    if (systemTitleWrap) {
      if (typeof data.system_title === "string") {
        systemTitleWrap.hidden = false;
        if (systemTitleEl) systemTitleEl.value = data.system_title;
      } else {
        systemTitleWrap.hidden = true;
      }
    }
    if (pageKeyWrap) {
      if (data.pages && data.pages.length) {
        pageKeyWrap.hidden = false;
        if (pageKeyEl) pageKeyEl.value = data.page_key || "";
      } else {
        pageKeyWrap.hidden = true;
      }
    }
    const bound = data.boundary;
    const systemSurface = data.copy_surface === "system";
    if (boundFields) {
      if (bound && typeof bound === "object") {
        boundFields.hidden = false;
        if (boundIdEl) boundIdEl.value = bound.id || "";
        if (boundSurfaceEl) boundSurfaceEl.value = bound.surface || "software";
        if (boundTargetEl) boundTargetEl.value = bound.target || "web_build";
        if (boundLevelEl) boundLevelEl.value = bound.meta_level == null ? 0 : bound.meta_level;
      } else {
        boundFields.hidden = true;
      }
    }
    const hideBlocks = !!(bound && typeof bound === "object") || systemSurface;
    if (blocksEl) blocksEl.hidden = hideBlocks;
    if (blockAddEl) blockAddEl.hidden = hideBlocks;
    if (hideBlocks) {
      if (assetsEl) assetsEl.hidden = true;
    } else {
      renderBlocks(data.page_blocks && data.page_blocks.length ? data.page_blocks : (data.page_body || []).map(function (text) {
        return { kind: "paragraph", text: text };
      }));
      renderAssets(data.page_assets);
    }
  }

  function renderAssets(names) {
    if (!assetsEl) return;
    const slug = slugEl.value.trim();
    const list = names || [];
    assetsEl.hidden = !list.length;
    assetsEl.innerHTML = list
      .map(function (name) {
        const safe = escapeHtml(name);
        const href =
          "/api/builder-core/meta/sites/" +
          encodeURIComponent(slug) +
          "/assets/" +
          encodeURIComponent(name);
        return (
          '<div class="me-asset" data-asset="' +
          safe +
          '">' +
          '<button type="button" data-asset-insert>' +
          '<img src="' +
          escapeHtml(href) +
          '" alt="">' +
          "<span>" +
          safe +
          "</span></button>" +
          '<button type="button" class="me-btn me-btn--tiny" data-asset-remove>Remove</button>' +
          "</div>"
        );
      })
      .join("");
    assetsEl.querySelectorAll("[data-asset-insert]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const row = btn.closest("[data-asset]");
        const name = row ? row.getAttribute("data-asset") : "";
        if (!name) return;
        const blocks = readBlocks();
        blocks.push({ kind: "image", text: "", src: name });
        renderBlocks(blocks);
      });
    });
    assetsEl.querySelectorAll("[data-asset-remove]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const row = btn.closest("[data-asset]");
        const name = row ? row.getAttribute("data-asset") : "";
        if (name) removeAsset(name);
      });
    });
  }

  async function removeAsset(name) {
    const slug = slugEl.value.trim();
    if (!slug) {
      setStatus("Slug required", "err");
      return;
    }
    const res = await http().post(
      "/api/builder-core/meta/sites/" + encodeURIComponent(slug) + "/assets/remove",
      { name: name }
    );
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Remove failed", "err");
      return;
    }
    renderAssets(data.assets);
    await preview();
    setStatus("Removed " + name, "ok");
  }

  function renderBlocks(blocks) {
    if (!blocksEl) return;
    blocksEl.innerHTML = (blocks || [])
      .map(function (item) {
        const kind = item.kind || "paragraph";
        const text = item.text || "";
        const to = item.to || "";
        return (
          '<div class="me-block" data-block data-kind="' +
          escapeHtml(kind) +
          '">' +
          '<select data-block-kind>' +
          '<option value="paragraph"' + (kind === "paragraph" ? " selected" : "") + ">Paragraph</option>" +
          '<option value="heading"' + (kind === "heading" ? " selected" : "") + ">Heading</option>" +
          '<option value="quote"' + (kind === "quote" ? " selected" : "") + ">Quote</option>" +
          '<option value="code"' + (kind === "code" ? " selected" : "") + ">Code</option>" +
          '<option value="link"' + (kind === "link" ? " selected" : "") + ">Link</option>" +
          '<option value="list"' + (kind === "list" ? " selected" : "") + ">List</option>" +
          '<option value="image"' + (kind === "image" ? " selected" : "") + ">Image</option>" +
          "</select>" +
          (kind === "list" || kind === "code"
            ? '<textarea data-block-items maxlength="4000" placeholder="' +
              (kind === "code" ? "code" : "one item per line") +
              '">' +
              escapeHtml((item.items || []).join("\n") || text) +
              "</textarea>"
            : '<input type="text" data-block-text maxlength="4000" placeholder="' +
              (kind === "image" ? "alt" : "text") +
              '" value="' +
              escapeHtml(text) +
              '">') +
          (kind === "heading"
            ? '<select data-block-level>' +
              '<option value="2"' + (String(item.level || 2) !== "3" ? " selected" : "") + ">H2</option>" +
              '<option value="3"' + (String(item.level) === "3" ? " selected" : "") + ">H3</option>" +
              "</select>"
            : "") +
          (kind === "link"
            ? '<input type="text" data-block-to maxlength="64" placeholder="page key" value="' +
              escapeHtml(to) +
              '">'
            : "") +
          (kind === "image"
            ? '<input type="text" data-block-src maxlength="64" placeholder="hero.png" value="' +
              escapeHtml(item.src || "") +
              '">'
            : "") +
          '<button type="button" class="me-btn me-btn--tiny" data-block-remove>Remove</button>' +
          "</div>"
        );
      })
      .join("");
    bindBlockRow(blocksEl);
  }

  function bindBlockRow(root) {
    root.querySelectorAll("[data-block-kind]").forEach(function (sel) {
      sel.addEventListener("change", function () {
        const row = sel.closest("[data-block]");
        if (!row) return;
        row.setAttribute("data-kind", sel.value);
        const current = readBlocks();
        renderBlocks(current);
      });
    });
    root.querySelectorAll("[data-block-remove]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const row = btn.closest("[data-block]");
        if (row) row.remove();
      });
    });
  }

  function readBlocks() {
    if (!blocksEl) return [];
    return Array.prototype.map.call(blocksEl.querySelectorAll("[data-block]"), function (row) {
      const kindSel = row.querySelector("[data-block-kind]");
      const textEl = row.querySelector("[data-block-text]");
      const toEl = row.querySelector("[data-block-to]");
      const kind = kindSel ? kindSel.value : row.getAttribute("data-kind") || "paragraph";
      const block = { kind: kind, text: textEl ? textEl.value : "" };
      if (kind === "link") block.to = toEl ? toEl.value.trim() : "";
      if (kind === "heading") {
        const levelEl = row.querySelector("[data-block-level]");
        block.level = levelEl && levelEl.value === "3" ? 3 : 2;
      }
      if (kind === "list") {
        const itemsEl = row.querySelector("[data-block-items]");
        block.items = itemsEl
          ? itemsEl.value.split(/\r?\n/).map(function (line) { return line.trim(); }).filter(Boolean)
          : [];
      }
      if (kind === "code") {
        const itemsEl = row.querySelector("[data-block-items]");
        block.text = itemsEl ? itemsEl.value : block.text;
      }
      if (kind === "image") {
        const srcEl = row.querySelector("[data-block-src]");
        block.src = srcEl ? srcEl.value.trim() : "";
      }
      return block;
    });
  }

  function fillTheme(data) {
    if (!themeEl) return;
    if (data && data.can_theme === false) {
      themeEl.hidden = true;
      return;
    }
    const scope = readThemeScope();
    const theme = scope === "page" ? data.page_theme_local || data.page_theme : data.page_theme;
    if (!theme || typeof theme !== "object") {
      themeEl.hidden = true;
      return;
    }
    themeEl.hidden = false;
    if (themeAccentEl) themeAccentEl.value = theme.accent || "";
    if (themeBgEl) themeBgEl.value = theme.background || "";
    if (themeFgEl) themeFgEl.value = theme.color || "";
    if (themeMeasureEl) themeMeasureEl.value = theme.measure === "" || theme.measure == null ? "" : theme.measure;
    if (themeSpaceEl) themeSpaceEl.value = theme.space === "" || theme.space == null ? "" : theme.space;
  }

  function readThemeScope() {
    const checked = themeEl ? themeEl.querySelector('input[name="me-theme-scope"]:checked') : null;
    return checked && checked.value === "page" ? "page" : "site";
  }

  async function mutateSitePage(op, key, extra) {
    extra = extra || {};
    const res = await http().post("/api/builder-core/meta/site-page", {
      code: codeEl.value,
      slug: slugEl.value,
      op: op,
      key: key || "",
      page_key: currentPageKey,
      title: op === "update" && titleEl ? titleEl.value : "",
      site_title: op === "update" && siteTitleEl ? siteTitleEl.value : "",
      system_title: op === "update" && systemTitleEl ? systemTitleEl.value : "",
      new_key: op === "update" && pageKeyEl ? pageKeyEl.value.trim() : "",
      boundary_id: op === "update" && boundIdEl ? boundIdEl.value.trim() : "",
      surface: op === "update" && boundSurfaceEl ? boundSurfaceEl.value : "",
      target: op === "update" && boundTargetEl ? boundTargetEl.value : "",
      meta_level: op === "update" && boundLevelEl && boundLevelEl.value !== ""
        ? parseInt(boundLevelEl.value, 10)
        : "",
      blocks: op === "update" ? readBlocks() : [],
      theme: op === "theme" ? readTheme() : {},
      scope: op === "theme" ? readThemeScope() : "site",
      delta: extra.delta,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Page update failed", "err");
      return;
    }
    applyPreview(data);
    saveDraft();
  }

  async function mutateSystemPart(op, extra) {
    extra = extra || {};
    const res = await http().post("/api/builder-core/meta/system-part", {
      code: codeEl.value,
      slug: slugEl.value,
      op: op,
      page_key: currentPageKey,
      delta: extra.delta,
      kind: extra.kind || "",
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Part update failed", "err");
      return;
    }
    applyPreview(data);
    saveDraft();
  }

  function readTheme() {
    function numberOrBlank(el) {
      if (!el || el.value === "") return "";
      const n = parseInt(el.value, 10);
      return Number.isFinite(n) ? n : el.value;
    }
    return {
      accent: themeAccentEl ? themeAccentEl.value.trim() : "",
      background: themeBgEl ? themeBgEl.value.trim() : "",
      color: themeFgEl ? themeFgEl.value.trim() : "",
      measure: numberOrBlank(themeMeasureEl),
      space: numberOrBlank(themeSpaceEl),
    };
  }

  function renderSimulation(simulation) {
    const emptyEl = document.getElementById("me-sim-empty");
    const liveEl = document.getElementById("me-sim-live");
    const events = (simulation && simulation.events) || [];
    const hasMachine = Boolean(simulation && (simulation.state || events.length));
    if (!hasMachine) {
      if (emptyEl) emptyEl.hidden = false;
      if (liveEl) liveEl.hidden = true;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    if (liveEl) liveEl.hidden = false;
    if (stateEl) stateEl.textContent = simulation.state || "";
    if (!eventBtns) return;
    eventBtns.innerHTML = "";
    events.forEach(function (event) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "me-btn me-btn--tiny";
      btn.textContent = event;
      btn.addEventListener("click", function () {
        stepOnce(event);
      });
      eventBtns.appendChild(btn);
    });
  }

  async function stepOnce(eventName) {
    const event = eventName || (eventsEl.value || "").split(",")[0].trim();
    if (!event) {
      setStatus("Event required", "err");
      return;
    }
    const res = await http().post("/api/builder-core/meta/step", {
      code: codeEl.value,
      event: event,
      slug: slugEl.value,
      page_key: currentPageKey,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      setStatus(data.error || "Step failed", "err");
      return;
    }
    applyPreview(data);
    setStatus("state → " + ((data.simulation && data.simulation.state) || ""), "ok");
    saveDraft();
  }

    async function instantiate() {
    const events = (eventsEl.value || "")
      .split(",")
      .map(function (item) {
        return item.trim();
      })
      .filter(Boolean);
    const res = await http().post("/api/builder-core/meta/instantiate", {
      slug: slugEl.value,
      code: codeEl.value,
      language: codeLang(),
      events: events,
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      window._zintriqInstantiateError = data.error || "Instantiate failed";
      setStatus(data.error || "Instantiate failed", "err");
      return;
    }
    window._zintriqInstantiateError = "";
    if (data.public_url && openEl) {
      openEl.setAttribute("href", data.public_url + "/home");
    }
    showArtifact(data);
    setStatus("Saved " + (data.public_url || data.slug || "artifact"), "ok");
  }

  async function produce() {
    const res = await http().post("/api/builder-core/meta/produce", {
      slug: slugEl.value || "made",
      prompt: (document.querySelector("[data-assistant-prompt]") || {}).value || "",
      kind: "",
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      window._zintriqInstantiateError = data.error || "Make failed";
      setStatus(data.error || "Make failed", "err");
      return;
    }
    window._zintriqInstantiateError = "";
    if (data.code) {
      codeEl.value = data.code;
      pushHistory();
    }
    if (data.slug) slugEl.value = data.slug;
    if (data.public_url && openEl) {
      openEl.setAttribute("href", data.public_url + (String(data.public_url).indexOf("/build/") === 0 ? "/home" : ""));
    }
    showArtifact(data);
    setStatus("Made " + (data.kind || "") + " → " + (data.public_url || data.slug || data.target || "artifact"), "ok");
    preview();
  }

  function showArtifact(data) {
    const box = document.getElementById("me-artifact");
    const meta = document.getElementById("me-artifact-meta");
    const empty = document.getElementById("me-artifact-empty");
    if (!box || !meta) return;
    const bits = data ? [data.target, data.slug, data.checksum].filter(Boolean) : [];
    if (!bits.length && !(data && data.public_url)) {
      if (empty) empty.hidden = false;
      meta.hidden = true;
      meta.textContent = "";
      return;
    }
    if (empty) empty.hidden = true;
    meta.hidden = false;
    meta.textContent = bits.join(" · ");
    const zip = Object.assign({}, data);
    if (!zip.zip_url && zip.target === "web_build" && zip.slug) {
      zip.zip_url = "/api/builder-core/meta/sites/" + zip.slug + "/zip";
    }
    showZip(zip);
    renderCanvasTree(data.canvas);
  }

  function renderCanvasTree(tree) {
    const el = document.getElementById("me-canvas-tree");
    if (!el) return;
    if (!tree || !tree.pages || !tree.pages.length) {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    function nodeHtml(node) {
      const kids = (node.children || []).map(nodeHtml).join("");
      return (
        "<li data-canvas-key=\"" +
        String(node.key || "").replace(/"/g, "") +
        "\">" +
        String(node.type || "node") +
        " · " +
        String(node.key || "") +
        (kids ? "<ul>" + kids + "</ul>" : "") +
        "</li>"
      );
    }
    el.hidden = false;
    el.innerHTML = "<p>Canvas</p><ul>" + tree.pages.map(nodeHtml).join("") + "</ul>";
  }

  async function loadExistingArtifact() {
    const slug = (slugEl && slugEl.value.trim()) || "";
    if (!slug) return;
    try {
      const res = await http().get("/api/builder-core/meta/artifacts/" + encodeURIComponent(slug));
      if (!res.ok) return;
      showArtifact(await res.json());
    } catch (_err) {
      /* none yet */
    }
  }

  function showZip(data) {
    if (data.public_url && openEl) {
      openEl.setAttribute("href", data.public_url + "/home");
    }
    if (zipEl && data.zip_url) {
      zipEl.hidden = false;
      zipEl.setAttribute("href", data.zip_url);
      zipEl.setAttribute("download", (data.slug || "site") + ".zip");
    } else if (zipEl) {
      zipEl.hidden = true;
      zipEl.removeAttribute("href");
    }
  }

  document.getElementById("me-preview").addEventListener("click", function () {
    preview();
  });
  const visualApply = document.getElementById("me-visual-apply");
  if (visualApply) {
    visualApply.addEventListener("click", function () {
      applyVisual();
    });
  }
  const uirApply = document.getElementById("me-uir-apply");
  if (uirApply) {
    uirApply.addEventListener("click", function () {
      applyUir();
    });
  }
  const undoEl = document.getElementById("me-undo");
  const redoEl = document.getElementById("me-redo");
  if (undoEl) {
    undoEl.addEventListener("click", function () {
      restoreHistory(-1);
    });
  }
  if (redoEl) {
    redoEl.addEventListener("click", function () {
      restoreHistory(1);
    });
  }
  if (window.ZintriqEngine) {
    window.ZintriqEngine.command.register("history.undo", function () {
      restoreHistory(-1);
    });
    window.ZintriqEngine.command.register("history.redo", function () {
      restoreHistory(1);
    });
    window.ZintriqEngine.command.register("meta.preview", function () {
      return preview();
    });
    window.ZintriqEngine.command.register("meta.instantiate", function () {
      return instantiate();
    });
    window.ZintriqEngine.command.register("meta.step", function () {
      return stepOnce();
    });
    window.ZintriqEngine.command.register("meta.space", function () {
      return http().get("/api/builder-core/meta/space");
    });
    window.ZintriqEngine.input.bind();
  } else {
    document.addEventListener("keydown", function (ev) {
      if (!(ev.metaKey || ev.ctrlKey) || ev.key.toLowerCase() !== "z") return;
      if (ev.target && (ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA")) return;
      ev.preventDefault();
      restoreHistory(ev.shiftKey ? 1 : -1);
    });
  }
  if (window.ZintriqWorkbench && window.ZintriqWorkbench.bindAssistant) {
    window.ZintriqWorkbench.bindAssistant({
      getCode: function () {
        return codeEl.value;
      },
      setCode: function (text) {
        codeEl.value = text;
        pushHistory();
      },
      onProduce: function (data, ok) {
        if (!ok || !data) return;
        if (data.slug) slugEl.value = data.slug;
        showArtifact(data);
        setStatus("Made " + (data.kind || "") + " → " + (data.public_url || data.slug || "artifact"), "ok");
        preview();
      },
    });
  }
  document.getElementById("me-instantiate").addEventListener("click", function () {
    instantiate();
  });
  const produceEl = document.getElementById("me-produce");
  if (produceEl) {
    produceEl.addEventListener("click", function () {
      produce();
    });
  }
  document.querySelectorAll("[data-export]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const kind = button.getAttribute("data-export") || "";
      const res = await http().post("/api/builder-core/meta/produce", {
        slug: slugEl.value || (kind === "webpage" ? "export-page" : kind === "app" ? "export-app" : "export-plugin"),
        kind: kind === "webpage" ? "page" : kind === "app" ? "engine" : "plugin",
        title: slugEl.value || kind,
        prompt: kind === "plugin" ? ((document.getElementById("da-stamp-form") || {}).value || "view") : "",
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        setStatus(data.error || "Export failed", "err");
        return;
      }
      if (data.pack) {
        setStatus("Plugin " + (data.pack.id || ""), "ok");
        window.location.href = "/app/community";
        return;
      }
      if (data.code) {
        codeEl.value = data.code;
        pushHistory();
      }
      if (data.slug) slugEl.value = data.slug;
      if (data.public_url && openEl) {
        openEl.setAttribute("href", data.public_url + (String(data.public_url).indexOf("/build/") === 0 ? "/home" : ""));
      }
      showArtifact(data);
      setStatus("Exported " + (data.kind || kind), "ok");
      if (data.zip_url) {
        const link = document.createElement("a");
        link.href = data.zip_url;
        link.setAttribute("download", (data.slug || "pack") + (kind === "app" ? ".zintriq-app.zip" : ".zip"));
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
      if (kind === "webpage" && data.studio) {
        window.location.href = data.studio;
      }
    });
  });
  const savePluginEl = document.getElementById("me-save-plugin");
  if (savePluginEl) {
    savePluginEl.addEventListener("click", async function () {
      const name = slugEl.value || "plugin";
      let targetId = lastPackId || "";
      let overwrite = false;
      try {
        const tip = await http().get("/api/plugin/stamp-target?name=" + encodeURIComponent(name));
        const tipData = await tip.json().catch(function () {
          return {};
        });
        if (tip.ok && tipData.id) {
          targetId = tipData.id;
          overwrite = !!tipData.overwrite;
        }
      } catch (_err) {
        /* ignore */
      }
      const label = overwrite ? "Overwrite " + targetId + "?" : "Save as " + (targetId || "community-…") + "?";
      if (!window.confirm(label)) return;
      const res = await http().post("/api/plugin/stamp", {
        name: name,
        form: "view",
        slug: slugEl.value,
        id: lastPackId || targetId || undefined,
        code: codeEl.value,
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        setStatus(data.error || "Save failed", "err");
        return;
      }
      if (data.code) codeEl.value = data.code;
      if (data.slug) slugEl.value = data.slug;
      lastStamped = codeEl.value;
      if (data.pack && data.pack.id) lastPackId = data.pack.id;
      setStatus((data.replaced ? "Updated " : "Saved ") + ((data.pack && data.pack.id) || "") + " — draft refreshed", "ok");
      if (data.pane && window.ZintriqEditorViews) window.ZintriqEditorViews.activate(data.pane);
      stampConsistency();
      if (window.zintriqDesktop && window.zintriqDesktop.setDirty) window.zintriqDesktop.setDirty(false);
      await preview();
    });
  }
  const importEl = document.getElementById("me-import");
  const importFileEl = document.getElementById("me-import-file");
  if (importEl && importFileEl) {
    importEl.addEventListener("click", function () {
      importFileEl.click();
    });
    importFileEl.addEventListener("change", async function () {
      const file = importFileEl.files && importFileEl.files[0];
      importFileEl.value = "";
      if (!file) return;
      const form = new FormData();
      form.append("slug", slugEl.value);
      form.append("site", file, file.name);
      const res = await http().post("/api/builder-core/meta/sites/import", form);
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        setStatus(data.error || "Import failed", "err");
        return;
      }
      if (data.slug) slugEl.value = data.slug;
      if (data.code) codeEl.value = data.code;
      showZip(data);
      await preview();
      setStatus("Imported " + (data.public_url || data.studio || data.slug || ""), "ok");
    });
  }
  const imageUploadEl = document.getElementById("me-image-upload");
  const imageFileEl = document.getElementById("me-image-file");
  if (imageUploadEl && imageFileEl) {
    imageUploadEl.addEventListener("click", function () {
      imageFileEl.click();
    });
    imageFileEl.addEventListener("change", async function () {
      const file = imageFileEl.files && imageFileEl.files[0];
      imageFileEl.value = "";
      if (!file) return;
      const slug = slugEl.value.trim();
      if (!slug) {
        setStatus("Slug required", "err");
        return;
      }
      const form = new FormData();
      form.append("file", file, file.name);
      const res = await http().post(
        "/api/builder-core/meta/sites/" + encodeURIComponent(slug) + "/assets",
        form
      );
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        setStatus(data.error || "Upload failed", "err");
        return;
      }
      const name = data.name || data.src || "";
      const blocks = readBlocks();
      blocks.push({ kind: "image", text: "", src: name });
      renderBlocks(blocks);
      renderAssets(data.assets);
      await mutateSitePage("update", currentPageKey);
      setStatus("Uploaded " + name, "ok");
    });
  }
  document.getElementById("me-step").addEventListener("click", function () {
    stepOnce();
  });
  if (copyEl) {
    copyEl.addEventListener("submit", function (ev) {
      ev.preventDefault();
      mutateSitePage("update", currentPageKey);
    });
    copyEl.querySelectorAll("[data-block-add]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const kind = btn.getAttribute("data-block-add") || "paragraph";
        const blocks = readBlocks();
        if (kind === "link") blocks.push({ kind: "link", text: "", to: "" });
        else if (kind === "list") blocks.push({ kind: "list", items: [] });
        else if (kind === "image") blocks.push({ kind: "image", text: "", src: "" });
        else if (kind === "heading") blocks.push({ kind: "heading", text: "", level: 2 });
        else if (kind === "code") blocks.push({ kind: "code", text: "" });
        else blocks.push({ kind: kind, text: "" });
        renderBlocks(blocks);
      });
    });
  }
  if (themeEl) {
    themeEl.addEventListener("submit", function (ev) {
      ev.preventDefault();
      mutateSitePage("theme", currentPageKey);
    });
    themeEl.querySelectorAll('input[name="me-theme-scope"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        fillTheme(lastPreview);
      });
    });
  }
  document.querySelectorAll("[data-insert]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const key = btn.getAttribute("data-insert");
      if (key === "space") {
        http()
          .get("/api/builder-core/meta/space")
          .then(function (res) {
            return res.json().then(function (data) {
              if (!res.ok || !data.code) {
                setStatus((data && data.error) || "Space not loaded", "err");
                return;
              }
              currentPageKey = "";
              codeEl.value = data.code;
              preview();
            });
          })
          .catch(function () {
            setStatus("Space not loaded", "err");
          });
        return;
      }
      if (FORMS[key]) {
        currentPageKey = "";
        codeEl.value = FORMS[key];
        preview();
      }
    });
  });
  codeEl.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      preview(currentPageKey, "code");
      stampConsistency();
    }, 400);
  });
  document.querySelectorAll('input[name="me-code-lang"]').forEach(function (el) {
    el.addEventListener("change", function () {
      preview(currentPageKey, "code");
    });
  });
  const uirLive = document.getElementById("me-uir");
  if (uirLive) {
    uirLive.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        applyUir(true);
      }, 400);
    });
  }
  const visualLive = document.getElementById("me-visual-props");
  if (visualLive) {
    visualLive.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(applyVisual, 400);
    });
  }
  function bindSurfaceLinks() {
    const slug = (slugEl.value || "").trim();
    const routes = {
      describe: "/studio/meta",
      simulate: "/studio/simulate",
      instantiate: "/studio/instantiate",
      space: "/studio/space",
    };
    let pane = document.body.getAttribute("data-editor-view") || "";
    try {
      pane = new URL(window.location.href).searchParams.get("pane") || pane;
    } catch (_err) {
      /* ignore */
    }
    document.querySelectorAll("[data-meta-href]").forEach(function (link) {
      const view = link.getAttribute("data-meta-href");
      const base = routes[view];
      if (!base) return;
      let href = base;
      if (slug && view !== "space") href = base + "/" + encodeURIComponent(slug);
      if (pane) href += "?pane=" + encodeURIComponent(pane);
      link.setAttribute("href", href);
    });
  }

  slugEl.addEventListener("input", function () {
    const slug = slugEl.value.trim() || "untitled";
    openEl.setAttribute("href", "/build/" + slug + "/home");
    bindSurfaceLinks();
    window.clearTimeout(timer);
    timer = window.setTimeout(preview, 400);
  });
  eventsEl.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(saveDraft, 400);
  });
  bindSurfaceLinks();
  if (window.ZintriqEditorViews && typeof window.ZintriqEditorViews.bindDocument === "function") {
    window.ZintriqEditorViews.bindDocument({
      visual: function () {
        return lastVisual;
      },
      preview: function () {
        return lastPreview;
      },
      applyVisual: applyVisualTree,
      applyCode: function (desc, opts) {
        opts = opts || {};
        let payload = desc;
        if (opts.merge && opts.field) {
          try {
            const current = JSON.parse(codeEl.value);
            if (current && current.form === "struct" && current.fields && typeof current.fields === "object" && !Array.isArray(current.fields)) {
              current.fields[opts.field] = desc;
              payload = current;
            } else {
              const fields = {};
              fields[opts.field] = desc;
              payload = { form: "struct", fields: fields };
            }
          } catch (_err) {
            const fields = {};
            fields[opts.field] = desc;
            payload = { form: "struct", fields: fields };
          }
        }
        const text = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
        currentPageKey = "";
        codeEl.value = text;
        preview("", "plugin");
      },
    });
  }
  function bindHardware() {
    const portEl = document.getElementById("me-hw-port");
    const logEl = document.getElementById("me-hw-log");
    const refreshBtn = document.getElementById("me-hw-refresh");
    const flashBtn = document.getElementById("me-hw-flash");
    const ssidEl = document.getElementById("me-hw-ssid");
    const passEl = document.getElementById("me-hw-pass");
    if (!portEl || !flashBtn) return;
    let jobTimer = 0;
    async function refreshPorts() {
      const res = await http().get("/api/builder-core/meta/hardware/ports");
      const data = await res.json().catch(function () {
        return {};
      });
      const ports = data.ports || [];
      const current = portEl.value;
      portEl.innerHTML = ports
        .map(function (item) {
          return "<option value=\"" + escapeHtml(item.path) + "\">" + escapeHtml(item.label || item.path) + "</option>";
        })
        .join("");
      if (!ports.length) {
        portEl.innerHTML = "<option value=\"\">No serial device</option>";
      } else if (current) {
        portEl.value = current;
      }
      if (ssidEl && data.wifi && data.wifi.ssid && !ssidEl.value) {
        ssidEl.value = data.wifi.ssid;
      }
    }
    async function pollJob(id) {
      const res = await http().get("/api/builder-core/meta/hardware/jobs/" + encodeURIComponent(id));
      const data = await res.json().catch(function () {
        return {};
      });
      if (logEl) logEl.textContent = data.log || "";
      if (data.status === "running" || data.status === "queued") {
        jobTimer = window.setTimeout(function () {
          pollJob(id);
        }, 800);
        return;
      }
      setStatus(data.status === "ok" ? "Flash complete" : data.error || "Flash finished", data.status === "ok" ? "ok" : "err");
    }
    refreshBtn && refreshBtn.addEventListener("click", refreshPorts);
    const busEl = document.getElementById("me-hw-bus");
    const busDevEl = document.getElementById("me-hw-bus-dev");
    const busLog = document.getElementById("me-hw-bus-log");
    const busRefresh = document.getElementById("me-hw-bus-refresh");
    const busPing = document.getElementById("me-hw-bus-ping");
    async function refreshBuses() {
      if (!busEl || !busDevEl) return;
      const res = await http().get("/api/builder-core/meta/hardware/buses");
      const data = await res.json().catch(function () {
        return {};
      });
      const kind = busEl.value || "usb";
      const rows = ((data.buses || {})[kind]) || [];
      busDevEl.innerHTML = rows
        .map(function (item) {
          return "<option value=\"" + escapeHtml(item.id) + "\">" + escapeHtml(item.label || item.id) + "</option>";
        })
        .join("") || "<option value=\"\">None</option>";
    }
    busRefresh && busRefresh.addEventListener("click", refreshBuses);
    busEl && busEl.addEventListener("change", refreshBuses);
    busPing && busPing.addEventListener("click", async function () {
      const res = await http().post("/api/builder-core/meta/hardware/buses/transfer", {
        kind: busEl ? busEl.value : "usb",
        device: busDevEl ? busDevEl.value : "",
        payload: "ping",
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (busLog) busLog.textContent = JSON.stringify(data);
    });
    let busSession = "";
    const busOpen = document.getElementById("me-hw-bus-open");
    const busWrite = document.getElementById("me-hw-bus-write");
    const busRead = document.getElementById("me-hw-bus-read");
    const busClose = document.getElementById("me-hw-bus-close");
    busOpen && busOpen.addEventListener("click", async function () {
      const res = await http().post("/api/builder-core/meta/hardware/buses/session", {
        kind: busEl ? busEl.value : "usb",
        device: busDevEl ? busDevEl.value : "",
      });
      const data = await res.json().catch(function () {
        return {};
      });
      busSession = data.session || "";
      if (busLog) busLog.textContent = JSON.stringify(data);
    });
    busWrite && busWrite.addEventListener("click", async function () {
      const res = await http().post("/api/builder-core/meta/hardware/buses/session/write", {
        session: busSession,
        payload: "ping",
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (busLog) busLog.textContent = JSON.stringify(data);
    });
    busRead && busRead.addEventListener("click", async function () {
      const res = await http().post("/api/builder-core/meta/hardware/buses/session/read", {
        session: busSession,
        n: 256,
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (busLog) busLog.textContent = JSON.stringify(data);
    });
    busClose && busClose.addEventListener("click", async function () {
      const res = await http().post("/api/builder-core/meta/hardware/buses/session/close", {
        session: busSession,
      });
      const data = await res.json().catch(function () {
        return {};
      });
      busSession = "";
      if (busLog) busLog.textContent = JSON.stringify(data);
    });
    refreshBuses();
    flashBtn.addEventListener("click", async function () {
      window.clearTimeout(jobTimer);
      const payload = {
        code: codeEl.value,
        language: codeLang(),
        port: portEl.value,
        slug: slugEl.value,
        wifi_ssid: ssidEl ? ssidEl.value : "",
      };
      if (passEl && passEl.value) payload.wifi_password = passEl.value;
      const res = await http().post("/api/builder-core/meta/hardware/flash", payload);
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        setStatus(data.error || "Flash failed", "err");
        if (logEl) logEl.textContent = data.error || "";
        return;
      }
      if (logEl) logEl.textContent = data.log || "queued";
      if (data.id) pollJob(data.id);
    });
    refreshPorts();
  }

  async function pushCollab() {
    const slug = (slugEl && slugEl.value.trim()) || "";
    if (!slug) return;
    await http().post("/api/builder-core/meta/collab", {
      slug: slug,
      code: codeEl.value,
      language: codeLang(),
    });
  }

  function startCollab() {
    const label = document.getElementById("me-collab");
    async function tick() {
      const slug = (slugEl && slugEl.value.trim()) || "";
      if (!slug) return;
      try {
        await pushCollab();
        if (window.zintriqDesktop && typeof window.zintriqDesktop.collabSync === "function") {
          await window.zintriqDesktop.collabSync(slug);
        }
        const res = await http().get("/api/builder-core/meta/collab/" + encodeURIComponent(slug));
        const data = await res.json().catch(function () {
          return {};
        });
        if (label && data.replica) {
          label.hidden = false;
          label.textContent = "Live · " + String(data.replica).slice(0, 8);
        }
        if (data.code && document.activeElement !== codeEl && data.code !== codeEl.value) {
          codeEl.value = data.code;
          preview(currentPageKey, "code");
        }
      } catch (_err) {
        /* offline */
      }
    }
    window.setInterval(tick, 1200);
    tick();
  }

  bindHardware();
  startCollab();
  preview();
})();
