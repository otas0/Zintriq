(() => {
  const boot = performance.now();
  const treeEl = document.getElementById("tree");
  const tabsEl = document.getElementById("tabs");
  const editor = document.getElementById("editor");
  const editorB = document.getElementById("editor-b");
  const hlA = document.getElementById("hl-a");
  const hlB = document.getElementById("hl-b");
  const empty = document.getElementById("empty");
  const statusPath = document.getElementById("status-path");
  const statusPerf = document.getElementById("status-perf");
  const statusDiag = document.getElementById("status-diag");
  const statusCursors = document.getElementById("status-cursors");
  const findBar = document.getElementById("find-bar");
  const findInput = document.getElementById("find-input");
  const panel = document.getElementById("panel");
  const panelTitle = document.getElementById("panel-title");
  const panelBody = document.getElementById("panel-body");
  const appEl = document.getElementById("app");
  const editorsEl = document.getElementById("editors");
  const paneB = document.getElementById("pane-b");
  const splitHandle = document.getElementById("split-handle");
  const completionEl = document.getElementById("completion");
  const cursorLayer = document.getElementById("cursor-layer");
  const inlineValuesEl = document.getElementById("inline-values");
  const hoverTip = document.getElementById("hover-tip");
  const foldGutter = document.getElementById("fold-gutter");
  const minimap = document.getElementById("minimap");
  const sidebar = document.getElementById("sidebar");
  const sidebarHandle = document.getElementById("sidebar-handle");
  const panelHandle = document.getElementById("panel-handle");
  const bottomDock = document.getElementById("bottom-dock");
  const bottomBody = document.getElementById("bottom-body");
  const bottomHandle = document.getElementById("bottom-handle");
  const workArea = document.getElementById("work-area");
  const diffOverlay = document.getElementById("diff-overlay");
  const diffFiles = document.getElementById("diff-files");
  const diffBefore = document.getElementById("diff-before");
  const diffAfter = document.getElementById("diff-after");
  const diffTitle = document.getElementById("diff-title");
  const btnShowSidebar = document.getElementById("btn-show-sidebar");

  /** @type {Map<string, {path:string, text:string, saved:string, language:string, foldedStarts:Set<number>}>} */
  const buffers = new Map();
  let activePath = "";
  let secondaryPath = "";
  let cwd = "";
  let panelMode = "";
  let splitRatio = 0.55;
  let splitEnabled = false;
  let sidebarW = 220;
  let panelW = 360;
  let bottomH = 220;
  let sidebarHidden = false;
  let bottomOpen = false;
  let diffChangeId = "";
  let diffSelectedPath = "";
  /** @type {Record<string, {line:number, condition?:string, hitCondition?:string, logMessage?:string, enabled?:boolean, group?:string}[]>} */
  let breakpoints = {};
  let debugPoll = 0;
  let debugStoppedLine = 0;
  let debugStoppedPath = "";
  let debugPaused = false;
  let activeDebugSessionId = "";
  let selectedDebugFrameId = null;
  /** @type {any[]} */
  let lastInlineValues = [];
  /** @type {Record<string, {hits:number[], misses:number[], branches:any[]}>} */
  let coverageByFile = {};
  /** @type {Record<string, boolean>} */
  let breakpointGroups = {};
  let debugLayout = {
    showStack: true,
    showVars: true,
    showWatches: true,
    showConsole: true,
  };
  let debugLayoutSaveTimer = 0;

  function bpLinesFor(path) {
    const list = breakpoints[path] || [];
    if (!list.length) return [];
    if (typeof list[0] === "number") return list;
    return list.map((b) => b.line);
  }

  function bpMeta(path, line) {
    const list = breakpoints[path] || [];
    return list.find((b) => (typeof b === "number" ? b === line : b.line === line));
  }

  function wordAtOffset(text, offset) {
    const re = /[A-Za-z_$][\w$]*/g;
    let m;
    while ((m = re.exec(text))) {
      if (offset >= m.index && offset <= m.index + m[0].length) return m[0];
    }
    return "";
  }
  let diagnoseTimer = 0;
  let completeTimer = 0;
  let hoverTimer = 0;
  /** @type {number[]} caret offsets for multi-cursor */
  let cursors = [];
  let completionItems = [];
  let completionIndex = 0;
  let ptyId = "";
  let ptyPoll = 0;
  let ptyBackend = "";
  /** @type {any} */
  let xtermInst = null;
  /** @type {any} */
  let xtermFit = null;
  /** @type {ResizeObserver|null} */
  let xtermRo = null;
  /** @type {(() => void)|null} */
  let ptyUnsubData = null;
  /** @type {(() => void)|null} */
  let ptyUnsubExit = null;
  /** @type {any[]} */
  let lastDiags = [];
  let charWidth = 8;
  const lineHeight = 20.15;

  function measureCharWidth() {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return 8;
    ctx.font = '13px "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace';
    return ctx.measureText("M").width || 8;
  }
  charWidth = measureCharWidth();

  async function api(method, url, body) {
    const desktop = window.zintriqDesktop;
    if (desktop && typeof desktop.http === "function") {
      return desktop.http({ method, path: url, body });
    }
    const token = desktop && (await desktop.getToken());
    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Zintriq-Desktop-Token": token } : {}),
      },
      body: body == null ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || data.message || res.statusText);
    return data;
  }

  function setStatus(path, extra) {
    statusPath.textContent = path || "Ready";
    if (extra != null) statusPerf.textContent = extra;
  }

  function paint(ta, hl, language) {
    if (!window.ZintriqSyntax) {
      hl.textContent = ta.value;
      return;
    }
    hl.innerHTML = window.ZintriqSyntax.paint(ta.value, language || "plaintext");
    hl.scrollTop = ta.scrollTop;
    hl.scrollLeft = ta.scrollLeft;
  }

  function showEditor(on) {
    editor.classList.toggle("hidden", !on);
    empty.classList.toggle("hidden", on);
  }

  function applyShellLayout() {
    document.documentElement.style.setProperty("--sidebar-w", sidebarHidden ? "0px" : `${sidebarW}px`);
    document.documentElement.style.setProperty("--panel-w", panel.classList.contains("hidden") ? "0px" : `${panelW}px`);
    document.documentElement.style.setProperty("--bottom-h", `${bottomH}px`);
    appEl.classList.toggle("no-sidebar", sidebarHidden);
    appEl.classList.toggle("no-panel", panel.classList.contains("hidden"));
    sidebar.classList.toggle("hidden", sidebarHidden);
    if (btnShowSidebar) btnShowSidebar.classList.toggle("hidden", !sidebarHidden);
    bottomDock.classList.toggle("hidden", !bottomOpen);
    bottomHandle.style.display = bottomOpen ? "" : "none";
  }

  function applySplit() {
    editorsEl.classList.toggle("single", !splitEnabled);
    editorsEl.classList.toggle("split-on", splitEnabled);
    paneB.classList.toggle("hidden", !splitEnabled);
    if (splitEnabled) {
      const a = Math.max(0.2, Math.min(0.8, splitRatio));
      editorsEl.style.gridTemplateColumns = `${a}fr 4px ${1 - a}fr`;
    } else {
      editorsEl.style.gridTemplateColumns = "1fr";
    }
    persistLayout();
  }

  function persistLayout() {
    const layout = {
      sidebarW,
      panelW,
      bottomH,
      sidebarHidden,
      bottomOpen,
      panelOpen: !panel.classList.contains("hidden"),
      panelMode,
      splitEnabled,
      splitRatio,
      activePath,
      secondaryPath,
      debugLayout,
    };
    localStorage.setItem("zintriq.layout", JSON.stringify(layout));
    if (window.zintriqDesktop && typeof window.zintriqDesktop.saveLayout === "function") {
      window.zintriqDesktop.saveLayout(layout);
    }
  }

  function scheduleDebugLayoutPersist() {
    clearTimeout(debugLayoutSaveTimer);
    debugLayoutSaveTimer = setTimeout(() => {
      persistLayout();
      api("POST", "/api/debug/layout", { layout: debugLayout }).catch(() => {});
    }, 200);
  }

  function restoreLayout(opts) {
    const fresh = opts && opts.freshStart;
    let layout = null;
    try {
      layout = JSON.parse(localStorage.getItem("zintriq.layout") || "null");
    } catch {
      layout = null;
    }
    if (!layout || fresh) {
      bottomOpen = false;
      sidebarHidden = false;
      panel.classList.add("hidden");
      panelBody.innerHTML = "";
      panelMode = "";
      applyShellLayout();
      applySplit();
      return;
    }
    if (layout.sidebarW) sidebarW = Math.max(140, Number(layout.sidebarW) || 220);
    if (layout.panelW) panelW = Math.max(240, Number(layout.panelW) || 360);
    if (layout.bottomH) bottomH = Math.max(120, Number(layout.bottomH) || 220);
    sidebarHidden = Boolean(layout.sidebarHidden);
    bottomOpen = Boolean(layout.bottomOpen);
    if (layout.splitRatio) splitRatio = Number(layout.splitRatio) || 0.55;
    splitEnabled = Boolean(layout.splitEnabled);
    if (layout.debugLayout && typeof layout.debugLayout === "object") {
      debugLayout = { ...debugLayout, ...layout.debugLayout };
    }
    applyShellLayout();
    applySplit();
    if (bottomOpen) renderTermPanel();
    if (layout.panelOpen && layout.panelMode && layout.panelMode !== "term") {
      openPanel(layout.panelMode);
    }
    // Avoid the "empty black panel + empty term dock" first-impression mess
    if (!panelBody.childElementCount) {
      panel.classList.add("hidden");
      panelMode = "";
      applyShellLayout();
    }
  }

  function openBottom() {
    bottomOpen = true;
    applyShellLayout();
    renderTermPanel();
    persistLayout();
  }

  function closeBottom() {
    bottomOpen = false;
    disposeXterm();
    applyShellLayout();
    persistLayout();
  }

  function bufFolds(buf) {
    if (!buf.foldedStarts) buf.foldedStarts = new Set();
    return buf.foldedStarts;
  }

  function syncEditorFromBuf(buf) {
    if (!buf) return;
    const Fold = window.ZintriqFold;
    const folds = bufFolds(buf);
    if (Fold && folds.size) {
      const view = Fold.applyFolds(buf.text, folds);
      editor.value = view.text;
    } else {
      editor.value = buf.text;
    }
    paint(editor, hlA, buf.language);
    renderFoldGutter(buf);
    paintMinimap(buf);
    paintCursorLayer();
  }

  function expandAllFolds(buf) {
    if (!buf) return;
    bufFolds(buf).clear();
    editor.value = buf.text;
  }

  function ensureUnfoldedForEdit() {
    if (!activePath || !buffers.has(activePath)) return;
    const buf = buffers.get(activePath);
    if (bufFolds(buf).size) {
      expandAllFolds(buf);
      paint(editor, hlA, buf.language);
      renderFoldGutter(buf);
      paintMinimap(buf);
    }
  }

  function renderFoldGutter(buf) {
    if (!foldGutter || !window.ZintriqFold || !buf) {
      if (foldGutter) foldGutter.innerHTML = "";
      return;
    }
    const folds = window.ZintriqFold.computeFolds(buf.text);
    const active = bufFolds(buf);
    const byStart = new Map(folds.map((f) => [f.start, f]));
    const display = window.ZintriqFold.applyFolds(buf.text, active);
    foldGutter.innerHTML = "";
    foldGutter.style.paddingTop = "14px";
    foldGutter.scrollTop = editor.scrollTop;
    const seen = new Set();
    const bpLines = new Set(bpLinesFor(buf.path));
    for (let di = 0; di < display.map.length; di++) {
      const src = display.map[di];
      const line1 = src + 1;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "fold-btn";
      const fold = byStart.get(src);
      const meta = bpMeta(buf.path, line1);
      const hasCond = meta && meta.condition;
      const hasHit = meta && meta.hitCondition;
      const hasLog = meta && meta.logMessage;
      if (fold && !seen.has(src)) {
        seen.add(src);
        btn.textContent = active.has(src) ? "▶" : "▼";
        btn.title = active.has(src)
          ? "Unfold"
          : "Fold · Alt+BP · Shift=cond · Ctrl/Cmd=hit · Alt+Shift=logpoint";
        btn.onclick = (e) => {
          e.preventDefault();
          if (e.shiftKey && (e.altKey || e.metaKey)) {
            editBreakpointLogMessage(line1);
            return;
          }
          if (e.shiftKey) {
            editBreakpointCondition(line1);
            return;
          }
          if (e.metaKey || e.ctrlKey) {
            editBreakpointHitCount(line1);
            return;
          }
          if (e.altKey) {
            toggleBreakpointAt(line1);
            return;
          }
          if (active.has(src)) active.delete(src);
          else active.add(src);
          syncEditorFromBuf(buf);
        };
      } else {
        btn.classList.add("empty");
        btn.textContent = "·";
        const bits = [];
        if (hasCond) bits.push(`if ${meta.condition}`);
        if (hasHit) bits.push(`hit ${meta.hitCondition}`);
        if (hasLog) bits.push(`log ${meta.logMessage}`);
        btn.title = bits.length
          ? `BP ${bits.join(" · ")} · click to edit`
          : "Toggle BP · right-click / long-press for editor";
        btn.onclick = (e) => {
          e.preventDefault();
          if (e.shiftKey && e.altKey) editBreakpointLogMessage(line1);
          else if (e.shiftKey) editBreakpointCondition(line1);
          else if (e.metaKey || e.ctrlKey) editBreakpointHitCount(line1);
          else if (bpLines.has(line1) && !e.altKey) openBreakpointPopup(line1, btn);
          else toggleBreakpointAt(line1);
        };
        btn.oncontextmenu = (e) => {
          e.preventDefault();
          openBreakpointPopup(line1, btn);
        };
      }
      if (bpLines.has(line1)) btn.classList.add("bp");
      if (meta && meta.enabled === false) btn.classList.add("bp-disabled");
      if (hasCond) btn.classList.add("bp-cond");
      if (hasHit) btn.classList.add("bp-hit");
      if (hasLog) btn.classList.add("bp-log");
      const heat = (window.__bpHeat && window.__bpHeat[buf.path]) || {};
      const heatLv = heat[String(line1)];
      if (heatLv) btn.classList.add("bp-heat-" + heatLv);
      const cov = coverageByFile[buf.path] || {};
      const hits = cov.hits || [];
      const misses = cov.misses || [];
      const branchLines = new Set((cov.branches || []).map((b) => b.line));
      if (hits.includes(line1)) btn.classList.add("cov-hit");
      if (misses.includes(line1)) btn.classList.add("cov-miss");
      if (branchLines.has(line1)) btn.classList.add("cov-branch");
      if (debugStoppedPath === buf.path && debugStoppedLine === line1) btn.classList.add("bp-current");
      foldGutter.appendChild(btn);
    }
  }

  function closeBreakpointPopup() {
    document.querySelectorAll(".bp-inline-popup").forEach((el) => el.remove());
  }

  function openBreakpointPopup(line1, anchor) {
    closeBreakpointPopup();
    if (!activePath) return;
    const meta = bpMeta(activePath, line1) || {
      line: line1,
      condition: "",
      hitCondition: "",
      logMessage: "",
      enabled: true,
      group: "default",
    };
    const pop = document.createElement("div");
    pop.className = "bp-inline-popup";
    const title = document.createElement("div");
    title.className = "meta";
    title.textContent = `Breakpoint · L${line1}`;
    const cond = document.createElement("input");
    cond.placeholder = "condition";
    cond.value = meta.condition || "";
    const hit = document.createElement("input");
    hit.placeholder = "hit condition";
    hit.value = meta.hitCondition || "";
    const log = document.createElement("input");
    log.placeholder = "log message";
    log.value = meta.logMessage || "";
    const colIn = document.createElement("input");
    colIn.type = "number";
    colIn.min = "0";
    colIn.placeholder = "column (0 = whole line)";
    colIn.value = meta.column != null ? String(meta.column) : "";
    const colPick = document.createElement("select");
    colPick.innerHTML = `<option value="">column…</option>`;
    api("POST", "/api/debug/breakpointLocations", {
      path: activePath,
      line: line1,
      ...(activeDebugSessionId ? { sessionId: activeDebugSessionId } : {}),
    })
      .then((res) => {
        for (const loc of res.locations || []) {
          const opt = document.createElement("option");
          opt.value = String(loc.column || 1);
          opt.textContent = `col ${loc.column}`;
          colPick.appendChild(opt);
        }
      })
      .catch(() => {});
    colPick.onchange = () => {
      if (colPick.value) colIn.value = colPick.value;
    };
    const group = document.createElement("input");
    group.placeholder = "group";
    group.value = meta.group || "default";
    const en = document.createElement("input");
    en.type = "checkbox";
    en.checked = meta.enabled !== false;
    const enLab = document.createElement("label");
    enLab.append(en, document.createTextNode(" enabled"));
    const suggestBtn = document.createElement("button");
    suggestBtn.textContent = "AI suggest";
    suggestBtn.type = "button";
    const llmBtn = document.createElement("button");
    llmBtn.textContent = "LLM";
    llmBtn.type = "button";
    const suggestBox = document.createElement("div");
    suggestBox.className = "debug-console-complete";
    const fillSuggest = (res) => {
      suggestBox.innerHTML = "";
      const note = document.createElement("div");
      note.className = "meta";
      note.textContent = res.provider || "";
      suggestBox.appendChild(note);
      for (const s of res.suggestions || []) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = `${s.condition} — ${s.reason}`;
        b.onclick = () => {
          cond.value = s.condition;
        };
        suggestBox.appendChild(b);
      }
    };
    suggestBtn.onclick = async () => {
      try {
        fillSuggest(
          await api("POST", "/api/debug/suggestCondition", { path: activePath, line: line1 })
        );
      } catch (e) {
        suggestBox.textContent = String(e.message || e);
      }
    };
    llmBtn.onclick = async () => {
      try {
        fillSuggest(
          await api("POST", "/api/debug/suggestCondition/llm", {
            path: activePath,
            line: line1,
            allowNetwork: true,
          })
        );
      } catch (e) {
        suggestBox.textContent = String(e.message || e);
      }
    };
    const row = document.createElement("div");
    row.className = "row";
    const save = document.createElement("button");
    save.textContent = "Save";
    save.onclick = async () => {
      try {
        if (!bpLinesFor(activePath).includes(line1)) {
          await api("POST", "/api/debug/breakpoints/toggle", { path: activePath, line: line1 });
        }
        let data = await api("POST", "/api/debug/breakpoints/condition", {
          path: activePath,
          line: line1,
          condition: cond.value,
        });
        data = await api("POST", "/api/debug/breakpoints/hit", {
          path: activePath,
          line: line1,
          hitCondition: hit.value,
        });
        data = await api("POST", "/api/debug/breakpoints/log", {
          path: activePath,
          line: line1,
          logMessage: log.value,
        });
        data = await api("POST", "/api/debug/breakpoints/meta", {
          path: activePath,
          line: line1,
          enabled: en.checked,
          group: group.value || "default",
        });
        if (colIn.value) {
          data = await api("POST", "/api/debug/breakpoints/column", {
            path: activePath,
            line: line1,
            column: Number(colIn.value) || null,
          });
        }
        breakpoints[activePath] = data.breakpoints || [];
        if (buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
        closeBreakpointPopup();
      } catch (e) {
        alert(e.message || e);
      }
    };
    const rm = document.createElement("button");
    rm.textContent = "Remove";
    rm.onclick = async () => {
      await toggleBreakpointAt(line1);
      closeBreakpointPopup();
    };
    const cancel = document.createElement("button");
    cancel.textContent = "Close";
    cancel.onclick = () => closeBreakpointPopup();
    row.append(save, rm, cancel, suggestBtn, llmBtn);
    pop.append(title, cond, hit, log, colIn, colPick, group, enLab, suggestBox, row);
    document.body.appendChild(pop);
    const rect = (anchor || foldGutter).getBoundingClientRect();
    pop.style.top = Math.min(window.innerHeight - 280, rect.top) + "px";
    pop.style.left = Math.min(window.innerWidth - 320, rect.right + 6) + "px";
  }

  function applyCoverageFiles(files) {
    coverageByFile = {};
    for (const [p, info] of Object.entries(files || {})) {
      coverageByFile[p] = {
        hits: (info && info.hits) || [],
        misses: (info && info.misses) || [],
        branches: (info && info.branches) || [],
      };
    }
    if (activePath && buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
  }

  async function toggleBreakpointAt(line1) {
    if (!activePath) return;
    try {
      const data = await api("POST", "/api/debug/breakpoints/toggle", {
        path: activePath,
        line: line1,
      });
      breakpoints[activePath] = data.breakpoints || (data.lines || []).map((line) => ({ line }));
      if (buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
    } catch (e) {
      setStatus(activePath, String(e.message || e));
    }
  }

  function promptDebugExpression(placeholder, existing, onSave, opts) {
    const options = opts || {};
    const overlay = document.createElement("div");
    overlay.className = "debug-cond-overlay";
    const input = document.createElement("input");
    input.type = "text";
    input.value = existing || "";
    input.placeholder = placeholder;
    const historyEl = document.createElement("div");
    historyEl.className = "debug-console-complete";
    const suggest = document.createElement("div");
    suggest.className = "debug-console-complete";
    const ok = document.createElement("button");
    ok.textContent = "Set";
    const cancel = document.createElement("button");
    cancel.textContent = "Cancel";
    overlay.append(input, historyEl, suggest, ok, cancel);
    document.body.appendChild(overlay);
    input.focus();
    if (options.history) {
      api("GET", "/api/debug/conditions/history")
        .then((res) => {
          for (const h of (res.history || []).slice(0, 8)) {
            const b = document.createElement("button");
            b.type = "button";
            b.textContent = h;
            b.title = "History";
            b.onclick = () => {
              input.value = h;
              input.focus();
            };
            historyEl.appendChild(b);
          }
        })
        .catch(() => {});
    }
    let t = 0;
    const refreshSuggest = async () => {
      suggest.innerHTML = "";
      if (!input.value) return;
      try {
        const res = await api("POST", "/api/debug/completions", {
          text: input.value,
          column: input.value.length + 1,
          ...(activeDebugSessionId ? { sessionId: activeDebugSessionId } : {}),
          ...(selectedDebugFrameId != null ? { frameId: selectedDebugFrameId } : {}),
        });
        for (const it of (res.items || []).slice(0, 10)) {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = it.label || it.text || it;
          b.onclick = () => {
            const label = it.text || it.label || "";
            input.value = input.value.replace(/[\w$]*$/, "") + label;
            suggest.innerHTML = "";
            input.focus();
          };
          suggest.appendChild(b);
        }
      } catch {
        /* ignore */
      }
    };
    input.oninput = () => {
      clearTimeout(t);
      t = setTimeout(refreshSuggest, 180);
    };
    const finish = async (save) => {
      overlay.remove();
      if (!save) return;
      await onSave(input.value);
    };
    ok.onclick = () => finish(true);
    cancel.onclick = () => finish(false);
    input.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        finish(true);
      }
      if (e.key === "Escape") finish(false);
    };
  }

  async function editBreakpointCondition(line1) {
    if (!activePath) return;
    const cur = bpMeta(activePath, line1);
    promptDebugExpression(
      `Condition for line ${line1} (empty = always)`,
      cur && cur.condition ? cur.condition : "",
      async (cond) => {
      try {
        if (!bpLinesFor(activePath).includes(line1)) {
          await api("POST", "/api/debug/breakpoints/toggle", { path: activePath, line: line1 });
        }
        const data = await api("POST", "/api/debug/breakpoints/condition", {
          path: activePath,
          line: line1,
          condition: cond,
        });
        breakpoints[activePath] = data.breakpoints || [];
        if (buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
      } catch (e) {
        alert(e.message || e);
      }
    },
      { history: true }
    );
  }

  async function editBreakpointHitCount(line1) {
    if (!activePath) return;
    const cur = bpMeta(activePath, line1);
    promptDebugExpression(
      `Hit count for line ${line1} (e.g. 5, >=3, %2)`,
      cur && cur.hitCondition ? cur.hitCondition : "",
      async (hit) => {
        try {
          if (!bpLinesFor(activePath).includes(line1)) {
            await api("POST", "/api/debug/breakpoints/toggle", { path: activePath, line: line1 });
          }
          const data = await api("POST", "/api/debug/breakpoints/hit", {
            path: activePath,
            line: line1,
            hitCondition: hit,
          });
          breakpoints[activePath] = data.breakpoints || [];
          if (buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
        } catch (e) {
          alert(e.message || e);
        }
      }
    );
  }

  async function editBreakpointLogMessage(line1) {
    if (!activePath) return;
    const cur = bpMeta(activePath, line1);
    promptDebugExpression(
      `Logpoint for line ${line1} (use {expr})`,
      cur && cur.logMessage ? cur.logMessage : "",
      async (msg) => {
        try {
          if (!bpLinesFor(activePath).includes(line1)) {
            await api("POST", "/api/debug/breakpoints/toggle", { path: activePath, line: line1 });
          }
          const data = await api("POST", "/api/debug/breakpoints/log", {
            path: activePath,
            line: line1,
            logMessage: msg,
          });
          breakpoints[activePath] = data.breakpoints || [];
          if (buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
        } catch (e) {
          alert(e.message || e);
        }
      }
    );
  }

  function paintMinimap(buf) {
    if (!minimap || !buf) return;
    const cssH = Math.max(40, editorsEl.clientHeight || 400);
    const dpr = window.devicePixelRatio || 1;
    const w = 72;
    minimap.width = Math.floor(w * dpr);
    minimap.height = Math.floor(cssH * dpr);
    minimap.style.height = `${cssH}px`;
    const ctx = minimap.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#12141a";
    ctx.fillRect(0, 0, w, cssH);
    const lines = buf.text.split("\n");
    const rowH = Math.max(1, cssH / Math.max(lines.length, 1));
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trim = line.trim();
      if (!trim) continue;
      let color = "#3a4252";
      if (/^\s*(\/\/|#|\/\*|\*)/.test(line)) color = "#5c6370";
      else if (/["'`]/.test(line)) color = "#4a6a48";
      else if (/\b(def|class|function|const|let|return|import)\b/.test(line)) color = "#6a4a7a";
      else if (/\d/.test(line)) color = "#6a5538";
      const indent = (line.match(/^\s*/) || [""])[0].length;
      const x = 4 + Math.min(20, indent);
      const barW = Math.min(w - x - 4, 8 + Math.min(40, trim.length));
      ctx.fillStyle = color;
      ctx.fillRect(x, i * rowH, barW, Math.max(1, rowH * 0.85));
    }
    // viewport
    const total = editor.scrollHeight || 1;
    const view = editor.clientHeight || 1;
    const top = (editor.scrollTop / total) * cssH;
    const vh = (view / total) * cssH;
    ctx.fillStyle = "rgba(108,178,255,0.15)";
    ctx.fillRect(0, top, w, Math.max(8, vh));
  }

  function renderTabs() {
    tabsEl.innerHTML = "";
    for (const [path, buf] of buffers) {
      const tab = document.createElement("div");
      tab.className =
        "tab" +
        (path === activePath ? " active" : "") +
        (buf.text !== buf.saved ? " dirty" : "");
      tab.title = path + (path === secondaryPath ? " (split)" : "");
      const label = document.createElement("span");
      label.textContent = path.split("/").pop() || path;
      const close = document.createElement("button");
      close.type = "button";
      close.className = "close";
      close.textContent = "×";
      close.addEventListener("click", (e) => {
        e.stopPropagation();
        closeTab(path);
      });
      tab.append(label, close);
      tab.addEventListener("click", () => activate(path));
      tab.addEventListener("dblclick", () => {
        secondaryPath = path;
        splitEnabled = true;
        syncSecondary();
        applySplit();
      });
      tabsEl.appendChild(tab);
    }
  }

  function activate(path) {
    const buf = buffers.get(path);
    if (!buf) return;
    if (activePath && buffers.has(activePath) && activePath !== path) {
      const prev = buffers.get(activePath);
      if (!bufFolds(prev).size) prev.text = editor.value;
    }
    activePath = path;
    syncEditorFromBuf(buf);
    showEditor(true);
    setStatus(path);
    renderTabs();
    scheduleDiagnose();
    persistLayout();
  }

  function syncSecondary() {
    if (!splitEnabled || !secondaryPath || !buffers.has(secondaryPath)) return;
    const buf = buffers.get(secondaryPath);
    editorB.value = buf.text;
    paint(editorB, hlB, buf.language);
  }

  function closeTab(path) {
    buffers.delete(path);
    if (secondaryPath === path) secondaryPath = "";
    if (activePath === path) {
      activePath = "";
      const next = buffers.keys().next();
      if (!next.done) activate(next.value);
      else {
        editor.value = "";
        hlA.textContent = "";
        showEditor(false);
        setStatus("Ready");
      }
    }
    renderTabs();
    syncSecondary();
  }

  function joinPath(base, name) {
    const a = (base || "").replace(/\\/g, "/").replace(/\/+$/, "");
    const b = (name || "").replace(/\\/g, "/").replace(/^\/+/, "");
    if (!a) return b;
    if (!b) return a;
    return `${a}/${b}`;
  }

  function promptName(title, placeholder) {
    const raw = window.prompt(title, placeholder || "");
    if (raw == null) return null;
    const name = String(raw).trim().replace(/\\/g, "/");
    if (!name || name.includes("..") || name.startsWith("/")) {
      alert("Invalid name");
      return null;
    }
    return name;
  }

  async function createNewFile(suggested) {
    const name = promptName("New file name (relative to current folder)", suggested || "untitled.py");
    if (!name) return;
    const path = joinPath(cwd, name);
    try {
      await api("POST", "/api/fs/create", { path, text: "" });
      await loadTree(cwd);
      await openFile(path);
    } catch (err) {
      alert(err.message || err);
    }
  }

  async function createNewFolder() {
    const name = promptName("New folder name", "src");
    if (!name) return;
    const path = joinPath(cwd, name);
    try {
      await api("POST", "/api/fs/mkdir", { path });
      await loadTree(cwd);
    } catch (err) {
      alert(err.message || err);
    }
  }

  function showOnboarding(show) {
    const el = document.getElementById("onboarding");
    if (!el) return;
    el.classList.toggle("hidden", !show);
  }

  async function completeOnboarding(openHello) {
    try {
      await api("POST", "/api/onboarding/complete", { completed: true });
    } catch {
      /* ignore */
    }
    showOnboarding(false);
    if (openHello) {
      try {
        await openFile("examples/hello.py");
      } catch {
        try {
          await openFile("WELCOME.md");
        } catch {
          /* ignore */
        }
      }
    }
  }

  async function loadTree(path) {
    cwd = path || "";
    const data = await api("GET", `/api/fs/list?path=${encodeURIComponent(cwd)}`);
    treeEl.innerHTML = "";
    if (cwd) {
      const up = document.createElement("li");
      up.className = "dir";
      up.textContent = "..";
      up.addEventListener("click", () => {
        const parts = cwd.split("/").filter(Boolean);
        parts.pop();
        loadTree(parts.join("/"));
      });
      treeEl.appendChild(up);
    }
    const entries = data.entries || [];
    if (!entries.length) {
      const emptyLi = document.createElement("li");
      emptyLi.className = "tree-empty";
      emptyLi.innerHTML =
        "<div>This folder is empty.</div>" +
        '<div class="tree-empty-actions">' +
        '<button type="button" class="tree-btn" data-act="file">New File</button>' +
        '<button type="button" class="tree-btn" data-act="folder">New Folder</button>' +
        "</div>";
      emptyLi.querySelector('[data-act="file"]').addEventListener("click", (e) => {
        e.stopPropagation();
        createNewFile();
      });
      emptyLi.querySelector('[data-act="folder"]').addEventListener("click", (e) => {
        e.stopPropagation();
        createNewFolder();
      });
      treeEl.appendChild(emptyLi);
      return data;
    }
    for (const entry of entries) {
      const li = document.createElement("li");
      li.className = entry.dir ? "dir" : "";
      if (entry.path === activePath) li.classList.add("active");
      li.textContent = (entry.dir ? "▸ " : "") + entry.name;
      li.title = entry.path;
      li.addEventListener("click", () => {
        if (entry.dir) loadTree(entry.path);
        else openFile(entry.path);
      });
      li.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        if (!window.confirm(`Delete ${entry.path}?`)) return;
        api("POST", "/api/fs/delete", { path: entry.path })
          .then(() => {
            if (activePath === entry.path) closeTab(entry.path);
            return loadTree(cwd);
          })
          .catch((err) => alert(err.message || err));
      });
      treeEl.appendChild(li);
    }
    return data;
  }

  async function openFile(path) {
    if (buffers.has(path)) {
      activate(path);
      return;
    }
    const t0 = performance.now();
    const data = await api("GET", `/api/fs/read?path=${encodeURIComponent(path)}`);
    buffers.set(path, {
      path,
      text: data.text,
      saved: data.text,
      language: data.language || "plaintext",
      foldedStarts: new Set(),
    });
    activate(path);
    setStatus(path, `open ${Math.round(performance.now() - t0)}ms`);
  }

  async function saveActive() {
    if (!activePath) return;
    const buf = buffers.get(activePath);
    if (!buf) return;
    if (!bufFolds(buf).size) buf.text = editor.value;
    const t0 = performance.now();
    await api("PUT", "/api/fs/write", { path: activePath, text: buf.text });
    buf.saved = buf.text;
    renderTabs();
    setStatus(activePath, `saved ${Math.round(performance.now() - t0)}ms`);
    scheduleDiagnose();
  }

  function scheduleDiagnose() {
    clearTimeout(diagnoseTimer);
    diagnoseTimer = setTimeout(runDiagnose, 450);
  }

  async function runDiagnose() {
    if (!activePath) {
      statusDiag.textContent = "";
      return;
    }
    try {
      const data = await api("POST", "/api/lsp/diagnose", {
        path: activePath,
        text: editor.value,
      });
      const diags = data.diagnostics || [];
      lastDiags = diags;
      const eng = data.engine ? ` · ${data.engine}` : "";
      if (!diags.length) {
        statusDiag.textContent = `${data.language || ""}${eng}`;
        statusDiag.className = "";
        return;
      }
      const first = diags[0];
      statusDiag.textContent = `${first.severity} L${first.line}: ${first.message}${eng}`;
      statusDiag.className = first.severity === "error" ? "err" : "warn";
    } catch {
      /* ignore */
    }
  }

  function offsetToPos(text, offset) {
    const slice = text.slice(0, Math.max(0, offset));
    const lines = slice.split("\n");
    return { line: lines.length - 1, character: lines[lines.length - 1].length };
  }

  function syncCursorStatus() {
    if (!statusCursors) return;
    statusCursors.textContent = cursors.length > 1 ? `${cursors.length} cursors` : "";
    paintCursorLayer();
  }

  function paintCursorLayer() {
    if (!cursorLayer) return;
    cursorLayer.innerHTML = "";
    if (!cursors.length) return;
    const padX = 16;
    const padY = 14;
    const scrollTop = editor.scrollTop;
    const scrollLeft = editor.scrollLeft;
    for (const off of cursors) {
      const pos = offsetToPos(editor.value, off);
      const el = document.createElement("div");
      el.className = "mc-caret";
      el.style.left = `${padX + pos.character * charWidth - scrollLeft}px`;
      el.style.top = `${padY + pos.line * lineHeight - scrollTop}px`;
      el.style.height = `${lineHeight}px`;
      cursorLayer.appendChild(el);
    }
    if (activePath && buffers.has(activePath)) paintMinimap(buffers.get(activePath));
    if (foldGutter) foldGutter.scrollTop = editor.scrollTop;
    paintInlineValues();
  }

  function paintInlineValues() {
    if (!inlineValuesEl) return;
    inlineValuesEl.innerHTML = "";
    if (!activePath || !lastInlineValues.length) return;
    const padY = 14;
    const scrollTop = editor.scrollTop;
    const lines = editor.value.split("\n");
    for (const iv of lastInlineValues) {
      if ((iv.path || "") !== activePath) continue;
      const line1 = Number(iv.line) || 0;
      if (line1 < 1) continue;
      const line0 = line1 - 1;
      const src = lines[line0] || "";
      const el = document.createElement("div");
      el.className = "inline-value";
      el.textContent = iv.text || "";
      el.title = iv.text || "";
      const leftPad = 16 + Math.min(src.length + 2, 120) * charWidth;
      el.style.left = `${leftPad}px`;
      el.style.top = `${padY + line0 * lineHeight - scrollTop}px`;
      el.style.height = `${lineHeight}px`;
      el.style.lineHeight = `${lineHeight}px`;
      inlineValuesEl.appendChild(el);
    }
  }

  function hideHover() {
    if (hoverTip) hoverTip.classList.add("hidden");
  }

  async function showHoverAtCaret() {
    if (!activePath || !hoverTip) return;
    const caret = editor.selectionStart || 0;
    const pos = offsetToPos(editor.value, caret);
    const place = () => {
      hoverTip.style.left = "24px";
      hoverTip.style.top = `${14 + (pos.line + 1) * lineHeight - editor.scrollTop}px`;
    };
    if (debugPaused) {
      const word = wordAtOffset(editor.value, caret);
      if (word) {
        try {
          const res = await api("POST", "/api/debug/evaluate", {
            expression: word,
            context: "hover",
            ...(activeDebugSessionId ? { sessionId: activeDebugSessionId } : {}),
            ...(selectedDebugFrameId != null ? { frameId: selectedDebugFrameId } : {}),
          });
          const val = res.result || res;
          const text = `${word} = ${val.value ?? val.error ?? "?"}${val.type ? ` (${val.type})` : ""}`;
          hoverTip.textContent = text;
          hoverTip.classList.remove("hidden");
          place();
          return;
        } catch {
          /* fall through to LSP */
        }
      }
    }
    try {
      const data = await api("POST", "/api/lsp/hover", {
        path: activePath,
        text: editor.value,
        line: pos.line,
        character: pos.character,
      });
      const text = (data.contents || "").trim();
      if (!text) {
        hideHover();
        return;
      }
      hoverTip.textContent = text;
      hoverTip.classList.remove("hidden");
      place();
    } catch {
      hideHover();
    }
  }

  async function goToDefinition() {
    if (!activePath) return;
    const caret = editor.selectionStart || 0;
    const pos = offsetToPos(editor.value, caret);
    try {
      const data = await api("POST", "/api/lsp/definition", {
        path: activePath,
        text: editor.value,
        line: pos.line,
        character: pos.character,
      });
      const loc = (data.locations || [])[0];
      if (!loc) {
        setStatus(activePath, "no definition");
        return;
      }
      await openFile(loc.path);
      const lines = editor.value.split("\n");
      let off = 0;
      for (let i = 0; i < loc.line && i < lines.length; i++) off += lines[i].length + 1;
      off += loc.character || 0;
      editor.focus();
      editor.setSelectionRange(off, off);
      cursors = [off];
      syncCursorStatus();
    } catch (e) {
      setStatus(activePath, String(e.message || e));
    }
  }

  async function renameSymbol() {
    if (!activePath) return;
    const caret = editor.selectionStart || 0;
    const pos = offsetToPos(editor.value, caret);
    const newName = prompt("Rename to:");
    if (!newName) return;
    try {
      await saveActive();
      const data = await api("POST", "/api/lsp/rename", {
        path: activePath,
        text: editor.value,
        line: pos.line,
        character: pos.character,
        newName,
      });
      openPanel("changes");
      if (data.change) await showChangeDiff(data.change.id);
    } catch (e) {
      alert(e.message || e);
    }
  }

  async function jumpToLocation(loc) {
    if (!loc || !loc.path) return;
    await openFile(loc.path);
    const lines = editor.value.split("\n");
    let off = 0;
    for (let i = 0; i < loc.line && i < lines.length; i++) off += lines[i].length + 1;
    off += loc.character || 0;
    editor.focus();
    editor.setSelectionRange(off, off);
    cursors = [off];
    syncCursorStatus();
  }

  async function findReferences() {
    if (!activePath) return;
    const caret = editor.selectionStart || 0;
    const pos = offsetToPos(editor.value, caret);
    openPanel("refs");
    panelBody.innerHTML = "<p class='meta'>Finding references…</p>";
    try {
      const data = await api("POST", "/api/lsp/references", {
        path: activePath,
        text: editor.value,
        line: pos.line,
        character: pos.character,
      });
      const locs = data.locations || [];
      panelBody.innerHTML = "";
      const tip = document.createElement("p");
      tip.className = "meta";
      tip.textContent = `${locs.length} reference(s) · ${data.engine || "none"}`;
      const list = document.createElement("div");
      list.className = "ref-list";
      if (!locs.length) {
        list.textContent = data.error || "No references.";
      }
      for (const loc of locs) {
        const btn = document.createElement("button");
        btn.className = "hit";
        btn.textContent = `${loc.path}:${(loc.line || 0) + 1}:${(loc.character || 0) + 1}`;
        btn.onclick = () => jumpToLocation(loc);
        list.appendChild(btn);
      }
      panelBody.append(tip, list);
    } catch (e) {
      panelBody.innerHTML = `<p>${e.message || e}</p>`;
    }
  }

  async function runCodeActions() {
    if (!activePath) return;
    const start = editor.selectionStart || 0;
    const end = editor.selectionEnd || start;
    const pos = offsetToPos(editor.value, start);
    const endPos = offsetToPos(editor.value, end);
    openPanel("actions");
    panelBody.innerHTML = "<p class='meta'>Loading code actions…</p>";
    try {
      const data = await api("POST", "/api/lsp/codeAction", {
        path: activePath,
        text: editor.value,
        line: pos.line,
        character: pos.character,
        endLine: endPos.line,
        endCharacter: endPos.character,
        diagnostics: lastDiags,
      });
      const actions = data.actions || [];
      panelBody.innerHTML = "";
      const tip = document.createElement("p");
      tip.className = "meta";
      tip.textContent = `${actions.length} action(s) · ${data.engine || "none"}`;
      const list = document.createElement("div");
      list.className = "action-list";
      if (!actions.length) {
        list.textContent = data.error || "No code actions.";
      }
      for (const action of actions) {
        const btn = document.createElement("button");
        btn.className = "hit";
        const kind = action.kind ? ` · ${action.kind}` : "";
        btn.textContent = `${action.title || "action"}${kind}`;
        if (action.disabled) {
          btn.disabled = true;
          btn.title = (action.disabled && action.disabled.reason) || "disabled";
        }
        btn.onclick = async () => {
          try {
            const overrides = {};
            for (const [p, buf] of buffers) overrides[p] = buf.text;
            const res = await api("POST", "/api/lsp/codeAction/apply", {
              action,
              openOverrides: overrides,
            });
            openPanel("changes");
            if (res.change) await showChangeDiff(res.change.id);
          } catch (err) {
            alert(err.message || err);
          }
        };
        list.appendChild(btn);
      }
      panelBody.append(tip, list);
    } catch (e) {
      panelBody.innerHTML = `<p>${e.message || e}</p>`;
    }
  }

  function hideCompletion() {
    completionItems = [];
    completionIndex = 0;
    if (completionEl) {
      completionEl.classList.add("hidden");
      completionEl.innerHTML = "";
    }
  }

  function renderCompletion() {
    if (!completionEl) return;
    if (!completionItems.length) {
      hideCompletion();
      return;
    }
    completionEl.innerHTML = "";
    completionItems.forEach((item, i) => {
      const li = document.createElement("li");
      if (i === completionIndex) li.className = "active";
      li.innerHTML = `${item.label}<span class="detail">${item.detail || ""}</span>`;
      li.onmousedown = (e) => {
        e.preventDefault();
        applyCompletion(item);
      };
      completionEl.appendChild(li);
    });
    completionEl.classList.remove("hidden");
    // position near caret roughly under textarea top-left + line estimate
    const pos = offsetToPos(editor.value, editor.selectionStart || 0);
    completionEl.style.left = "16px";
    completionEl.style.top = `${14 + (pos.line + 1) * 20}px`;
  }

  function applyCompletion(item) {
    const text = editor.value;
    const caret = editor.selectionStart || 0;
    let start = caret;
    while (start > 0 && /[\w$]/.test(text[start - 1])) start -= 1;
    const insert = item.insertText || item.label;
    const next = text.slice(0, start) + insert + text.slice(caret);
    editor.value = next;
    const newCaret = start + insert.length;
    editor.setSelectionRange(newCaret, newCaret);
    cursors = [newCaret];
    const buf = buffers.get(activePath);
    if (buf) {
      buf.text = next;
      paint(editor, hlA, buf.language);
      renderTabs();
    }
    hideCompletion();
    syncCursorStatus();
    scheduleDiagnose();
  }

  function scheduleComplete() {
    clearTimeout(completeTimer);
    completeTimer = setTimeout(runComplete, 180);
  }

  async function runComplete() {
    if (!activePath) return;
    const caret = editor.selectionStart || 0;
    const pos = offsetToPos(editor.value, caret);
    try {
      const data = await api("POST", "/api/lsp/complete", {
        path: activePath,
        text: editor.value,
        line: pos.line,
        character: pos.character,
      });
      completionItems = data.items || [];
      completionIndex = 0;
      renderCompletion();
    } catch {
      hideCompletion();
    }
  }

  function applyTypedToCursors(ch) {
    if (cursors.length <= 1) return false;
    let text = editor.value;
    const sorted = [...cursors].sort((a, b) => b - a);
    const nextCursors = [];
    for (const off of sorted) {
      text = text.slice(0, off) + ch + text.slice(off);
      nextCursors.push(off + ch.length);
    }
    editor.value = text;
    cursors = nextCursors.sort((a, b) => a - b);
    editor.setSelectionRange(cursors[cursors.length - 1], cursors[cursors.length - 1]);
    const buf = buffers.get(activePath);
    if (buf) {
      buf.text = text;
      paint(editor, hlA, buf.language);
      renderTabs();
    }
    syncCursorStatus();
    return true;
  }

  function addNextOccurrenceCursor() {
    const start = editor.selectionStart || 0;
    const end = editor.selectionEnd || 0;
    if (end <= start) return;
    const word = editor.value.slice(start, end);
    let from = end;
    let idx = editor.value.indexOf(word, from);
    if (idx < 0) idx = editor.value.indexOf(word, 0);
    if (idx < 0 || idx === start) return;
    if (!cursors.length) cursors = [end];
    if (!cursors.includes(idx + word.length)) cursors.push(idx + word.length);
    cursors.sort((a, b) => a - b);
    editor.setSelectionRange(idx, idx + word.length);
    syncCursorStatus();
  }

  function toggleFind(show) {
    findBar.classList.toggle("hidden", !show);
    if (show) {
      findInput.focus();
      findInput.select();
    }
  }

  function findNext() {
    const q = findInput.value;
    if (!q) return;
    const text = editor.value;
    const from = editor.selectionEnd || 0;
    let idx = text.indexOf(q, from);
    if (idx < 0) idx = text.indexOf(q, 0);
    if (idx < 0) {
      setStatus(activePath || "Ready", "no match");
      return;
    }
    editor.focus();
    editor.setSelectionRange(idx, idx + q.length);
  }

  function closePanel() {
    panel.classList.add("hidden");
    if (panelMode === "debug") stopDebugPoll();
    panelMode = "";
    applyShellLayout();
    persistLayout();
  }

  function openPanel(mode) {
    if (mode === "term") {
      openBottom();
      return;
    }
    panelMode = mode;
    panel.classList.remove("hidden");
    applyShellLayout();
    panelTitle.textContent =
      {
        changes: "Changes",
        git: "Git",
        ai: "AI (explicit)",
        perms: "Permissions",
        search: "Search",
        debug: "Debug",
        refs: "References",
        actions: "Code Actions",
      }[mode] || mode;
    if (mode === "changes") renderChangesPanel();
    if (mode === "git") renderGitPanel();
    if (mode === "ai") renderAiPanel();
    if (mode === "perms") renderPermsPanel();
    if (mode === "search") renderSearchPanel();
    if (mode === "debug") renderDebugPanel();
    persistLayout();
  }

  function stopDebugPoll() {
    if (debugPoll) {
      clearInterval(debugPoll);
      debugPoll = 0;
    }
  }

  function applyDebugSnapshot(st) {
    if (!st) return;
    if (st.breakpoints) breakpoints = st.breakpoints;
    else if (st.breakpointLines) {
      breakpoints = {};
      for (const [p, lines] of Object.entries(st.breakpointLines)) {
        breakpoints[p] = (lines || []).map((line) => ({ line }));
      }
    }
    if (st.breakpointGroups && typeof st.breakpointGroups === "object") {
      breakpointGroups = { ...st.breakpointGroups };
    }
    if (st.coverage && st.coverage.files) {
      applyCoverageFiles(st.coverage.files);
    }
    if (st.layout && typeof st.layout === "object") {
      debugLayout = { ...debugLayout, ...st.layout };
    }
    if (st.sessionId || st.activeSessionId) activeDebugSessionId = st.sessionId || st.activeSessionId || "";
    if (st.selectedFrameId != null) selectedDebugFrameId = st.selectedFrameId;
    debugPaused = Boolean(st.stopped);
    lastInlineValues = st.stopped ? st.inlineValues || [] : [];
    const frames = st.stack || [];
    const selected =
      frames.find((f) => f.id === selectedDebugFrameId || String(f.id) === String(selectedDebugFrameId)) ||
      frames[0];
    if (st.stopped && selected) {
      debugStoppedPath = selected.path || "";
      debugStoppedLine = Number(selected.line) || 0;
    } else if (!(st.sessions || []).some((s) => s.stopped)) {
      debugStoppedPath = "";
      debugStoppedLine = 0;
      lastInlineValues = [];
      selectedDebugFrameId = null;
      debugPaused = false;
    }
    if (activePath && buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
    paintInlineValues();
  }

  function makeDebugSection(title, key, bodyEl) {
    const details = document.createElement("details");
    details.className = "debug-section";
    details.open = debugLayout[key] !== false;
    const summary = document.createElement("summary");
    summary.textContent = title;
    details.append(summary, bodyEl);
    details.addEventListener("toggle", () => {
      debugLayout[key] = details.open;
      scheduleDebugLayoutPersist();
    });
    return details;
  }

  function appendVarNode(parent, v, depth, onRefresh) {
    const row = document.createElement("div");
    row.className = "debug-var-row";
    const expandable = Boolean(v.expandable || (v.variablesReference && v.variablesReference > 0));
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "debug-var-toggle";
    toggle.textContent = expandable ? "▶" : "";
    toggle.disabled = !expandable;
    const body = document.createElement("div");
    body.className = "debug-var-body";
    const scope = v.scope ? `[${v.scope}] ` : "";
    const typeHint = v.type ? ` : ${v.type}` : "";
    body.textContent = `${scope}${v.name}${typeHint} = ${v.error || v.value || ""}`;
    const actions = document.createElement("div");
    actions.className = "debug-var-actions";
    if (v.name && !String(v.name).includes(".")) {
      const dbp = document.createElement("button");
      dbp.type = "button";
      dbp.textContent = "⊗";
      dbp.title = "Data breakpoint (break on write)";
      dbp.onclick = async (e) => {
        e.stopPropagation();
        try {
          await api("POST", "/api/debug/dataBreakpoints", {
            name: v.name,
            accessType: "write",
          });
          if (onRefresh) onRefresh();
        } catch (err) {
          alert(err.message || err);
        }
      };
      actions.appendChild(dbp);
    }
    const children = document.createElement("div");
    children.className = "debug-var-children";
    children.hidden = true;
    let loaded = false;
    let open = false;
    toggle.onclick = async () => {
      if (!expandable) return;
      open = !open;
      toggle.textContent = open ? "▼" : "▶";
      children.hidden = !open;
      if (open && !loaded) {
        loaded = true;
        children.textContent = "…";
        try {
          const data = await api("POST", "/api/debug/variables", {
            variablesReference: v.variablesReference,
            ...(activeDebugSessionId ? { sessionId: activeDebugSessionId } : {}),
          });
          children.innerHTML = "";
          const list = data.variables || [];
          if (!list.length) {
            const empty = document.createElement("div");
            empty.className = "meta";
            empty.textContent = "(empty)";
            children.appendChild(empty);
          } else {
            for (const child of list) appendVarNode(children, child, (depth || 0) + 1, onRefresh);
          }
        } catch (e) {
          children.textContent = String(e.message || e);
        }
      }
    };
    row.append(toggle, body, actions);
    parent.appendChild(row);
    parent.appendChild(children);
  }

  async function renderDebugPanel() {
    stopDebugPoll();
    panelBody.innerHTML = "<p class='meta'>Loading…</p>";
    let adapters = {};
    try {
      adapters = await api("GET", "/api/debug/adapters");
    } catch {
      adapters = {};
    }
    panelBody.innerHTML = "";
    const tip = document.createElement("p");
    tip.className = "meta";
    const rev = (adapters.reverse || {});
    tip.textContent = `Reverse: ${(rev.modes || ["timeline"]).join(" / ")}${
      adapters.rr ? " · rr ready" : rev.hint ? ` · ${rev.hint}` : ""
    }. Shift=cond · Alt+Shift=log. F9/F5/F10/F11.`;
    const launchRow = document.createElement("div");
    launchRow.className = "row";
    const launchSelect = document.createElement("select");
    launchSelect.className = "debug-launch-select";
    const launchSave = document.createElement("button");
    launchSave.textContent = "Save launch.json";
    const launchEnsure = document.createElement("button");
    launchEnsure.textContent = "Write defaults";
    const launchEditToggle = document.createElement("button");
    launchEditToggle.textContent = "Edit config";
    launchRow.append(launchSelect, launchEnsure, launchSave, launchEditToggle);
    const launchEditorEl = document.createElement("div");
    launchEditorEl.className = "debug-launch-editor hidden";
    /** @type {any[]} */
    let launchConfigs = [];
    /** @type {any[]} */
    let launchCompounds = [];
    const fillLaunchSelect = (configs, preferred, compounds) => {
      launchConfigs = configs || [];
      if (compounds) launchCompounds = compounds;
      launchSelect.innerHTML = "";
      const none = document.createElement("option");
      none.value = "";
      none.textContent = "(current file)";
      launchSelect.appendChild(none);
      for (const c of launchConfigs) {
        const opt = document.createElement("option");
        opt.value = c.name || "";
        opt.dataset.kind = "config";
        opt.textContent = `${c.name} · ${c.request || "launch"}/${c.type || "?"}${
          c.reverse === "rr" ? " · rr" : ""
        }`;
        if (preferred && preferred === c.name) opt.selected = true;
        launchSelect.appendChild(opt);
      }
      for (const c of launchCompounds || []) {
        const opt = document.createElement("option");
        opt.value = `compound:${c.name || ""}`;
        opt.dataset.kind = "compound";
        opt.textContent = `⬡ ${c.name} · compound(${(c.configurations || []).length})`;
        if (preferred && preferred === opt.value) opt.selected = true;
        launchSelect.appendChild(opt);
      }
    };
    const field = (label, el) => {
      const wrap = document.createElement("label");
      wrap.className = "debug-launch-field";
      const lab = document.createElement("span");
      lab.textContent = label;
      wrap.append(lab, el);
      return wrap;
    };
    const paintLaunchEditor = () => {
      launchEditorEl.innerHTML = "";
      const name = launchSelect.value;
      let cfg = launchConfigs.find((c) => c.name === name);
      if (!cfg) {
        cfg = {
          name: name || "New config",
          type: "python",
          request: "launch",
          program: "${file}",
          cwd: "${workspaceFolder}",
          stopOnEntry: true,
        };
      }
      const nameIn = document.createElement("input");
      nameIn.value = cfg.name || "";
      const typeIn = document.createElement("select");
      typeIn.innerHTML = `<option value="python">python</option><option value="node">node</option><option value="custom">custom</option><option value="jupyter">jupyter</option><option value="wasm">wasm</option>`;
      typeIn.value = ["node", "custom", "jupyter", "wasm"].includes(cfg.type) ? cfg.type : "python";
      const adapterIn = document.createElement("input");
      adapterIn.value = Array.isArray(cfg.debugAdapter)
        ? cfg.debugAdapter.join(" ")
        : cfg.debugAdapter || "";
      adapterIn.placeholder = "debugAdapter cmd (custom)";
      const skipIn = document.createElement("input");
      skipIn.value = Array.isArray(cfg.skipFiles) ? cfg.skipFiles.join(", ") : "";
      skipIn.placeholder = "skipFiles globs (comma)";
      const schemaEl = document.createElement("div");
      schemaEl.className = "debug-schema-errors";
      const reqIn = document.createElement("select");
      reqIn.innerHTML = `<option value="launch">launch</option><option value="attach">attach</option>`;
      reqIn.value = cfg.request === "attach" ? "attach" : "launch";
      const progIn = document.createElement("input");
      progIn.value = cfg.program || cfg.module || "";
      progIn.placeholder = "program or module";
      const cwdIn = document.createElement("input");
      cwdIn.value = cfg.cwd || "${workspaceFolder}";
      const hostIn2 = document.createElement("input");
      hostIn2.value = cfg.host || "127.0.0.1";
      const portIn2 = document.createElement("input");
      portIn2.type = "number";
      portIn2.value = String(cfg.port || (typeIn.value === "node" ? 9229 : 5678));
      const argsIn = document.createElement("input");
      argsIn.value = Array.isArray(cfg.args) ? cfg.args.join(" ") : "";
      argsIn.placeholder = "args (space-separated)";
      const sshIn = document.createElement("input");
      sshIn.value = (cfg.ssh && cfg.ssh.host) || "";
      sshIn.placeholder = "SSH user@host (attach tunnel)";
      const dockerIn = document.createElement("input");
      dockerIn.value = (cfg.docker && cfg.docker.container) || "";
      dockerIn.placeholder = "Docker container name";
      const preTaskIn = document.createElement("input");
      preTaskIn.value = cfg.preLaunchTask || "";
      preTaskIn.placeholder = "preLaunchTask label";
      const reverseIn = document.createElement("select");
      reverseIn.innerHTML = `<option value="">(none)</option><option value="rr">rr</option>`;
      reverseIn.value = cfg.reverse === "rr" ? "rr" : "";
      const stopCb = document.createElement("input");
      stopCb.type = "checkbox";
      stopCb.checked = cfg.stopOnEntry !== false;
      const applyBtn = document.createElement("button");
      applyBtn.textContent = "Apply to list";
      applyBtn.onclick = () => {
        const next = {
          ...cfg,
          name: nameIn.value.trim() || "Debug",
          type: typeIn.value,
          request: reqIn.value,
          cwd: cwdIn.value || "${workspaceFolder}",
          stopOnEntry: stopCb.checked,
          args: argsIn.value.trim() ? argsIn.value.trim().split(/\s+/) : [],
          preLaunchTask: preTaskIn.value.trim() || undefined,
          reverse: reverseIn.value || undefined,
        };
        if (adapterIn.value.trim()) next.debugAdapter = adapterIn.value.trim().split(/\s+/);
        else delete next.debugAdapter;
        if (skipIn.value.trim())
          next.skipFiles = skipIn.value.split(",").map((s) => s.trim()).filter(Boolean);
        else delete next.skipFiles;
        if (reqIn.value === "attach") {
          next.host = hostIn2.value || "127.0.0.1";
          next.port = Number(portIn2.value) || 5678;
          delete next.program;
          delete next.module;
          if (sshIn.value.trim()) {
            next.ssh = {
              host: sshIn.value.trim(),
              localPort: next.port,
              remotePort: next.port,
            };
          } else delete next.ssh;
          if (dockerIn.value.trim()) {
            next.docker = { container: dockerIn.value.trim(), port: next.port };
          } else delete next.docker;
        } else {
          if (progIn.value.includes("pytest") || progIn.value === "pytest") {
            next.module = "pytest";
            delete next.program;
          } else {
            next.program = progIn.value || "${file}";
            delete next.module;
          }
          delete next.host;
          delete next.port;
          delete next.ssh;
          delete next.docker;
        }
        const idx = launchConfigs.findIndex((c) => c.name === name || c.name === next.name);
        if (idx >= 0) launchConfigs[idx] = next;
        else launchConfigs.push(next);
        fillLaunchSelect(launchConfigs, next.name);
        launchSelect.value = next.name;
        api("POST", "/api/debug/launch/validate", {
          version: "0.2.0",
          configurations: launchConfigs,
          compounds: launchCompounds,
        })
          .then((v) => {
            const errs = (v.errors || []).map((e) => `${e.path}: ${e.message}`);
            const warns = (v.warnings || []).map((e) => `${e.path}: ${e.message}`);
            schemaEl.textContent = errs.length
              ? "✖ " + errs.join(" · ")
              : warns.length
                ? "⚠ " + warns.join(" · ")
                : "✓ schema ok";
            schemaEl.className =
              "debug-schema-errors" + (errs.length ? " error" : warns.length ? " warn" : " ok");
          })
          .catch(() => {});
        setStatus(activePath || "debug", `Updated config "${next.name}" (Save launch.json to persist)`);
      };
      const addPreset = document.createElement("button");
      addPreset.textContent = "+ SSH attach";
      addPreset.onclick = () => {
        launchConfigs.push({
          name: "Python: SSH attach",
          type: "python",
          request: "attach",
          host: "127.0.0.1",
          port: 5678,
          ssh: { host: "user@remote", localPort: 5678, remotePort: 5678 },
          pathMappings: [{ localRoot: "${workspaceFolder}", remoteRoot: "/app" }],
        });
        fillLaunchSelect(launchConfigs, "Python: SSH attach");
        paintLaunchEditor();
      };
      const addDocker = document.createElement("button");
      addDocker.textContent = "+ Docker attach";
      addDocker.onclick = () => {
        launchConfigs.push({
          name: "Python: Docker attach",
          type: "python",
          request: "attach",
          host: "127.0.0.1",
          port: 5678,
          docker: { container: "my-app", port: 5678 },
          pathMappings: [{ localRoot: "${workspaceFolder}", remoteRoot: "/app" }],
        });
        fillLaunchSelect(launchConfigs, "Python: Docker attach");
        paintLaunchEditor();
      };
      const inspectDocker = document.createElement("button");
      inspectDocker.textContent = "Inspect Docker";
      inspectDocker.onclick = async () => {
        const container = dockerIn.value.trim();
        if (!container) return alert("Enter container name");
        try {
          const res = await api("POST", "/api/debug/docker/inspect", {
            container,
            apply: true,
          });
          pathMappings = (res.pathMappings || []).map((m) => ({ ...m }));
          renderPathMaps();
          if (res.hostPort) portIn2.value = String(res.hostPort);
          setStatus(activePath || "debug", `Docker mounts → ${pathMappings.length} pathMappings`);
        } catch (e) {
          alert(e.message || e);
        }
      };
      launchEditorEl.append(
        field("Name", nameIn),
        field("Type", typeIn),
        field("Request", reqIn),
        field("Program/module", progIn),
        field("debugAdapter", adapterIn),
        field("skipFiles", skipIn),
        field("Cwd", cwdIn),
        field("Args", argsIn),
        field("preLaunchTask", preTaskIn),
        field("Reverse", reverseIn),
        field("Host", hostIn2),
        field("Port", portIn2),
        field("SSH", sshIn),
        field("Docker", dockerIn),
        field("Stop on entry", stopCb),
        schemaEl
      );
      const act = document.createElement("div");
      act.className = "row";
      act.append(applyBtn, addPreset, addDocker, inspectDocker);
      launchEditorEl.appendChild(act);
    };
    launchEditToggle.onclick = () => {
      launchEditorEl.classList.toggle("hidden");
      if (!launchEditorEl.classList.contains("hidden")) paintLaunchEditor();
    };
    launchSelect.onchange = () => {
      if (!launchEditorEl.classList.contains("hidden")) paintLaunchEditor();
    };
    const sessRow = document.createElement("div");
    sessRow.className = "row";
    const sessSelect = document.createElement("select");
    sessSelect.className = "debug-session-select";
    const attachRow = document.createElement("div");
    attachRow.className = "row debug-attach-row";
    const engSelect = document.createElement("select");
    engSelect.innerHTML = `<option value="python">python</option><option value="node">node</option>`;
    const hostInput = document.createElement("input");
    hostInput.className = "host";
    hostInput.type = "text";
    hostInput.value = "127.0.0.1";
    hostInput.placeholder = "host";
    const portInput = document.createElement("input");
    portInput.type = "number";
    portInput.value = "5678";
    portInput.placeholder = "port";
    const attachBtn = document.createElement("button");
    attachBtn.textContent = "Attach";
    attachRow.append(engSelect, hostInput, portInput, attachBtn);
    const pathMapEl = document.createElement("div");
    /** @type {{localRoot:string, remoteRoot:string}[]} */
    let pathMappings = [];
    const renderPathMaps = () => {
      pathMapEl.innerHTML = "";
      const head = document.createElement("div");
      head.className = "meta";
      head.textContent = "Path mappings (localRoot → remoteRoot)";
      pathMapEl.appendChild(head);
      if (!pathMappings.length) pathMappings = [{ localRoot: "", remoteRoot: "" }];
      pathMappings.forEach((m, idx) => {
        const rowM = document.createElement("div");
        rowM.className = "debug-pathmap-row";
        const local = document.createElement("input");
        local.placeholder = "localRoot";
        local.value = m.localRoot || "";
        const remote = document.createElement("input");
        remote.placeholder = "remoteRoot";
        remote.value = m.remoteRoot || "";
        local.oninput = () => {
          pathMappings[idx].localRoot = local.value;
        };
        remote.oninput = () => {
          pathMappings[idx].remoteRoot = remote.value;
        };
        const rm = document.createElement("button");
        rm.textContent = "×";
        rm.onclick = () => {
          pathMappings.splice(idx, 1);
          renderPathMaps();
        };
        rowM.append(local, remote, rm);
        pathMapEl.appendChild(rowM);
      });
      const actions = document.createElement("div");
      actions.className = "row";
      const addMap = document.createElement("button");
      addMap.textContent = "+ map";
      addMap.onclick = () => {
        pathMappings.push({ localRoot: "", remoteRoot: "" });
        renderPathMaps();
      };
      const saveMap = document.createElement("button");
      saveMap.textContent = "Save maps";
      saveMap.onclick = async () => {
        try {
          const clean = pathMappings.filter((x) => x.localRoot && x.remoteRoot);
          const res = await api("POST", "/api/debug/pathMappings", { pathMappings: clean });
          pathMappings = res.pathMappings || clean;
          renderPathMaps();
        } catch (e) {
          alert(e.message || e);
        }
      };
      const multiRoot = document.createElement("button");
      multiRoot.textContent = "Multi-root sync";
      multiRoot.onclick = async () => {
        try {
          const res = await api("POST", "/api/debug/pathMappings/multiRoot", {});
          pathMappings = (res.pathMappings || []).map((m) => ({ ...m }));
          renderPathMaps();
          setStatus(activePath || "debug", `Multi-root → ${pathMappings.length} mappings`);
        } catch (e) {
          alert(e.message || e);
        }
      };
      actions.append(addMap, saveMap, multiRoot);
      pathMapEl.appendChild(actions);
    };
    renderPathMaps();
    const skipRow = document.createElement("div");
    skipRow.className = "row";
    const skipInput = document.createElement("input");
    skipInput.placeholder = "skipFiles / blackbox globs (comma)…";
    skipInput.style.flex = "1";
    const skipBtn = document.createElement("button");
    skipBtn.textContent = "Save skipFiles";
    skipBtn.onclick = async () => {
      try {
        const patterns = skipInput.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        const res = await api("POST", "/api/debug/skipFiles", { skipFiles: patterns });
        skipInput.value = (res.skipFiles || patterns).join(", ");
      } catch (e) {
        alert(e.message || e);
      }
    };
    skipRow.append(skipInput, skipBtn);
    const eventsEl = document.createElement("pre");
    eventsEl.className = "debug-events";
    eventsEl.textContent = "(session events: launch → stopped → continued)";
    const eventsSec = document.createElement("div");
    const paintEvents = (events) => {
      const list = events || [];
      if (!list.length) {
        eventsEl.textContent = "(no events yet)";
        return;
      }
      eventsEl.textContent = list
        .slice(-40)
        .map((e) => {
          const t = e.ts ? new Date(e.ts * 1000).toLocaleTimeString() : "";
          return `${t}  ${e.kind}${e.reason ? " · " + e.reason : ""}${
            e.path ? " @ " + e.path + ":" + (e.line || "") : ""
          }`;
        })
        .join("\n");
    };
    eventsSec.appendChild(eventsEl);
    const excRow = document.createElement("div");
    excRow.className = "debug-exc-row";
    const raisedCb = document.createElement("input");
    raisedCb.type = "checkbox";
    raisedCb.id = "dbg-exc-raised";
    const uncaughtCb = document.createElement("input");
    uncaughtCb.type = "checkbox";
    uncaughtCb.id = "dbg-exc-uncaught";
    uncaughtCb.checked = true;
    const raisedLab = document.createElement("label");
    raisedLab.append(raisedCb, document.createTextNode("Break on raised"));
    const uncaughtLab = document.createElement("label");
    uncaughtLab.append(uncaughtCb, document.createTextNode("Break on uncaught"));
    excRow.append(raisedLab, uncaughtLab);
    const syncExc = async () => {
      try {
        await api("POST", "/api/debug/exceptions", {
          raised: raisedCb.checked,
          uncaught: uncaughtCb.checked,
        });
      } catch (e) {
        alert(e.message || e);
      }
    };
    raisedCb.onchange = syncExc;
    uncaughtCb.onchange = syncExc;
    const row = document.createElement("div");
    row.className = "row";
    const mkBtn = (label) => {
      const b = document.createElement("button");
      b.textContent = label;
      return b;
    };
    const startBtn = mkBtn("Start");
    const testBtn = mkBtn("Debug Test");
    const postBtn = mkBtn("Postmortem");
    const stopBtn = mkBtn("Stop");
    const stopAllBtn = mkBtn("Stop all");
    const contBtn = mkBtn("Continue");
    const nextBtn = mkBtn("Step");
    const inBtn = mkBtn("Step In");
    const outBtn = mkBtn("Step Out");
    const backBtn = mkBtn("Step Back");
    const revContBtn = mkBtn("◀ Continue");
    const bpBtn = mkBtn("Toggle BP");
    const condBtn = mkBtn("BP if…");
    const hitBtn = mkBtn("BP hit…");
    const logBtn = mkBtn("BP log…");
    const covBtn = mkBtn("Coverage");
    const profCpuBtn = mkBtn("CPU profile");
    const profHeapBtn = mkBtn("Heap snapshot");
    const stateEl = document.createElement("div");
    stateEl.className = "meta";
    const groupsEl = document.createElement("div");
    groupsEl.className = "debug-bp-groups";
    const paintGroups = (groups) => {
      groupsEl.innerHTML = "";
      const head = document.createElement("div");
      head.className = "meta";
      head.textContent = "Breakpoint groups";
      groupsEl.appendChild(head);
      const gmap = groups || breakpointGroups || {};
      const keys = Object.keys(gmap);
      if (!keys.length) {
        const d = document.createElement("div");
        d.className = "meta";
        d.textContent = "(assign group via BP group…)";
        groupsEl.appendChild(d);
      }
      for (const g of keys) {
        const rowG = document.createElement("label");
        rowG.className = "debug-bp-group-row";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = gmap[g] !== false;
        cb.onchange = async () => {
          try {
            const res = await api("POST", "/api/debug/breakpoints/groups", {
              group: g,
              enabled: cb.checked,
            });
            breakpointGroups = res.groups || gmap;
            paintGroups(breakpointGroups);
            refresh();
          } catch (e) {
            alert(e.message || e);
          }
        };
        rowG.append(cb, document.createTextNode(` ${g}`));
        groupsEl.appendChild(rowG);
      }
      const batchRow = document.createElement("div");
      batchRow.className = "row";
      const groupName = document.createElement("input");
      groupName.placeholder = "group name";
      groupName.value = "default";
      const setGroupBtn = mkBtn("Set group on line");
      setGroupBtn.onclick = async () => {
        if (!activePath) return;
        const pos = offsetToPos(editor.value, editor.selectionStart || 0);
        try {
          const res = await api("POST", "/api/debug/breakpoints/meta", {
            path: activePath,
            line: pos.line + 1,
            group: groupName.value || "default",
          });
          breakpoints[activePath] = res.breakpoints || [];
          breakpointGroups = res.groups || breakpointGroups;
          paintGroups(breakpointGroups);
          if (buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
        } catch (e) {
          alert(e.message || e);
        }
      };
      const enAll = mkBtn("Enable all");
      enAll.onclick = async () => {
        const enable = [];
        for (const [p, list] of Object.entries(breakpoints)) {
          for (const b of list) enable.push({ path: p, line: typeof b === "number" ? b : b.line });
        }
        try {
          const res = await api("POST", "/api/debug/breakpoints/batch", { enable });
          if (res.breakpoints) breakpoints = res.breakpoints;
          if (res.groups) breakpointGroups = res.groups;
          refresh();
        } catch (e) {
          alert(e.message || e);
        }
      };
      const disAll = mkBtn("Disable all");
      disAll.onclick = async () => {
        const disable = [];
        for (const [p, list] of Object.entries(breakpoints)) {
          for (const b of list) disable.push({ path: p, line: typeof b === "number" ? b : b.line });
        }
        try {
          const res = await api("POST", "/api/debug/breakpoints/batch", { disable });
          if (res.breakpoints) breakpoints = res.breakpoints;
          if (res.groups) breakpointGroups = res.groups;
          refresh();
        } catch (e) {
          alert(e.message || e);
        }
      };
      batchRow.append(groupName, setGroupBtn, enAll, disAll);
      groupsEl.appendChild(batchRow);
    };
    const timelineRow = document.createElement("div");
    timelineRow.className = "debug-timeline-row";
    const timelineLabel = document.createElement("span");
    timelineLabel.className = "meta";
    timelineLabel.textContent = "Timeline";
    const timelineRange = document.createElement("input");
    timelineRange.type = "range";
    timelineRange.min = "0";
    timelineRange.max = "0";
    timelineRange.value = "0";
    const timelineMeta = document.createElement("span");
    timelineMeta.className = "meta";
    const timelineLive = document.createElement("button");
    timelineLive.textContent = "Live";
    const timelineBadge = document.createElement("span");
    timelineBadge.className = "debug-timeline-badge";
    timelineRow.append(timelineLabel, timelineRange, timelineMeta, timelineLive, timelineBadge);
    const threadsEl = document.createElement("div");
    threadsEl.className = "debug-stack debug-threads";
    const stackEl = document.createElement("div");
    stackEl.className = "debug-stack";
    const varsEl = document.createElement("div");
    varsEl.className = "debug-vars";
    const watchEl = document.createElement("div");
    watchEl.className = "debug-vars";
    const dataBpEl = document.createElement("div");
    dataBpEl.className = "debug-vars";
    const memEl = document.createElement("div");
    const memOut = document.createElement("pre");
    memOut.className = "debug-hex";
    memOut.textContent = "(pause, then Disasm / Memory)";
    const memRow = document.createElement("div");
    memRow.className = "row";
    const memInput = document.createElement("input");
    memInput.type = "text";
    memInput.placeholder = "Memory expression (bytes/Buffer)…";
    const memBtn = mkBtn("Memory");
    const disasmBtn = mkBtn("Disasm");
    memRow.append(memInput, memBtn, disasmBtn);
    memEl.append(memRow, memOut);
    // memWriteBtn appended after definition below
    const watchRow = document.createElement("div");
    watchRow.className = "row";
    const watchInput = document.createElement("input");
    watchInput.type = "text";
    watchInput.placeholder = "Watch expression…";
    const watchAdd = mkBtn("Add watch");
    watchRow.append(watchInput, watchAdd);
    const dataBpRow = document.createElement("div");
    dataBpRow.className = "row";
    const dataBpInput = document.createElement("input");
    dataBpInput.type = "text";
    dataBpInput.placeholder = "Data BP name (e.g. x)…";
    const dataBpAdd = mkBtn("Add data BP");
    dataBpRow.append(dataBpInput, dataBpAdd);
    const consoleEl = document.createElement("div");
    consoleEl.className = "debug-console";
    const evalRow = document.createElement("div");
    evalRow.className = "row";
    const evalInput = document.createElement("input");
    evalInput.type = "text";
    evalInput.placeholder = "Debug console evaluate…";
    const evalBtn = mkBtn("Eval");
    const completeBox = document.createElement("div");
    completeBox.className = "debug-console-complete hidden";
    evalRow.append(evalInput, evalBtn);
    let completeTimerDbg = 0;
    const showDbgCompletions = async () => {
      if (!debugPaused || !evalInput.value) {
        completeBox.classList.add("hidden");
        return;
      }
      try {
        const res = await api("POST", "/api/debug/completions", {
          text: evalInput.value,
          column: evalInput.value.length + 1,
          ...sidPayload(),
          ...(selectedDebugFrameId != null ? { frameId: selectedDebugFrameId } : {}),
        });
        const items = res.items || [];
        completeBox.innerHTML = "";
        if (!items.length) {
          completeBox.classList.add("hidden");
          return;
        }
        for (const it of items.slice(0, 12)) {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = it.label || it.text || it;
          b.onclick = () => {
            const label = it.text || it.label || "";
            const prefix = evalInput.value.replace(/[\w$]*$/, "");
            evalInput.value = prefix + label;
            completeBox.classList.add("hidden");
            evalInput.focus();
          };
          completeBox.appendChild(b);
        }
        completeBox.classList.remove("hidden");
      } catch {
        completeBox.classList.add("hidden");
      }
    };
    evalInput.oninput = () => {
      clearTimeout(completeTimerDbg);
      completeTimerDbg = setTimeout(showDbgCompletions, 200);
    };

    const threadsSec = makeDebugSection("Threads", "showStack", threadsEl);
    const stackSec = makeDebugSection("Stack", "showStack", stackEl);
    const varsSec = makeDebugSection("Variables", "showVars", varsEl);
    const watchSec = makeDebugSection("Watches", "showWatches", watchEl);
    const dataBpSec = makeDebugSection("Data breakpoints", "showWatches", dataBpEl);
    const memSec = makeDebugSection("Disasm / Memory", "showConsole", memEl);
    const consoleSec = makeDebugSection("Console", "showConsole", consoleEl);

    const sidPayload = () => (activeDebugSessionId ? { sessionId: activeDebugSessionId } : {});

    const paintState = (st) => {
      applyDebugSnapshot(st);
      stackSec.open = debugLayout.showStack !== false;
      varsSec.open = debugLayout.showVars !== false;
      watchSec.open = debugLayout.showWatches !== false;
      consoleSec.open = debugLayout.showConsole !== false;
      if (st.exceptionBreakpoints) {
        raisedCb.checked = Boolean(st.exceptionBreakpoints.raised);
        uncaughtCb.checked = Boolean(st.exceptionBreakpoints.uncaught);
      }
      if (Array.isArray(st.skipFiles) && document.activeElement !== skipInput) {
        skipInput.value = st.skipFiles.join(", ");
      }
      if (st.bpHits && st.bpHits.heat) {
        window.__bpHeat = st.bpHits.heat;
        if (activePath && buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
      }
      if (typeof st.readonlyAttach === "boolean") roCb.checked = st.readonlyAttach;
      const ev = (st.timeline && st.timeline.events) || st.events;
      if (Array.isArray(ev)) paintEvents(ev);
      if (Array.isArray(st.pathMappings)) {
        pathMappings = st.pathMappings.length
          ? st.pathMappings.map((m) => ({ ...m }))
          : pathMappings;
        // don't fully re-render path maps on every poll (preserve focus) — only if empty UI
        if (!pathMapEl.querySelector(".debug-pathmap-row")) renderPathMaps();
      }
      if (st.launch && Array.isArray(st.launch.configurations)) {
        const cur = launchSelect.value;
        fillLaunchSelect(
          st.launch.configurations,
          cur || undefined,
          st.launch.compounds || launchCompounds
        );
        if (cur) launchSelect.value = cur;
      }
      fillDiffSelects(st.sessions || []);
      if (Array.isArray(st.profiles) && st.profiles.length && !flameEl.childElementCount) {
        const last = st.profiles[st.profiles.length - 1];
        if (last && last.hasFlame) showProfile(last.id).catch(() => {});
      }
      const tl = st.timeline || {};
      const tlen = Number(tl.length) || 0;
      timelineRange.max = String(Math.max(0, tlen - 1));
      timelineRange.value = String(tl.index != null ? tl.index : Math.max(0, tlen - 1));
      timelineMeta.textContent = tlen ? `${(Number(tl.index) || 0) + 1}/${tlen}` : "0/0";
      const rrTag = st.engine && String(st.engine).includes("rr") ? " · rr" : "";
      timelineBadge.textContent = tl.viewing
        ? "VIEWING HISTORY (read-only)" + rrTag
        : rrTag.trim();
      const sessions = st.sessions || [];
      sessSelect.innerHTML = "";
      if (!sessions.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "(no sessions)";
        sessSelect.appendChild(opt);
      }
      for (const s of sessions) {
        const opt = document.createElement("option");
        opt.value = s.id || s.sessionId;
        const tag = s.attached ? "attach" : s.configName || s.engine || "";
        opt.textContent = `${s.path} · ${s.stopped ? "paused" : s.running ? "run" : "dead"} · ${tag}`;
        if ((s.id || s.sessionId) === (st.activeSessionId || st.sessionId)) opt.selected = true;
        sessSelect.appendChild(opt);
      }
      stateEl.textContent = st.running
        ? `${st.path || ""} · ${st.engine || "dbg"} · ${st.stopped ? "paused" : "running"}${
            st.attached ? " · attached" : ""
          }${st.configName ? ` · ${st.configName}` : ""}${st.reason ? ` · ${st.reason}` : ""}${
            st.error ? ` · ${st.error}` : ""
          } · sessions ${sessions.length}`
        : sessions.length
          ? `${sessions.length} session(s)`
          : "Idle";
      threadsEl.innerHTML = "";
      const tid = st.threadId;
      for (const th of st.threads || []) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = `${th.name || th.id}`;
        if (th.id === tid || String(th.id) === String(tid)) b.classList.add("active-thread");
        b.onclick = async () => {
          try {
            paintState(await api("POST", "/api/debug/thread", { threadId: th.id, ...sidPayload() }));
          } catch (e) {
            alert(e.message || e);
          }
        };
        threadsEl.appendChild(b);
      }
      if (!(st.threads || []).length) {
        const d = document.createElement("div");
        d.className = "meta";
        d.textContent = "(no threads)";
        threadsEl.appendChild(d);
      }
      stackEl.innerHTML = "";
      const selId = st.selectedFrameId != null ? st.selectedFrameId : selectedDebugFrameId;
      for (const fr of st.stack || []) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = `${fr.name}  ${fr.path}:${fr.line}`;
        if (fr.id === selId || String(fr.id) === String(selId)) b.classList.add("active-frame");
        b.onclick = async () => {
          try {
            const next = await api("POST", "/api/debug/frame", {
              frameId: fr.id,
              ...sidPayload(),
            });
            paintState(next);
            if (fr.path && !String(fr.path).startsWith("(")) {
              await openFile(fr.path);
              const lines = editor.value.split("\n");
              let off = 0;
              for (let i = 0; i < (fr.line || 1) - 1 && i < lines.length; i++) off += lines[i].length + 1;
              editor.setSelectionRange(off, off);
              editor.focus();
            }
          } catch (e) {
            alert(e.message || e);
          }
        };
        stackEl.appendChild(b);
      }
      if (!(st.stack || []).length) {
        const d = document.createElement("div");
        d.className = "meta";
        d.textContent = "(none)";
        stackEl.appendChild(d);
      }
      varsEl.innerHTML = "";
      for (const v of st.variables || []) appendVarNode(varsEl, v, 0, refresh);
      if (!(st.variables || []).length) {
        const d = document.createElement("div");
        d.className = "meta";
        d.textContent = "(none)";
        varsEl.appendChild(d);
      }
      watchEl.innerHTML = "";
      for (const w of st.watches || []) {
        const wrap = document.createElement("div");
        appendVarNode(
          wrap,
          {
            name: w.expression,
            value: w.error || w.value || "",
            type: w.type || "",
            variablesReference: w.variablesReference || 0,
            expandable: w.expandable,
          },
          0,
          refresh
        );
        const rm = document.createElement("button");
        rm.textContent = "×";
        rm.onclick = async () => {
          await api("POST", "/api/debug/watches/remove", { expression: w.expression });
          refresh();
        };
        const first = wrap.querySelector(".debug-var-row");
        if (first) first.appendChild(rm);
        watchEl.appendChild(wrap);
      }
      if (!(st.watches || []).length) {
        const d = document.createElement("div");
        d.className = "meta";
        d.textContent = "(no watches)";
        watchEl.appendChild(d);
      }
      dataBpEl.innerHTML = "";
      for (const db of st.dataBreakpoints || []) {
        const d = document.createElement("div");
        d.className = "debug-data-bp-row";
        d.innerHTML = `<span>${escapeHtml(db.name)} <span class="meta">${escapeHtml(
          db.accessType || "write"
        )}</span></span>`;
        const rm = document.createElement("button");
        rm.textContent = "×";
        rm.onclick = async () => {
          await api("POST", "/api/debug/dataBreakpoints/remove", { id: db.id, name: db.name });
          refresh();
        };
        d.appendChild(rm);
        dataBpEl.appendChild(d);
      }
      if (!(st.dataBreakpoints || []).length) {
        const d = document.createElement("div");
        d.className = "meta";
        d.textContent = "(none — Python DAP write watches; Node soft-detects on pause)";
        dataBpEl.appendChild(d);
      }
      consoleEl.innerHTML = "";
      for (const line of st.console || []) {
        const d = document.createElement("div");
        d.className = `debug-console-line ${line.type || ""}`;
        d.textContent =
          line.type === "in" ? `› ${line.text}` : line.type === "out" ? String(line.text) : line.text || "";
        consoleEl.appendChild(d);
      }
      const nextGroups = st.breakpointGroups || breakpointGroups;
      if (JSON.stringify(nextGroups) !== JSON.stringify(breakpointGroups) || !groupsEl.childElementCount) {
        breakpointGroups = { ...nextGroups };
        paintGroups(breakpointGroups);
      } else {
        breakpointGroups = { ...nextGroups };
      }
      backBtn.disabled = Boolean(st.timeline && st.timeline.viewing) && !st.supportsStepBack;
      backBtn.title = st.supportsStepBack
        ? "DAP stepBack / reverse"
        : "Seek timeline previous snapshot (install rr for true reverse)";
      if (st.childSessionIds && st.childSessionIds.length) {
        stateEl.textContent += ` · children ${st.childSessionIds.length}`;
      }
    };

    const refresh = async () => {
      try {
        const q = activeDebugSessionId ? `?sessionId=${encodeURIComponent(activeDebugSessionId)}` : "";
        const st = await api("GET", `/api/debug/status${q}`);
        paintState(st);
      } catch (e) {
        stateEl.textContent = String(e.message || e);
      }
    };

    sessSelect.onchange = async () => {
      activeDebugSessionId = sessSelect.value;
      if (!activeDebugSessionId) return;
      try {
        paintState(await api("POST", "/api/debug/active", { sessionId: activeDebugSessionId }));
      } catch (e) {
        alert(e.message || e);
      }
    };
    startBtn.onclick = async () => {
      try {
        if (activePath) await saveActive();
        const payload = {};
        const sel = launchSelect.value;
        if (sel.startsWith("compound:")) {
          payload.compoundName = sel.slice("compound:".length);
          if (activePath) payload.path = activePath;
        } else if (sel) {
          payload.configName = sel;
          if (activePath) payload.path = activePath;
        } else if (activePath) {
          payload.path = activePath;
        } else {
          return alert("Open a file or pick a launch config");
        }
        const st = await api("POST", "/api/debug/start", payload);
        paintState(st);
      } catch (e) {
        alert(e.message || e);
      }
    };
    launchEnsure.onclick = async () => {
      try {
        const cur = await api("GET", "/api/debug/launch");
        if ((cur.configurations || []).length) {
          fillLaunchSelect(cur.configurations, undefined, cur.compounds || []);
          return;
        }
      } catch {
        /* write defaults */
      }
      try {
        const res = await api("POST", "/api/debug/launch", {
          version: "0.2.0",
          configurations: [
            {
              name: "Python: current file",
              type: "python",
              request: "launch",
              program: "${file}",
              cwd: "${workspaceFolder}",
              stopOnEntry: true,
            },
            {
              name: "Node: current file",
              type: "node",
              request: "launch",
              program: "${file}",
              cwd: "${workspaceFolder}",
              stopOnEntry: true,
            },
            {
              name: "Python: attach",
              type: "python",
              request: "attach",
              host: "127.0.0.1",
              port: 5678,
            },
            {
              name: "Node: attach",
              type: "node",
              request: "attach",
              host: "127.0.0.1",
              port: 9229,
            },
          ],
        });
        fillLaunchSelect(res.configurations || []);
        setStatus(activePath || "debug", `Wrote ${res.path || ".zintriq/launch.json"}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    launchSave.onclick = async () => {
      try {
        const cur = await api("GET", "/api/debug/launch");
        const res = await api("POST", "/api/debug/launch", {
          version: cur.version || "0.2.0",
          configurations: launchConfigs.length ? launchConfigs : cur.configurations || [],
          compounds: launchCompounds.length ? launchCompounds : cur.compounds || [],
        });
        fillLaunchSelect(res.configurations || [], undefined, res.compounds || []);
        setStatus(activePath || "debug", `Saved ${res.path || "launch.json"}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    testBtn.onclick = async () => {
      try {
        if (!activePath) return alert("Open a test file");
        await saveActive();
        const xdist = /\.py$/.test(activePath) && confirm("Use pytest-xdist (-n auto)?");
        paintState(
          await api("POST", "/api/debug/test", {
            path: activePath,
            xdist: Boolean(xdist),
            workers: "auto",
          })
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const stopCompoundBtn = mkBtn("Stop compound");
    stopCompoundBtn.onclick = async () => {
      try {
        const name = prompt("Compound name to stopAll:");
        if (!name) return;
        paintState(await api("POST", "/api/debug/compound/stop", { name }));
      } catch (e) {
        alert(e.message || e);
      }
    };
    const gotoBtn = mkBtn("Goto line");
    gotoBtn.onclick = async () => {
      try {
        if (!activePath) return;
        const pos = offsetToPos(editor.value, editor.selectionStart || 0);
        const targets = await api("POST", "/api/debug/gotoTargets", {
          path: activePath,
          line: pos.line + 1,
          ...sidPayload(),
        });
        const list = targets.targets || [];
        if (!list.length) return alert("No goto targets");
        paintState(
          await api("POST", "/api/debug/goto", {
            targetId: list[0].id,
            path: activePath,
            line: pos.line + 1,
            ...sidPayload(),
          })
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const restartFrameBtn = mkBtn("Restart frame");
    restartFrameBtn.onclick = async () => {
      try {
        paintState(
          await api("POST", "/api/debug/restartFrame", {
            frameId: selectedDebugFrameId,
            ...sidPayload(),
          })
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const sourcemapBtn = mkBtn("Sourcemap");
    sourcemapBtn.onclick = async () => {
      try {
        if (!activePath) return;
        const pos = offsetToPos(editor.value, editor.selectionStart || 0);
        const res = await api("POST", "/api/debug/sourcemap", {
          path: activePath,
          line: pos.line + 1,
          column: pos.character || 0,
        });
        const orig = res.original || {};
        if (orig.path) {
          await openFile(orig.path);
          setStatus(orig.path, `← ${activePath}:${pos.line + 1} → ${orig.path}:${orig.line}`);
        } else {
          alert(JSON.stringify(res));
        }
      } catch (e) {
        alert(e.message || e);
      }
    };
    postBtn.onclick = async () => {
      try {
        const path =
          activePath ||
          prompt("Traceback / dump path (workspace-relative):", "traceback.txt");
        if (!path) return;
        paintState(await api("POST", "/api/debug/postmortem", { path }));
      } catch (e) {
        alert(e.message || e);
      }
    };
    const covSummaryEl = document.createElement("div");
    covSummaryEl.className = "debug-cov-summary";
    const paintCovSummary = async () => {
      try {
        const sum = await api("GET", "/api/debug/coverage/summary");
        covSummaryEl.innerHTML = "";
        const tot = sum.totals || {};
        const head = document.createElement("div");
        head.className = "meta";
        head.textContent = `Coverage ${tot.pct ?? "—"}% · ${tot.hits || 0} hit / ${tot.misses || 0} miss`;
        covSummaryEl.appendChild(head);
        for (const f of (sum.files || []).slice(0, 40)) {
          const row = document.createElement("div");
          row.className = "debug-cov-file";
          row.textContent = `${f.pct}%  ${f.path}  (+${f.hits}/-${f.misses})`;
          row.onclick = () => openFile(f.path);
          covSummaryEl.appendChild(row);
        }
      } catch {
        /* ignore */
      }
    };
    covBtn.onclick = async () => {
      try {
        if (!activePath) return alert("Open a file to cover");
        await saveActive();
        const res = await api("POST", "/api/debug/coverage", { path: activePath });
        if (res.files) applyCoverageFiles(res.files);
        await paintCovSummary();
        setStatus(activePath, `Coverage updated`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const covTipBtn = mkBtn("Save tip");
    const covDiffBtn = mkBtn("Diff tip");
    covTipBtn.onclick = async () => {
      try {
        await api("POST", "/api/debug/coverage/tip", {});
        setStatus(activePath || "debug", "Coverage tip saved");
      } catch (e) {
        alert(e.message || e);
      }
    };
    covDiffBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/coverage/tip", { diff: true });
        covSummaryEl.innerHTML = "";
        const head = document.createElement("div");
        head.className = "meta";
        head.textContent = `vs tip · ${res.changedFiles || 0} file(s)`;
        covSummaryEl.appendChild(head);
        for (const d of res.diff || []) {
          const row = document.createElement("div");
          row.className = "debug-cov-file";
          row.textContent = `${d.path}: +${(d.gained || []).length} / -${(d.lost || []).length}`;
          covSummaryEl.appendChild(row);
        }
      } catch (e) {
        alert(e.message || e);
      }
    };
    const covHtmlBtn = mkBtn("HTML report");
    covHtmlBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/coverage/html");
        setStatus(activePath || "debug", `Coverage HTML → ${res.path}`);
        if (res.path) window.open(`/editor#${res.path}`, "_blank");
      } catch (e) {
        alert(e.message || e);
      }
    };
    const flameEl = document.createElement("div");
    flameEl.className = "debug-flame";
    let flameRoot = null;
    let flameFocus = null;
    let flameProfileId = "";
    const renderFlame = (node, depth, maxVal) => {
      if (!node) return;
      const row = document.createElement("div");
      row.className = "debug-flame-row";
      const pct = maxVal ? (Number(node.value) || 0) / maxVal : 0;
      row.style.setProperty("--w", `${Math.max(2, pct * 100)}%`);
      row.style.paddingLeft = `${Math.min(depth, 12) * 8}px`;
      row.title = `Click to zoom · ${node.name} · ${node.value}${
        node.self != null ? ` (self ${node.self})` : ""
      }`;
      row.textContent = `${node.name}  ${node.value}`;
      row.onclick = () => {
        flameFocus = node;
        paintFlame();
      };
      flameEl.appendChild(row);
      for (const ch of node.children || []) renderFlame(ch, depth + 1, maxVal);
    };
    const paintFlame = () => {
      const node = flameFocus || flameRoot;
      if (!node) return;
      flameEl.innerHTML = "";
      const bar = document.createElement("div");
      bar.className = "row";
      const reset = document.createElement("button");
      reset.textContent = "Reset zoom";
      reset.onclick = () => {
        flameFocus = null;
        paintFlame();
      };
      const exp = document.createElement("button");
      exp.textContent = "Speedscope JSON";
      exp.onclick = async () => {
        if (!flameProfileId) return;
        try {
          const res = await api(
            "GET",
            `/api/debug/profiles/${encodeURIComponent(flameProfileId)}/speedscope`
          );
          const blob = new Blob([JSON.stringify(res.speedscope, null, 2)], {
            type: "application/json",
          });
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `profile-${flameProfileId}.speedscope.json`;
          a.click();
          URL.revokeObjectURL(a.href);
        } catch (e) {
          alert(e.message || e);
        }
      };
      const iframeBtn = document.createElement("button");
      iframeBtn.textContent = "Speedscope preview";
      iframeBtn.onclick = async () => {
        if (!flameProfileId) return;
        try {
          const desktop = window.zintriqDesktop;
          const token = desktop && (await desktop.getToken());
          const rawUrl = `${location.origin}/api/debug/profiles/${encodeURIComponent(
            flameProfileId
          )}/speedscope/raw${token ? `?token=${encodeURIComponent(token)}` : ""}`;
          const src = `https://www.speedscope.app/#profileURL=${encodeURIComponent(rawUrl)}`;
          let frame = flameEl.querySelector("iframe.debug-speedscope");
          if (!frame) {
            frame = document.createElement("iframe");
            frame.className = "debug-speedscope";
            frame.title = "Speedscope";
            flameEl.appendChild(frame);
          }
          frame.src = src;
        } catch (e) {
          alert(e.message || e);
        }
      };
      bar.append(reset, exp, iframeBtn);
      flameEl.appendChild(bar);
      renderFlame(node, 0, Number(node.value) || 1);
    };
    let allocTimeline = [];
    const allocScrub = document.createElement("div");
    allocScrub.className = "debug-alloc-scrub";
    const showProfile = async (id) => {
      try {
        const res = await api("GET", `/api/debug/profiles/${encodeURIComponent(id)}`);
        flameProfileId = id;
        flameRoot = res.flame || (res.payload && res.payload.flame);
        flameFocus = null;
        allocTimeline = res.timeline || [];
        allocScrub.innerHTML = "";
        if (allocTimeline.length) {
          const lab = document.createElement("span");
          lab.className = "meta";
          lab.textContent = "Alloc timeline";
          const range = document.createElement("input");
          range.type = "range";
          range.min = "0";
          range.max = String(Math.max(0, allocTimeline.length - 1));
          range.value = range.max;
          const meta = document.createElement("span");
          meta.className = "meta";
          const paintAlloc = () => {
            const sample = allocTimeline[Number(range.value) || 0];
            meta.textContent = sample
              ? `#${sample.i} size=${sample.size} cum=${sample.cumulative}`
              : "";
          };
          range.oninput = paintAlloc;
          paintAlloc();
          allocScrub.append(lab, range, meta);
        }
        if (!flameRoot) {
          flameEl.textContent = res.payload && res.payload.text
            ? String(res.payload.text).slice(0, 4000)
            : "(no flame data)";
          return;
        }
        paintFlame();
        if (allocScrub.childElementCount) flameEl.appendChild(allocScrub);
      } catch (e) {
        flameEl.textContent = String(e.message || e);
      }
    };
    const runProfile = (kind) => async () => {
      try {
        await api("POST", "/api/debug/profile/start", { kind, ...sidPayload() });
        setStatus(activePath || "debug", `${kind} profiling… click again to stop`);
        const stop = async () => {
          try {
            const res = await api("POST", "/api/debug/profile/stop", { kind, ...sidPayload() });
            setStatus(activePath || "debug", `Profile saved ${res.id || ""}`);
            if (res.id) await showProfile(res.id);
            refresh();
          } catch (e) {
            alert(e.message || e);
          }
        };
        if (kind === "heap") {
          await stop();
          return;
        }
        profCpuBtn.textContent = "Stop CPU";
        profCpuBtn.onclick = async () => {
          await stop();
          profCpuBtn.textContent = "CPU profile";
          profCpuBtn.onclick = runProfile("cpu");
        };
      } catch (e) {
        alert(e.message || e);
      }
    };
    const profAllocBtn = mkBtn("Alloc flame");
    profCpuBtn.onclick = runProfile("cpu");
    profHeapBtn.onclick = runProfile("heap");
    profAllocBtn.onclick = runProfile("allocation");
    const diffRow = document.createElement("div");
    diffRow.className = "row";
    const diffA = document.createElement("select");
    const diffB = document.createElement("select");
    const diffC = document.createElement("select");
    diffC.innerHTML = `<option value="">(optional 3rd)</option>`;
    const diffBtn = mkBtn("Diff vars");
    const diffEl = document.createElement("div");
    diffEl.className = "debug-var-diff";
    diffRow.append(diffA, diffB, diffC, diffBtn);
    const fillDiffSelects = (sessions) => {
      const curA = diffA.value;
      const curB = diffB.value;
      const curC = diffC.value;
      diffA.innerHTML = "";
      diffB.innerHTML = "";
      diffC.innerHTML = `<option value="">(optional 3rd+)</option>`;
      for (const s of sessions || []) {
        const id = s.id || s.sessionId;
        for (const sel of [diffA, diffB, diffC]) {
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = `${s.configName || s.path || id} · ${s.engine || ""}`;
          sel.appendChild(opt);
        }
      }
      if (curA) diffA.value = curA;
      if (curB) diffB.value = curB;
      if (curC) diffC.value = curC;
      if (!diffB.value && (sessions || []).length > 1) diffB.selectedIndex = 1;
    };
    diffBtn.onclick = async () => {
      try {
        const ids = [diffA.value, diffB.value, diffC.value].filter(Boolean);
        const payload =
          ids.length >= 3
            ? { sessionIds: ids }
            : { sessionA: diffA.value, sessionB: diffB.value };
        const res = await api("POST", "/api/debug/diff", payload);
        diffEl.innerHTML = "";
        const meta = document.createElement("div");
        meta.className = "meta";
        if (res.mode === "matrix") {
          meta.textContent = `matrix ${res.changed || 0} differing · ${(res.sessionIds || []).join(" · ")}`;
          diffEl.appendChild(meta);
          for (const row of res.matrix || []) {
            const d = document.createElement("div");
            d.className = `debug-diff-row ${row.status}`;
            d.textContent = `${row.name}: ${(row.values || []).map((v) => v ?? "—").join(" | ")}`;
            diffEl.appendChild(d);
          }
        } else {
          meta.textContent = `${res.changed || 0} differing · ${res.sessionA} vs ${res.sessionB}`;
          diffEl.appendChild(meta);
          for (const row of res.diff || []) {
            const d = document.createElement("div");
            d.className = `debug-diff-row ${row.status}`;
            d.textContent = `${row.name}: ${row.a ?? "—"} ${row.status === "same" ? "=" : "≠"} ${
              row.b ?? "—"
            }`;
            diffEl.appendChild(d);
          }
        }
      } catch (e) {
        alert(e.message || e);
      }
    };
    const sourcesEl = document.createElement("div");
    sourcesEl.className = "debug-sources";
    const refreshSources = async () => {
      try {
        const q = activeDebugSessionId
          ? `?sessionId=${encodeURIComponent(activeDebugSessionId)}`
          : "";
        const res = await api("GET", `/api/debug/sources${q}`);
        sourcesEl.innerHTML = "";
        for (const s of res.sources || []) {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = s.path || s.name;
          b.onclick = () => {
            if (s.path && !String(s.path).startsWith("(")) openFile(s.path);
          };
          sourcesEl.appendChild(b);
        }
        if (!(res.sources || []).length) {
          const d = document.createElement("div");
          d.className = "meta";
          d.textContent = "(no loaded sources)";
          sourcesEl.appendChild(d);
        }
      } catch (e) {
        sourcesEl.textContent = String(e.message || e);
      }
    };
    const bpIoRow = document.createElement("div");
    bpIoRow.className = "row";
    const bpExport = mkBtn("Export BPs");
    const bpImport = mkBtn("Import BPs");
    bpExport.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/breakpoints/export");
        const blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "breakpoints.json";
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) {
        alert(e.message || e);
      }
    };
    bpImport.onclick = async () => {
      const text = prompt("Paste breakpoints JSON (VS Code / Zintriq):");
      if (text == null || !text.trim()) return;
      try {
        const doc = JSON.parse(text);
        const res = await api("POST", "/api/debug/breakpoints/import", { ...doc, merge: true });
        if (res.breakpoints) breakpoints = res.breakpoints;
        if (activePath && buffers.has(activePath)) renderFoldGutter(buffers.get(activePath));
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    bpIoRow.append(bpExport, bpImport);
    const renameBtn = mkBtn("Rename session");
    renameBtn.onclick = async () => {
      if (!activeDebugSessionId) return;
      const name = prompt("Session display name:", "");
      if (name == null || !name.trim()) return;
      try {
        paintState(
          await api("POST", "/api/debug/session/rename", {
            sessionId: activeDebugSessionId,
            name,
          })
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    timelineRange.oninput = async () => {
      try {
        paintState(
          await api("POST", "/api/debug/timeline", {
            index: Number(timelineRange.value) || 0,
            ...sidPayload(),
          })
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    timelineLive.onclick = async () => {
      try {
        paintState(await api("POST", "/api/debug/timeline", { live: true, ...sidPayload() }));
      } catch (e) {
        alert(e.message || e);
      }
    };
    attachBtn.onclick = async () => {
      try {
        const clean = pathMappings.filter((x) => x.localRoot && x.remoteRoot);
        const st = await api("POST", "/api/debug/attach", {
          engine: engSelect.value,
          host: hostInput.value || "127.0.0.1",
          port: Number(portInput.value) || 0,
          path: activePath || "(remote)",
          pathMappings: clean,
        });
        paintState(st);
      } catch (e) {
        alert(e.message || e);
      }
    };
    engSelect.onchange = () => {
      if (engSelect.value === "node" && (portInput.value === "5678" || !portInput.value)) {
        portInput.value = "9229";
      } else if (engSelect.value === "python" && (portInput.value === "9229" || !portInput.value)) {
        portInput.value = "5678";
      }
    };
    stopBtn.onclick = async () => {
      try {
        paintState(await api("POST", "/api/debug/stop", sidPayload()));
      } catch (e) {
        alert(e.message || e);
      }
    };
    stopAllBtn.onclick = async () => {
      try {
        paintState(await api("POST", "/api/debug/stop", {}));
        activeDebugSessionId = "";
      } catch (e) {
        alert(e.message || e);
      }
    };
    const step = (path) => async () => {
      try {
        paintState(await api("POST", path, sidPayload()));
      } catch (e) {
        alert(e.message || e);
      }
    };
    contBtn.onclick = step("/api/debug/continue");
    nextBtn.onclick = step("/api/debug/stepOver");
    inBtn.onclick = step("/api/debug/stepIn");
    outBtn.onclick = step("/api/debug/stepOut");
    backBtn.onclick = step("/api/debug/stepBack");
    revContBtn.onclick = step("/api/debug/reverseContinue");
    bpBtn.onclick = () => {
      const pos = offsetToPos(editor.value, editor.selectionStart || 0);
      toggleBreakpointAt(pos.line + 1);
    };
    condBtn.onclick = () => {
      const pos = offsetToPos(editor.value, editor.selectionStart || 0);
      editBreakpointCondition(pos.line + 1);
    };
    hitBtn.onclick = () => {
      const pos = offsetToPos(editor.value, editor.selectionStart || 0);
      editBreakpointHitCount(pos.line + 1);
    };
    logBtn.onclick = () => {
      const pos = offsetToPos(editor.value, editor.selectionStart || 0);
      editBreakpointLogMessage(pos.line + 1);
    };
    disasmBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/disassemble", { ...sidPayload(), count: 80 });
        memOut.textContent = res.text || res.error || "(empty)";
      } catch (e) {
        memOut.textContent = String(e.message || e);
      }
    };
    memBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/memory", {
          expression: memInput.value,
          count: 128,
          ...sidPayload(),
        });
        memOut.textContent = res.text || res.error || "(empty)";
      } catch (e) {
        memOut.textContent = String(e.message || e);
      }
    };
    const memWriteBtn = mkBtn("Write mem");
    memWriteBtn.onclick = async () => {
      const ref = prompt("memoryReference");
      const data = prompt("hex or base64 bytes");
      if (!ref || !data) return;
      try {
        const res = await api("POST", "/api/debug/memory", {
          memoryReference: ref,
          data,
          write: true,
          ...sidPayload(),
        });
        memOut.textContent = `wrote ${res.bytesWritten || 0} bytes`;
      } catch (e) {
        memOut.textContent = String(e.message || e);
      }
    };
    memRow.append(memWriteBtn);
    const setExprBtn = mkBtn("Set expr");
    setExprBtn.onclick = async () => {
      const expression = prompt("expression to assign");
      const value = prompt("new value (literal)");
      if (!expression) return;
      try {
        await api("POST", "/api/debug/setExpression", {
          expression,
          value: value || "None",
          ...sidPayload(),
        });
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    const bpLocBtn = mkBtn("BP columns");
    bpLocBtn.onclick = async () => {
      const pos = offsetToPos(editor.value, editor.selectionStart || 0);
      try {
        const res = await api("POST", "/api/debug/breakpointLocations", {
          path: activePath,
          line: pos.line + 1,
          ...sidPayload(),
        });
        const locs = res.locations || [];
        setStatus(
          activePath || "debug",
          locs.length
            ? `breakpointLocations: ${locs.map((l) => `col ${l.column}`).join(", ")}`
            : "no column locations"
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const scanBtn = mkBtn("Scan ports");
    scanBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/ports/scan", {
          host: hostInput.value || "127.0.0.1",
        });
        const open = res.open || [];
        setStatus(
          activePath || "debug",
          open.length
            ? `open: ${open.map((p) => `${p.port}(${p.kind})`).join(", ")}`
            : "no debug ports open"
        );
        if (open[0]) portInput.value = String(open[0].port);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const tmplBtn = mkBtn("Log templates");
    tmplBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/logpointTemplates");
        const templates = res.templates || [];
        const labels = templates.map((t, i) => `${i + 1}. ${t.label}: ${t.logMessage}`).join("\n");
        const pick = prompt(`Logpoint templates (team-shared):\n${labels}\n\nEnter # to apply, or new message`);
        if (!pick) return;
        const n = Number(pick);
        let msg = pick;
        if (n >= 1 && n <= templates.length) msg = templates[n - 1].logMessage;
        const pos = offsetToPos(editor.value, editor.selectionStart || 0);
        await api("POST", "/api/debug/breakpoints/log", {
          path: activePath,
          line: pos.line + 1,
          logMessage: msg,
        });
        if (!res.shared && confirm("Save templates to .zintriq for team share?")) {
          await api("POST", "/api/debug/logpointTemplates", { templates });
        }
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    const wasmBtn = mkBtn("WASM DWARF");
    wasmBtn.onclick = async () => {
      if (!activePath || !/\.wasm$/i.test(activePath)) {
        alert("Open a .wasm file first");
        return;
      }
      try {
        const res = await api("POST", "/api/debug/wasm/dwarf", { path: activePath });
        setStatus(
          activePath,
          res.hasDwarf
            ? `DWARF: ${(res.dwarfSections || []).map((s) => s.name).join(", ")}`
            : res.hint || "no DWARF"
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const otelBtn = mkBtn("OTel spans");
    otelBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/otel/spans");
        const spans = res.spans || [];
        eventsEl.textContent =
          spans
            .slice(-30)
            .map((s) => `${s.name} sid=${(s.attributes || {})["debug.session_id"] || ""}`)
            .join("\n") || "(no otel spans)";
      } catch (e) {
        alert(e.message || e);
      }
    };
    const modulesEl = document.createElement("pre");
    modulesEl.className = "debug-modules";
    modulesEl.textContent = "(modules)";
    const modulesBtn = mkBtn("Modules");
    modulesBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/modules" + (activeDebugSessionId ? `?sessionId=${activeDebugSessionId}` : ""));
        modulesEl.textContent = (res.modules || [])
          .map((m) => `${m.name || m.id || "?"}  ${m.path || ""}`)
          .join("\n") || "(empty)";
      } catch (e) {
        modulesEl.textContent = String(e.message || e);
      }
    };
    const hotBtn = mkBtn("Hot reload");
    hotBtn.onclick = async () => {
      try {
        const mod = prompt("Module to reload (empty = current)") || "";
        const res = await api("POST", "/api/debug/hotReload", { module: mod, ...sidPayload() });
        setStatus(activePath || "debug", String(res.result || "reloaded"));
      } catch (e) {
        alert(e.message || e);
      }
    };
    const varHistEl = document.createElement("pre");
    varHistEl.className = "debug-modules";
    const varHistBtn = mkBtn("Var history");
    varHistBtn.onclick = async () => {
      try {
        const res = await api(
          "GET",
          "/api/debug/varHistory" + (activeDebugSessionId ? `?sessionId=${activeDebugSessionId}` : "")
        );
        varHistEl.textContent = (res.diffs || [])
          .slice(-20)
          .map((d) => {
            const ch = (d.changed || []).slice(0, 4).map((c) => `${c.name}: ${c.from}→${c.to}`).join("; ");
            return `#${d.i} ${ch || "(no change)"}`;
          })
          .join("\n") || "(no diffs yet)";
      } catch (e) {
        varHistEl.textContent = String(e.message || e);
      }
    };
    const matrixEl = document.createElement("pre");
    matrixEl.className = "debug-matrix";
    const matrixBtn = mkBtn("Subproc matrix");
    matrixBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/subprocessMatrix");
        matrixEl.textContent = (res.matrix || [])
          .map((r) => `${r.role} ${r.sessionId} ${r.label} ${r.alive ? "●" : "○"} ${r.stopped ? "⏸" : ""}`)
          .join("\n") || "(no sessions)";
      } catch (e) {
        matrixEl.textContent = String(e.message || e);
      }
    };
    const tunnelBtn = mkBtn("SSH tunnels");
    tunnelBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/ssh/tunnels");
        matrixEl.textContent = (res.tunnels || [])
          .map((t) => `${t.key} pid=${t.pid}${t.multiHop ? " · multi-hop" : ""}`)
          .join("\n") || "(no tunnels)";
      } catch (e) {
        matrixEl.textContent = String(e.message || e);
      }
    };
    const compoundGraphEl = document.createElement("pre");
    compoundGraphEl.className = "debug-mermaid";
    const compoundGraphBtn = mkBtn("Compounds graph");
    compoundGraphBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/compounds/graph");
        compoundGraphEl.textContent = res.mermaid || JSON.stringify(res.nodes || [], null, 0);
      } catch (e) {
        compoundGraphEl.textContent = String(e.message || e);
      }
    };
    const otlpBtn = mkBtn("OTLP export");
    otlpBtn.onclick = async () => {
      try {
        const endpoint = prompt("OTLP HTTP endpoint (optional)", "") || "";
        const res = await api("POST", "/api/debug/otel/export", { endpoint });
        setStatus(activePath || "debug", `OTLP → ${res.path} spans=${res.spanCount}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const recBtn = mkBtn("Rec session");
    recBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/replay/start", sidPayload());
        setStatus(activePath || "debug", `Recording ${res.replayId}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const recStopBtn = mkBtn("Stop rec");
    recStopBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/replay/stop", sidPayload());
        setStatus(activePath || "debug", res.replayId ? `Saved ${res.replayId}` : "not recording");
      } catch (e) {
        alert(e.message || e);
      }
    };
    const replayBtn = mkBtn("Load replay");
    replayBtn.onclick = async () => {
      try {
        const list = await api("GET", "/api/debug/replay");
        const ids = (list.recordings || []).map((r) => r.id);
        if (!ids.length) return alert("No recordings in .zintriq/replay");
        const id = prompt("Replay id:\n" + ids.join("\n"), ids[0]);
        if (!id) return;
        paintState(await api("POST", "/api/debug/replay/load", { id }));
      } catch (e) {
        alert(e.message || e);
      }
    };
    const instrBtn = mkBtn("Instr BP");
    instrBtn.onclick = async () => {
      const ref = prompt("instructionReference / address");
      if (!ref) return;
      try {
        await api("POST", "/api/debug/instructionBreakpoints", {
          instructionReference: ref,
          ...sidPayload(),
        });
        setStatus(activePath || "debug", `instruction BP @ ${ref}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const hwWatchBtn = mkBtn("HW watch");
    hwWatchBtn.onclick = async () => {
      const expression = prompt("gdb hardware watch expression");
      if (!expression) return;
      try {
        const res = await api("POST", "/api/debug/hardwareWatch", { expression, access: "write" });
        setStatus(activePath || "debug", res.ok ? `watch ${expression}` : res.error || "failed");
      } catch (e) {
        alert(e.message || e);
      }
    };
    const dwarfInjBtn = mkBtn("DWARF inject");
    dwarfInjBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/chrome/dwarfInject");
        setStatus(activePath || "debug", res.path + " — " + (res.hint || ""));
      } catch (e) {
        alert(e.message || e);
      }
    };
    const nbBtn = mkBtn("Notebook cells");
    nbBtn.onclick = async () => {
      if (!activePath || !/\.ipynb$/i.test(activePath)) {
        alert("Open a .ipynb first");
        return;
      }
      try {
        const res = await api("POST", "/api/debug/notebook/cells", { path: activePath });
        modulesEl.textContent = (res.cells || [])
          .map((c) => `[${c.index}] ${c.cell_type} ${c.preview}`)
          .join("\n");
      } catch (e) {
        alert(e.message || e);
      }
    };
    const roCb = document.createElement("input");
    roCb.type = "checkbox";
    const roLab = document.createElement("label");
    roLab.append(roCb, document.createTextNode(" Read-only attach"));
    roCb.onchange = async () => {
      try {
        await api("POST", "/api/debug/readonly", { readonly: roCb.checked });
      } catch (e) {
        alert(e.message || e);
      }
    };
    const stepTargetBtn = mkBtn("StepIn targets");
    stepTargetBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/stepInTargets", sidPayload());
        const targets = res.targets || [];
        if (!targets.length) {
          setStatus(activePath || "debug", "no stepInTargets");
          return;
        }
        const labels = targets.map((t, i) => `${i + 1}. ${t.label}`).join("\n");
        const pick = prompt(`Step into:\n${labels}`, "1");
        const n = Number(pick) - 1;
        if (n >= 0 && n < targets.length) {
          paintState(
            await api("POST", "/api/debug/stepInTarget", {
              targetId: targets[n].id,
              ...sidPayload(),
            })
          );
        }
      } catch (e) {
        alert(e.message || e);
      }
    };
    const fnBpBtn = mkBtn("Fn BP");
    fnBpBtn.onclick = async () => {
      const name = prompt("Function name breakpoint");
      if (!name) return;
      try {
        await api("POST", "/api/debug/functionBreakpoints", { name });
        setStatus(activePath || "debug", `function BP ${name}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const pinBtn = mkBtn("Pin var");
    pinBtn.onclick = async () => {
      const expression = prompt("Pin expression for inline display");
      if (!expression) return;
      try {
        await api("POST", "/api/debug/pins", { expression });
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    const shareBtn = mkBtn("Live share");
    shareBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/liveShare/publish", sidPayload());
        setStatus(activePath || "debug", `Live share room ${res.room} (read-only)`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const platformBtn = mkBtn("Lang/HW/Ext");
    platformBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/platform");
        const langs = (res.languages || [])
          .filter((l) => l.available)
          .map((l) => l.id)
          .join(", ");
        const hw = (res.hardware || [])
          .filter((h) => h.available)
          .map((h) => h.id)
          .join(", ");
        const ex = (res.extensions || []).map((e) => e.id).join(", ");
        modulesEl.textContent = `languages: ${langs || "—"}\nhardware: ${hw || "—"}\nextensions: ${ex || "—"}\npresets: ${(res.presets || []).length}`;
      } catch (e) {
        alert(e.message || e);
      }
    };
    const extBtn = mkBtn("+ Extension");
    extBtn.onclick = async () => {
      const id = prompt("Extension id (e.g. my-lang-debug)");
      if (!id) return;
      try {
        const res = await api("POST", "/api/debug/extensions/install", { id, label: id });
        setStatus(activePath || "debug", `Installed ${res.path}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const triageBtn = mkBtn("Triage");
    triageBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/triage", {});
        setStatus(activePath || "debug", `${res.markdown}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const vaultBtn = mkBtn("Vault");
    vaultBtn.onclick = async () => {
      const key = prompt("Secret key (use ${vault:KEY} in launch env)");
      if (!key) return;
      const value = prompt("Secret value");
      if (value == null) return;
      try {
        const res = await api("POST", "/api/debug/vault", { key, value });
        setStatus(activePath || "debug", `vault keys: ${(res.keys || []).join(", ")}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const catchBtn = mkBtn("Catch throw");
    catchBtn.onclick = async () => {
      try {
        const cur = await api("GET", "/api/debug/catchpoints");
        const on = !(cur.catchpoints && cur.catchpoints.throw);
        const sig = prompt("Also catch signals (comma, e.g. SIGSEGV)", (cur.catchpoints && cur.catchpoints.signals || []).join(","));
        await api("POST", "/api/debug/catchpoints", {
          throw: on,
          signals: (sig || "").split(",").map((s) => s.trim()).filter(Boolean),
        });
        setStatus(activePath || "debug", `catch throw=${on}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const replayDiffBtn = mkBtn("Replay diff");
    replayDiffBtn.onclick = async () => {
      try {
        const list = await api("GET", "/api/debug/replay");
        const ids = (list.recordings || []).map((r) => r.id);
        if (ids.length < 2) return alert("Need ≥2 recordings");
        const a = prompt("Replay A", ids[0]);
        const b = prompt("Replay B", ids[1]);
        const res = await api("POST", "/api/debug/replay/diff", { a, b });
        varHistEl.textContent = JSON.stringify(
          { stackEqual: res.stackEqual, varDiff: res.varDiff, eventCount: res.eventCount },
          null,
          2
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const sbomBtn = mkBtn("SBOM");
    sbomBtn.onclick = async () => {
      try {
        const res = await api("POST", "/api/debug/sbom", { path: ".zintriq/sbom.json" });
        setStatus(activePath || "debug", `SBOM vulns=${res.count}`);
      } catch (e) {
        alert(e.message || e);
      }
    };
    const budgetBtn = mkBtn("Perf budget");
    budgetBtn.onclick = async () => {
      try {
        const profiles = (await api("GET", "/api/debug/profiles")).profiles || [];
        const id = profiles.length ? profiles[profiles.length - 1].id : "";
        const res = await api("POST", "/api/debug/profile/budget", { id });
        setStatus(
          activePath || "debug",
          res.ok ? `budget OK → ${res.path}` : `budget FAIL ${ (res.violations || []).length } → ${res.path}`
        );
      } catch (e) {
        alert(e.message || e);
      }
    };
    const traceQBtn = mkBtn("Trace query");
    traceQBtn.onclick = async () => {
      const q = prompt("Tracepoint query");
      if (q == null) return;
      try {
        const res = await api("GET", `/api/debug/tracepoints?q=${encodeURIComponent(q)}`);
        modulesEl.textContent = (res.results || [])
          .map((r) => `${r.path}:${r.line} ${r.message}`)
          .join("\n") || "(no hits)";
      } catch (e) {
        alert(e.message || e);
      }
    };
    const mergeBpBtn = mkBtn("Merge BPs");
    mergeBpBtn.onclick = async () => {
      const raw = prompt("Paste remote breakpoints JSON {path:[{line,...}]}");
      if (!raw) return;
      try {
        const remote = JSON.parse(raw);
        const res = await api("POST", "/api/debug/breakpoints/merge", {
          remote,
          strategy: "union",
          apply: true,
        });
        setStatus(
          activePath || "debug",
          `merged; conflicts=${(res.conflicts || []).length}`
        );
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    const sabBtn = mkBtn("SAB/Worker");
    sabBtn.onclick = async () => {
      try {
        const res = await api("GET", "/api/debug/sab");
        modulesEl.textContent = JSON.stringify(res, null, 2);
      } catch (e) {
        alert(e.message || e);
      }
    };
    watchAdd.onclick = async () => {
      try {
        const group = prompt("Watch group (default)", "default") || "default";
        await api("POST", "/api/debug/watchGroups", {
          expression: watchInput.value,
          group,
        });
        watchInput.value = "";
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    dataBpAdd.onclick = async () => {
      try {
        await api("POST", "/api/debug/dataBreakpoints", {
          name: dataBpInput.value,
          accessType: "write",
        });
        dataBpInput.value = "";
        refresh();
      } catch (e) {
        alert(e.message || e);
      }
    };
    const runEval = async () => {
      try {
        const res = await api("POST", "/api/debug/evaluate", {
          expression: evalInput.value,
          ...sidPayload(),
        });
        evalInput.value = "";
        refresh();
        if (res.result) setStatus(activePath || "debug", String(res.result.value));
      } catch (e) {
        alert(e.message || e);
      }
    };
    evalBtn.onclick = runEval;
    evalInput.onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runEval();
      }
    };

    const toolsRow = document.createElement("div");
    toolsRow.className = "row";
    const flameSec = makeDebugSection("Flame graph", "showConsole", flameEl);
    const diffSec = makeDebugSection("Session var diff", "showVars", diffEl);
    const covSec = makeDebugSection("Coverage summary", "showConsole", covSummaryEl);
    const sourcesWrap = document.createElement("div");
    const srcBtn = mkBtn("Refresh sources");
    srcBtn.onclick = refreshSources;
    sourcesWrap.append(srcBtn, sourcesEl);
    const sourcesSec = makeDebugSection("Loaded sources", "showStack", sourcesWrap);
    const covTools = document.createElement("div");
    covTools.className = "row";
    covTools.append(covTipBtn, covDiffBtn, covHtmlBtn);
    toolsRow.append(
      testBtn,
      stopCompoundBtn,
      postBtn,
      covBtn,
      profCpuBtn,
      profHeapBtn,
      profAllocBtn,
      renameBtn,
      gotoBtn,
      restartFrameBtn,
      sourcemapBtn,
      scanBtn,
      tmplBtn,
      wasmBtn,
      otelBtn,
      setExprBtn,
      bpLocBtn,
      modulesBtn,
      hotBtn,
      varHistBtn,
      matrixBtn,
      tunnelBtn,
      compoundGraphBtn,
      otlpBtn,
      recBtn,
      recStopBtn,
      replayBtn,
      instrBtn,
      hwWatchBtn,
      dwarfInjBtn,
      nbBtn,
      stepTargetBtn,
      fnBpBtn,
      pinBtn,
      shareBtn,
      platformBtn,
      extBtn,
      triageBtn,
      vaultBtn,
      catchBtn,
      replayDiffBtn,
      sbomBtn,
      budgetBtn,
      traceQBtn,
      mergeBpBtn,
      sabBtn
    );
    sessRow.append(sessSelect, startBtn, stopBtn, stopAllBtn);
    row.append(contBtn, nextBtn, inBtn, outBtn, backBtn, revContBtn, bpBtn, condBtn, hitBtn, logBtn);
    const eventsWrap = makeDebugSection("Session events", "showConsole", eventsSec);
    panelBody.append(
      tip,
      launchRow,
      launchEditorEl,
      sessRow,
      toolsRow,
      attachRow,
      pathMapEl,
      skipRow,
      excRow,
      roLab,
      row,
      stateEl,
      timelineRow,
      eventsWrap,
      modulesEl,
      varHistEl,
      matrixEl,
      compoundGraphEl,
      groupsEl,
      bpIoRow,
      threadsSec,
      stackSec,
      sourcesSec,
      varsSec,
      diffRow,
      diffSec,
      watchRow,
      watchSec,
      dataBpRow,
      dataBpSec,
      flameSec,
      covTools,
      covSec,
      memSec,
      evalRow,
      completeBox,
      consoleSec
    );
    paintGroups(breakpointGroups);
    api("GET", "/api/debug/launch")
      .then((doc) => fillLaunchSelect(doc.configurations || [], undefined, doc.compounds || []))
      .catch(() => fillLaunchSelect([]));
    refresh();
    debugPoll = setInterval(() => {
      if (panelMode !== "debug") return;
      refresh();
    }, 900);
  }

  function colorDiff(text) {
    return (text || "")
      .split("\n")
      .map((line) => {
        const esc = window.ZintriqSyntax ? window.ZintriqSyntax.escape(line) : line;
        if (line.startsWith("+") && !line.startsWith("+++")) return `<span class="diff-add">${esc}</span>`;
        if (line.startsWith("-") && !line.startsWith("---")) return `<span class="diff-del">${esc}</span>`;
        return esc;
      })
      .join("\n");
  }

  async function renderChangesPanel() {
    panelBody.innerHTML = "<p>Loading…</p>";
    try {
      const data = await api("GET", "/api/changes");
      const list = data.changes || [];
      if (!list.length) {
        panelBody.innerHTML = "<p class='meta'>No change sets. AI/tools propose here before writing disk.</p>";
        return;
      }
      panelBody.innerHTML = "";
      for (const ch of list.slice(0, 30)) {
        const box = document.createElement("div");
        box.className = "change-item";
        box.innerHTML = `<div class="meta">${ch.id} · ${ch.source} · ${ch.status}</div>
          <div>${(ch.note || "").slice(0, 120)}</div>
          <div class="row" style="margin-top:8px"></div>`;
        const row = box.querySelector(".row");
        const view = document.createElement("button");
        view.textContent = "Diff";
        view.onclick = () => showChangeDiff(ch.id);
        row.appendChild(view);
        if (ch.status === "pending") {
          const acc = document.createElement("button");
          acc.textContent = "Accept";
          acc.onclick = async () => {
            await api("POST", `/api/changes/${ch.id}/accept`);
            await loadTree(cwd);
            if (activePath) await openFile(activePath);
            renderChangesPanel();
          };
          const rej = document.createElement("button");
          rej.textContent = "Reject";
          rej.onclick = async () => {
            await api("POST", `/api/changes/${ch.id}/reject`);
            renderChangesPanel();
          };
          row.append(acc, rej);
        }
        if (ch.status === "accepted") {
          const rb = document.createElement("button");
          rb.textContent = "Rollback";
          rb.onclick = async () => {
            await api("POST", `/api/changes/${ch.id}/rollback`);
            await loadTree(cwd);
            if (activePath) await openFile(activePath);
            renderChangesPanel();
          };
          row.appendChild(rb);
        }
        panelBody.appendChild(box);
      }
    } catch (err) {
      panelBody.innerHTML = `<p class="err">${err.message || err}</p>`;
    }
  }

  function closeDiffOverlay() {
    diffChangeId = "";
    diffSelectedPath = "";
    if (diffOverlay) diffOverlay.classList.add("hidden");
  }

  async function showChangeDiff(id) {
    diffChangeId = id;
    const data = await api("GET", `/api/changes/${id}`);
    const change = data.change || {};
    const files = change.files || [];
    if (diffOverlay) diffOverlay.classList.remove("hidden");
    if (diffTitle) {
      diffTitle.textContent = `${change.id || id} · ${change.source || ""} · ${change.status || ""}`;
    }
    const selectPath =
      diffSelectedPath && files.some((f) => f.path === diffSelectedPath)
        ? diffSelectedPath
        : (files[0] && files[0].path) || "";
    diffSelectedPath = selectPath;
    renderDiffFiles(change);
    const file = files.find((f) => f.path === selectPath);
    if (diffBefore) diffBefore.textContent = file ? file.before : "";
    if (diffAfter) diffAfter.textContent = file ? file.after : "";

    // keep a compact list in the side panel too
    panelBody.innerHTML = "";
    const back = document.createElement("button");
    back.textContent = "← Back";
    back.onclick = () => {
      closeDiffOverlay();
      renderChangesPanel();
    };
    const tip = document.createElement("p");
    tip.className = "meta";
    tip.textContent = "Side-by-side in editor. Accept/Reject per file.";
    panelBody.append(back, tip);
  }

  function renderDiffFiles(change) {
    if (!diffFiles) return;
    diffFiles.innerHTML = "";
    for (const f of change.files || []) {
      const wrap = document.createElement("div");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "hit" +
        (f.path === diffSelectedPath ? " active" : "") +
        (f.status === "accepted" ? " accepted" : "") +
        (f.status === "rejected" ? " rejected" : "");
      btn.textContent = `${f.path}${f.status && f.status !== "pending" ? ` · ${f.status}` : ""}`;
      btn.onclick = () => {
        diffSelectedPath = f.path;
        showChangeDiff(diffChangeId);
      };
      wrap.appendChild(btn);
      if (f.status === "pending" && (change.status === "pending" || change.status === "mixed")) {
        const actions = document.createElement("div");
        actions.className = "file-actions";
        const acc = document.createElement("button");
        acc.textContent = "Accept";
        acc.onclick = async (e) => {
          e.stopPropagation();
          await api("POST", `/api/changes/${diffChangeId}/files/accept`, { path: f.path });
          if (activePath === f.path) await openFile(f.path);
          await loadTree(cwd);
          showChangeDiff(diffChangeId);
        };
        const rej = document.createElement("button");
        rej.textContent = "Reject";
        rej.onclick = async (e) => {
          e.stopPropagation();
          await api("POST", `/api/changes/${diffChangeId}/files/reject`, { path: f.path });
          showChangeDiff(diffChangeId);
        };
        actions.append(acc, rej);
        wrap.appendChild(actions);
      }
      diffFiles.appendChild(wrap);
    }
  }

  async function renderGitPanel() {
    panelBody.innerHTML = "<p>Loading…</p>";
    try {
      const st = await api("GET", "/api/git/status");
      const diff = await api("GET", "/api/git/diff");
      let log = { lines: [], repo: false };
      let br = { branches: [], current: null, repo: false };
      if (st.repo) {
        try {
          log = await api("GET", "/api/git/log?limit=60");
        } catch {
          log = { lines: [], repo: true };
        }
        try {
          br = await api("GET", "/api/git/branches");
        } catch {
          br = { branches: [], current: st.branch || null, repo: true };
        }
      }
      panelBody.innerHTML = "";
      const row = document.createElement("div");
      row.className = "row";
      const initBtn = document.createElement("button");
      initBtn.textContent = "git init";
      initBtn.onclick = async () => {
        try {
          await api("POST", "/api/git/init");
          renderGitPanel();
        } catch (e) {
          alert(e.message || e);
        }
      };
      const commitBtn = document.createElement("button");
      commitBtn.textContent = "Commit all";
      commitBtn.onclick = async () => {
        const message = prompt("Commit message");
        if (!message) return;
        try {
          await api("POST", "/api/git/commit", { message });
          renderGitPanel();
        } catch (e) {
          alert(e.message || e);
        }
      };
      const newBr = document.createElement("button");
      newBr.textContent = "New branch";
      newBr.onclick = async () => {
        const name = prompt("Branch name");
        if (!name) return;
        try {
          await api("POST", "/api/git/checkout", { name, create: true });
          renderGitPanel();
        } catch (e) {
          alert(e.message || e);
        }
      };
      row.append(initBtn, commitBtn, newBr);

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = st.repo
        ? `on ${br.current || st.branch || "?"} · ${(st.entries || []).length} dirty`
        : "Not a git repo (enable git.write to init)";

      const branchBox = document.createElement("div");
      branchBox.className = "git-branches";
      if (st.repo) {
        const label = document.createElement("div");
        label.className = "meta";
        label.textContent = "Branches";
        branchBox.appendChild(label);
        for (const b of br.branches || []) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "hit" + (b.current ? " active" : "");
          btn.textContent = `${b.current ? "● " : ""}${b.name}${b.sha ? `  ${b.sha}` : ""}`;
          btn.disabled = Boolean(b.current);
          btn.onclick = async () => {
            try {
              await api("POST", "/api/git/checkout", { name: b.name });
              renderGitPanel();
            } catch (e) {
              alert(e.message || e);
            }
          };
          branchBox.appendChild(btn);
        }
      }

      const graphBox = document.createElement("div");
      graphBox.className = "git-graph";
      if (st.repo) {
        const gLabel = document.createElement("div");
        gLabel.className = "meta";
        gLabel.textContent = "Graph";
        graphBox.appendChild(gLabel);
        const gPre = document.createElement("div");
        gPre.className = "git-graph-lines";
        for (const line of log.lines || []) {
          const rowEl = document.createElement("div");
          rowEl.className = "git-graph-row";
          const g = document.createElement("span");
          g.className = "git-g";
          g.textContent = line.graph || "";
          rowEl.appendChild(g);
          if (line.commit) {
            const c = line.commit;
            const body = document.createElement("span");
            body.className = "git-c";
            const deco = c.decorations ? ` ${c.decorations}` : "";
            body.innerHTML = `<span class="git-sha">${escapeHtml(c.sha)}</span>${escapeHtml(deco)} <span class="git-sub">${escapeHtml(c.subject)}</span> <span class="meta">${escapeHtml(c.author)} · ${escapeHtml(c.date)}</span>`;
            rowEl.appendChild(body);
          }
          gPre.appendChild(rowEl);
        }
        if (!(log.lines || []).length) {
          gPre.textContent = "(no commits yet)";
        }
        graphBox.appendChild(gPre);
      }

      const pre = document.createElement("pre");
      pre.textContent = diff.diff || st.raw || (st.repo ? "(working tree clean)" : "");
      panelBody.append(row, meta, branchBox, graphBox, pre);
    } catch (err) {
      panelBody.innerHTML = `<p>${err.message || err}</p>`;
    }
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderAiPanel() {
    panelBody.innerHTML = "";
    const tip = document.createElement("p");
    tip.className = "meta";
    tip.textContent =
      "Enable ai.run (+ network for remote). Set ZINTRIQ_AI_API_KEY / BASE_URL / MODEL. Output is a pending change only.";
    const ta = document.createElement("textarea");
    ta.rows = 4;
    ta.placeholder = "Prompt for current file…";
    const pathHint = document.createElement("div");
    pathHint.className = "meta";
    pathHint.textContent = activePath ? `Target: ${activePath}` : "Open a file first";
    const run = document.createElement("button");
    run.textContent = "Run AI (explicit)";
    run.onclick = async () => {
      if (!activePath) return alert("Open a file first");
      try {
        await saveActive();
        const res = await api("POST", "/api/ai/run", { prompt: ta.value, path: activePath });
        openPanel("changes");
        if (res.change) await showChangeDiff(res.change.id);
      } catch (e) {
        alert(e.message || e);
      }
    };
    panelBody.append(tip, pathHint, ta, run);
  }

  function renderSearchPanel() {
    panelBody.innerHTML = "";
    const tip = document.createElement("p");
    tip.className = "meta";
    tip.textContent = "Workspace search (rg if installed, else walk). Ctrl/Cmd+Shift+F";
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Query…";
    const go = document.createElement("button");
    go.textContent = "Search";
    const results = document.createElement("div");
    const run = async () => {
      results.innerHTML = "Searching…";
      try {
        const data = await api("POST", "/api/search", { query: input.value });
        results.innerHTML = "";
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${(data.hits || []).length} hits · ${data.engine}`;
        results.appendChild(meta);
        for (const hit of data.hits || []) {
          const btn = document.createElement("button");
          btn.className = "hit";
          btn.textContent = `${hit.path}:${hit.line}  ${hit.text}`;
          btn.onclick = async () => {
            await openFile(hit.path);
            const lines = editor.value.split("\n");
            let off = 0;
            for (let i = 0; i < hit.line - 1 && i < lines.length; i++) off += lines[i].length + 1;
            editor.focus();
            editor.setSelectionRange(off, off + (lines[hit.line - 1] || "").length);
          };
          results.appendChild(btn);
        }
      } catch (e) {
        results.textContent = e.message || String(e);
      }
    };
    go.onclick = run;
    input.onkeydown = (e) => {
      if (e.key === "Enter") run();
    };
    panelBody.append(tip, input, go, results);
    input.focus();
  }

  function stopPtyPoll() {
    if (ptyPoll) {
      clearInterval(ptyPoll);
      ptyPoll = 0;
    }
  }

  function disposeXterm() {
    stopPtyPoll();
    if (ptyUnsubData) {
      ptyUnsubData();
      ptyUnsubData = null;
    }
    if (ptyUnsubExit) {
      ptyUnsubExit();
      ptyUnsubExit = null;
    }
    if (xtermRo) {
      try {
        xtermRo.disconnect();
      } catch {
        /* ignore */
      }
      xtermRo = null;
    }
    if (xtermInst) {
      try {
        xtermInst.dispose();
      } catch {
        /* ignore */
      }
      xtermInst = null;
      xtermFit = null;
    }
  }

  function desktopPty() {
    const d = window.zintriqDesktop;
    return d && d.pty && typeof d.pty.available === "function" ? d.pty : null;
  }

  async function ptyWrite(data) {
    const dp = desktopPty();
    if (dp && ptyBackend === "node-pty" && typeof dp.write === "function") {
      return dp.write(ptyId, data);
    }
    return api("POST", "/api/terminal/pty/write", { id: ptyId, data });
  }

  async function ptyResize(cols, rows) {
    const dp = desktopPty();
    if (dp && ptyBackend === "node-pty" && typeof dp.resize === "function") {
      return dp.resize(ptyId, cols, rows);
    }
    return api("POST", "/api/terminal/pty/resize", { id: ptyId, cols, rows });
  }

  async function ptyClose() {
    const dp = desktopPty();
    if (dp && ptyBackend === "node-pty" && typeof dp.kill === "function") {
      try {
        await dp.kill(ptyId);
      } catch {
        /* ignore */
      }
      return;
    }
    if (ptyId) {
      try {
        await api("POST", "/api/terminal/pty/close", { id: ptyId });
      } catch {
        /* ignore */
      }
    }
  }

  async function renderTermPanel() {
    disposeXterm();
    const hostEl = bottomBody || panelBody;
    hostEl.innerHTML = "";
    const tip = document.createElement("p");
    tip.className = "meta";
    tip.textContent =
      "Interactive PTY + xterm.js (Linux/macOS unix-pty, Windows ConPTY). Needs terminal permission.";
    const row = document.createElement("div");
    row.className = "row";
    const startBtn = document.createElement("button");
    startBtn.textContent = "Start PTY";
    const closeBtn = document.createElement("button");
    closeBtn.textContent = "Close PTY";
    const once = document.createElement("input");
    once.type = "text";
    once.placeholder = "one-shot command…";
    const onceBtn = document.createElement("button");
    onceBtn.textContent = "Run once";
    const host = document.createElement("div");
    host.className = "term-xterm-host";
    const fallback = document.createElement("div");
    fallback.className = "term-screen";
    fallback.style.display = "none";

    const Terminal = window.Terminal;
    const FitMod = window.FitAddon;
    const hasXterm = typeof Terminal === "function";

    const writeLocal = (s) => {
      if (xtermInst) xtermInst.write(s);
      else {
        fallback.style.display = "block";
        fallback.textContent += s;
        fallback.scrollTop = fallback.scrollHeight;
      }
    };

    if (hasXterm) {
      xtermInst = new Terminal({
        cursorBlink: true,
        fontFamily: '"IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace',
        fontSize: 12,
        theme: {
          background: "#0d0f14",
          foreground: "#d7dce8",
          cursor: "#6cb2ff",
          selectionBackground: "rgba(108,178,255,0.28)",
        },
        allowProposedApi: true,
        convertEol: false,
      });
      if (FitMod && FitMod.FitAddon) {
        xtermFit = new FitMod.FitAddon();
        xtermInst.loadAddon(xtermFit);
      }
      xtermInst.open(host);
      try {
        if (xtermFit) xtermFit.fit();
      } catch {
        /* ignore */
      }
      xtermInst.onData((data) => {
        if (!ptyId) return;
        ptyWrite(data).catch((err) => writeLocal(`\r\n[${err.message || err}]\r\n`));
      });
      xtermRo = new ResizeObserver(() => {
        if (!xtermInst || !xtermFit || !ptyId) return;
        try {
          xtermFit.fit();
          ptyResize(xtermInst.cols, xtermInst.rows).catch(() => {});
        } catch {
          /* ignore */
        }
      });
      xtermRo.observe(host);
    } else {
      host.style.display = "none";
      fallback.style.display = "block";
    }

    startBtn.onclick = async () => {
      try {
        if (ptyId) await ptyClose();
        ptyId = "";
        const cols = xtermInst ? xtermInst.cols : 80;
        const rows = xtermInst ? xtermInst.rows : 24;
        const dp = desktopPty();
        let data;
        if (dp && (await dp.available())) {
          if (ptyUnsubData) ptyUnsubData();
          if (ptyUnsubExit) ptyUnsubExit();
          data = await dp.start({ cols, rows });
          ptyBackend = "node-pty";
          ptyId = data.id;
          if (typeof dp.onData === "function") {
            ptyUnsubData = dp.onData((id, chunk) => {
              if (id === ptyId && chunk) writeLocal(chunk);
            });
          }
          if (typeof dp.onExit === "function") {
            ptyUnsubExit = dp.onExit((id) => {
              if (id === ptyId) {
                writeLocal("\r\n[pty exited]\r\n");
                ptyId = "";
              }
            });
          }
        } else {
          data = await api("POST", "/api/terminal/pty/start", { cols, rows });
          ptyBackend = data.backend || "flask-pty";
          ptyId = data.id;
          stopPtyPoll();
          ptyPoll = setInterval(async () => {
            if (!ptyId || !bottomOpen) return;
            try {
              const chunk = await api("GET", `/api/terminal/pty/read?id=${encodeURIComponent(ptyId)}`);
              if (chunk.data) writeLocal(chunk.data);
              if (chunk.alive === false) {
                writeLocal("\r\n[pty exited]\r\n");
                stopPtyPoll();
                ptyId = "";
              }
            } catch {
              /* ignore */
            }
          }, 80);
        }
        writeLocal(`\r\n[pty ${ptyId} · ${data.shell || ""} · ${ptyBackend}]\r\n`);
        if (xtermInst) xtermInst.focus();
      } catch (e) {
        writeLocal(`\r\n[${e.message || e}]\r\n`);
      }
    };
    closeBtn.onclick = async () => {
      stopPtyPoll();
      await ptyClose();
      ptyId = "";
      writeLocal("\r\n[closed]\r\n");
    };
    onceBtn.onclick = async () => {
      try {
        const data = await api("POST", "/api/terminal/run", { command: once.value });
        writeLocal(
          `\r\n$ ${once.value}\r\n${data.stdout || ""}${data.stderr || ""}\r\n[exit ${data.exitCode}]\r\n`
        );
      } catch (e) {
        writeLocal(`\r\n[${e.message || e}]\r\n`);
      }
    };

    try {
      const info = await api("GET", "/api/terminal/pty/supported");
      tip.textContent += ` Backend: ${info.backend || "?"} (${info.supported ? "ok" : "unavailable"}).`;
    } catch {
      /* ignore */
    }

    row.append(startBtn, closeBtn);
    hostEl.append(tip, row, once, onceBtn, host, fallback);
  }

  async function renderPermsPanel() {
    panelBody.innerHTML = "<p>Loading…</p>";
    try {
      const data = await api("GET", "/api/permissions");
      const perms = data.permissions || {};
      panelBody.innerHTML = "<p class='meta'>Deny by default for AI / network / terminal.</p>";
      for (const key of Object.keys(perms)) {
        const label = document.createElement("label");
        label.className = "perm";
        const span = document.createElement("span");
        span.textContent = key;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = Boolean(perms[key]);
        input.onchange = async () => {
          perms[key] = input.checked;
          await api("PUT", "/api/permissions", { permissions: perms });
        };
        label.append(span, input);
        panelBody.appendChild(label);
      }
    } catch (err) {
      panelBody.innerHTML = `<p>${err.message || err}</p>`;
    }
  }

  editor.addEventListener("input", () => {
    if (!activePath) return;
    const buf = buffers.get(activePath);
    if (!buf) return;
    ensureUnfoldedForEdit();
    buf.text = editor.value;
    paint(editor, hlA, buf.language);
    renderFoldGutter(buf);
    paintMinimap(buf);
    renderTabs();
    scheduleDiagnose();
    scheduleComplete();
    if (cursors.length <= 1) cursors = [editor.selectionStart || 0];
    syncCursorStatus();
  });
  editor.addEventListener("keydown", (e) => {
    if (
      activePath &&
      buffers.has(activePath) &&
      bufFolds(buffers.get(activePath)).size &&
      (e.key.length === 1 || e.key === "Backspace" || e.key === "Enter" || e.key === "Delete")
    ) {
      ensureUnfoldedForEdit();
    }
    if (completionItems.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        completionIndex = (completionIndex + 1) % completionItems.length;
        renderCompletion();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        completionIndex = (completionIndex - 1 + completionItems.length) % completionItems.length;
        renderCompletion();
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyCompletion(completionItems[completionIndex]);
        return;
      }
      if (e.key === "Escape") {
        hideCompletion();
        return;
      }
    }
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey && cursors.length > 1) {
      e.preventDefault();
      applyTypedToCursors(e.key);
      scheduleComplete();
      scheduleDiagnose();
    }
  });
  editor.addEventListener("scroll", () => {
    hlA.scrollTop = editor.scrollTop;
    hlA.scrollLeft = editor.scrollLeft;
    hideCompletion();
    hideHover();
    paintCursorLayer();
  });
  editor.addEventListener("click", (e) => {
    hideHover();
    if (e.altKey) {
      const off = editor.selectionStart || 0;
      if (!cursors.includes(off)) cursors.push(off);
      cursors.sort((a, b) => a - b);
      syncCursorStatus();
      e.preventDefault();
      return;
    }
    cursors = [editor.selectionStart || 0];
    syncCursorStatus();
  });
  editor.addEventListener("mousemove", () => {
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(showHoverAtCaret, 450);
  });
  editor.addEventListener("mouseleave", () => {
    clearTimeout(hoverTimer);
    hideHover();
  });
  editorB.addEventListener("input", () => {
    if (!secondaryPath || !buffers.has(secondaryPath)) return;
    const buf = buffers.get(secondaryPath);
    buf.text = editorB.value;
    paint(editorB, hlB, buf.language);
    renderTabs();
  });
  editorB.addEventListener("scroll", () => {
    hlB.scrollTop = editorB.scrollTop;
    hlB.scrollLeft = editorB.scrollLeft;
  });

  let dragging = false;
  let dragKind = "";
  splitHandle.addEventListener("mousedown", (e) => {
    dragging = true;
    dragKind = "split";
    e.preventDefault();
  });
  if (sidebarHandle) {
    sidebarHandle.addEventListener("mousedown", (e) => {
      dragging = true;
      dragKind = "sidebar";
      e.preventDefault();
    });
  }
  if (panelHandle) {
    panelHandle.addEventListener("mousedown", (e) => {
      dragging = true;
      dragKind = "panel";
      e.preventDefault();
    });
  }
  if (bottomHandle) {
    bottomHandle.addEventListener("mousedown", (e) => {
      dragging = true;
      dragKind = "bottom";
      e.preventDefault();
    });
  }
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    if (dragKind === "split" && splitEnabled) {
      const rect = editorsEl.getBoundingClientRect();
      splitRatio = Math.max(0.2, Math.min(0.8, (e.clientX - rect.left) / rect.width));
      applySplit();
      return;
    }
    if (dragKind === "sidebar" && !sidebarHidden) {
      sidebarW = Math.max(140, Math.min(480, e.clientX));
      applyShellLayout();
      return;
    }
    if (dragKind === "panel" && !panel.classList.contains("hidden")) {
      panelW = Math.max(240, Math.min(640, window.innerWidth - e.clientX));
      applyShellLayout();
      return;
    }
    if (dragKind === "bottom" && bottomOpen) {
      const rect = workArea.getBoundingClientRect();
      bottomH = Math.max(120, Math.min(rect.height - 80, rect.bottom - e.clientY));
      applyShellLayout();
    }
  });
  window.addEventListener("mouseup", () => {
    if (dragging) persistLayout();
    dragging = false;
    dragKind = "";
  });

  if (minimap) {
    minimap.addEventListener("click", (e) => {
      if (!activePath || !buffers.has(activePath)) return;
      const rect = minimap.getBoundingClientRect();
      const y = (e.clientY - rect.top) / Math.max(1, rect.height);
      const maxScroll = Math.max(0, editor.scrollHeight - editor.clientHeight);
      editor.scrollTop = y * maxScroll;
      hlA.scrollTop = editor.scrollTop;
      paintCursorLayer();
    });
  }

  document.getElementById("btn-refresh").addEventListener("click", () => loadTree(cwd));
  const btnNewFile = document.getElementById("btn-new-file");
  if (btnNewFile) btnNewFile.addEventListener("click", () => createNewFile());
  const btnNewFolder = document.getElementById("btn-new-folder");
  if (btnNewFolder) btnNewFolder.addEventListener("click", () => createNewFolder());
  const btnOnboarding = document.getElementById("btn-onboarding");
  if (btnOnboarding) btnOnboarding.addEventListener("click", () => showOnboarding(true));
  const btnEmptyNew = document.getElementById("btn-empty-new-file");
  if (btnEmptyNew) btnEmptyNew.addEventListener("click", () => createNewFile());
  const btnEmptyWelcome = document.getElementById("btn-empty-open-welcome");
  if (btnEmptyWelcome) {
    btnEmptyWelcome.addEventListener("click", () => {
      openFile("WELCOME.md").catch(() => createNewFile("WELCOME.md"));
    });
  }
  const btnEmptyGuide = document.getElementById("btn-empty-guide");
  if (btnEmptyGuide) btnEmptyGuide.addEventListener("click", () => showOnboarding(true));
  const onboardDismiss = document.getElementById("onboard-dismiss");
  if (onboardDismiss) onboardDismiss.addEventListener("click", () => completeOnboarding(false));
  const onboardHello = document.getElementById("onboard-open-hello");
  if (onboardHello) onboardHello.addEventListener("click", () => completeOnboarding(true));
  document.getElementById("btn-panel-close").addEventListener("click", closePanel);
  document.getElementById("btn-panel-changes").addEventListener("click", () => openPanel("changes"));
  document.getElementById("btn-panel-git").addEventListener("click", () => openPanel("git"));
  document.getElementById("btn-panel-search").addEventListener("click", () => openPanel("search"));
  const btnDebug = document.getElementById("btn-panel-debug");
  if (btnDebug) btnDebug.addEventListener("click", () => openPanel("debug"));
  document.getElementById("btn-panel-ai").addEventListener("click", () => openPanel("ai"));
  document.getElementById("btn-panel-perms").addEventListener("click", () => openPanel("perms"));
  const btnToggleBottom = document.getElementById("btn-toggle-bottom");
  if (btnToggleBottom) {
    btnToggleBottom.addEventListener("click", () => {
      if (bottomOpen) closeBottom();
      else openBottom();
    });
  }
  const btnTogglePanel = document.getElementById("btn-toggle-panel");
  if (btnTogglePanel) {
    btnTogglePanel.addEventListener("click", () => {
      if (panel.classList.contains("hidden")) openPanel(panelMode || "changes");
      else closePanel();
    });
  }
  const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
  if (btnToggleSidebar) {
    btnToggleSidebar.addEventListener("click", () => {
      sidebarHidden = true;
      applyShellLayout();
      persistLayout();
    });
  }
  if (btnShowSidebar) {
    btnShowSidebar.addEventListener("click", () => {
      sidebarHidden = false;
      applyShellLayout();
      persistLayout();
    });
  }
  const btnBottomClose = document.getElementById("btn-bottom-close");
  if (btnBottomClose) btnBottomClose.addEventListener("click", closeBottom);
  const diffClose = document.getElementById("diff-close");
  if (diffClose) diffClose.addEventListener("click", closeDiffOverlay);
  document.getElementById("find-next").addEventListener("click", findNext);
  document.getElementById("find-close").addEventListener("click", () => toggleFind(false));
  findInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      findNext();
    }
    if (e.key === "Escape") toggleFind(false);
  });

  window.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "n" && !e.shiftKey) {
      e.preventDefault();
      createNewFile();
      return;
    }
    if (mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      saveActive().catch((err) => setStatus(activePath, String(err.message || err)));
    }
    if (mod && e.shiftKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      openPanel("search");
      return;
    }
    if (mod && e.key.toLowerCase() === "f") {
      e.preventDefault();
      toggleFind(true);
    }
    if (mod && e.key.toLowerCase() === "d") {
      e.preventDefault();
      addNextOccurrenceCursor();
    }
    if (mod && e.key.toLowerCase() === " ") {
      e.preventDefault();
      scheduleComplete();
    }
    if (e.key === "F12" && e.shiftKey) {
      e.preventDefault();
      findReferences();
      return;
    }
    if (e.key === "F12") {
      e.preventDefault();
      goToDefinition();
    }
    if (e.key === "F2") {
      e.preventDefault();
      renameSymbol();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === ".") {
      e.preventDefault();
      runCodeActions();
    }
    if (e.key === "F9") {
      e.preventDefault();
      const pos = offsetToPos(editor.value, editor.selectionStart || 0);
      toggleBreakpointAt(pos.line + 1);
    }
    if (e.key === "F5") {
      e.preventDefault();
      openPanel("debug");
      (async () => {
        if (!activePath) return;
        try {
          await saveActive();
          await api("POST", "/api/debug/start", { path: activePath });
        } catch (err) {
          alert(err.message || err);
        }
      })();
    }
    if (e.key === "F10") {
      e.preventDefault();
      api("POST", "/api/debug/stepOver").catch((err) => alert(err.message || err));
    }
    if (e.key === "F11") {
      e.preventDefault();
      api("POST", "/api/debug/stepIn").catch((err) => alert(err.message || err));
    }
    if (mod && e.key === "k" && !e.shiftKey) {
      // reserved
    }
    if (mod && e.key.toLowerCase() === "\\") {
      e.preventDefault();
      splitEnabled = !splitEnabled;
      if (splitEnabled && !secondaryPath && activePath) secondaryPath = activePath;
      syncSecondary();
      applySplit();
    }
  });

  if (window.zintriqDesktop && typeof window.zintriqDesktop.onMenu === "function") {
    window.zintriqDesktop.onMenu((action) => {
      if (action === "save") saveActive();
      if (action === "find") toggleFind(true);
      if (action === "refresh") loadTree(cwd);
      if (action === "changes") openPanel("changes");
      if (action === "ai") openPanel("ai");
      if (action === "split") {
        splitEnabled = !splitEnabled;
        if (splitEnabled && !secondaryPath && activePath) secondaryPath = activePath;
        syncSecondary();
        applySplit();
      }
      if (action === "goDef") goToDefinition();
      if (action === "rename") renameSymbol();
      if (action === "findRefs") findReferences();
      if (action === "codeAction") runCodeActions();
    });
  }

  appEl.classList.add("no-panel");
  bottomHandle.style.display = "none";
  applyShellLayout();
  applySplit();
  showEditor(false);
  window.addEventListener("resize", () => {
    if (activePath && buffers.has(activePath)) paintMinimap(buffers.get(activePath));
  });

  (async () => {
    let showGuide = false;
    try {
      const bootInfo = await api("GET", "/api/onboarding");
      showGuide = Boolean(bootInfo.show_onboarding);
    } catch {
      showGuide = false;
    }
    restoreLayout({ freshStart: showGuide });
    try {
      await loadTree("");
      setStatus("Ready", `ui ${Math.round(performance.now() - boot)}ms`);
      if (showGuide) showOnboarding(true);
    } catch (err) {
      setStatus("Error", String(err.message || err));
      showOnboarding(true);
    }
  })();
})();
