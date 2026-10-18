(function () {
  const layoutEl = document.getElementById("da-settings-layout");
  const saveEl = document.getElementById("da-settings-save-layout");
  const conflictsEl = document.getElementById("da-keymap-conflicts");
  const desktop = window.zintriqDesktop;

  async function loadLayout() {
    if (!layoutEl) return;
    let layout = null;
    if (desktop && desktop.loadLayout) {
      layout = await desktop.loadLayout();
    } else if (window.zintriq && window.zintriq.http && window.zintriq.http.get) {
      const res = await window.zintriq.http.get("/api/builder-core/meta/layout");
      layout = await res.json();
    }
    layoutEl.textContent = JSON.stringify(layout || {}, null, 2);
  }

  if (saveEl) {
    saveEl.addEventListener("click", async function () {
      let layout = {};
      try {
        layout = JSON.parse(layoutEl.textContent || "{}");
      } catch {
        return;
      }
      if (desktop && desktop.saveLayout) await desktop.saveLayout(layout);
      else if (window.zintriq && window.zintriq.http && window.zintriq.http.post) {
        await window.zintriq.http.post("/api/builder-core/meta/layout", layout);
      }
      await loadLayout();
    });
  }

  loadLayout().catch(function () {});

  if (desktop && desktop.exportKeymap) {
    const exportEl = document.getElementById("da-keymap-export");
    if (exportEl) exportEl.addEventListener("click", function () {
      desktop.exportKeymap();
    });
  }
  const importEl = document.getElementById("da-keymap-import");
  const fileEl = document.getElementById("da-keymap-file");
  if (importEl && fileEl) {
    importEl.addEventListener("click", function () {
      fileEl.click();
    });
    fileEl.addEventListener("change", async function () {
      const file = fileEl.files && fileEl.files[0];
      fileEl.value = "";
      if (!file || !desktop || !desktop.importKeymap) return;
      const text = await file.text();
      const result = await desktop.importKeymap(text);
      if (conflictsEl) {
        if (result && result.conflicts && result.conflicts.length) {
          conflictsEl.textContent = "Conflict: " + result.conflicts.map(function (row) {
            return row.keys + " " + row.a + " / " + row.b;
          }).join("; ");
        } else {
          conflictsEl.textContent = result && result.ok ? "Keymap saved on this machine." : (result && result.error) || "";
        }
      }
    });
  }

  const ignoreEl = document.getElementById("da-git-ignore");
  const ignoreStatus = document.getElementById("da-git-ignore-status");
  if (ignoreEl && desktop && desktop.gitIgnore) {
    ignoreEl.addEventListener("click", async function () {
      const result = await desktop.gitIgnore();
      if (ignoreStatus) ignoreStatus.textContent = result && result.ok ? (result.path || "Wrote .gitignore") : (result && result.error) || "";
    });
  }

  const pushEl = document.getElementById("da-settings-push-max");
  const pushStatus = document.getElementById("da-settings-push-status");
  if (pushEl) {
    try {
      const saved = localStorage.getItem("zintriq-community-push-max");
      if (saved === "4" || saved === "8" || saved === "0") pushEl.value = saved;
      else pushEl.value = "8";
    } catch (_err) {
      pushEl.value = "8";
    }
    pushEl.addEventListener("change", function () {
      const value = pushEl.value === "4" || pushEl.value === "0" ? pushEl.value : "8";
      try {
        localStorage.setItem("zintriq-community-push-max", value);
      } catch (_err2) {
        /* ignore */
      }
      if (pushStatus) {
        pushStatus.textContent =
          value === "0" ? "Community push depth: unlimited (∞)." : "Community push depth: " + value + ".";
      }
    });
  }

  const debounceEl = document.getElementById("da-settings-layout-debounce");
  const debounceStatus = document.getElementById("da-settings-layout-debounce-status");
  if (debounceEl) {
    try {
      const saved = localStorage.getItem("zintriq-layout-debounce");
      debounceEl.value = saved === "low" ? "low" : "stable";
    } catch (_err) {
      debounceEl.value = "stable";
    }
    debounceEl.addEventListener("change", function () {
      const value = debounceEl.value === "low" ? "low" : "stable";
      try {
        localStorage.setItem("zintriq-layout-debounce", value);
      } catch (_err2) {
        /* ignore */
      }
      if (debounceStatus) {
        debounceStatus.textContent =
          value === "low" ? "Layout sync debounce: low latency (40ms)." : "Layout sync debounce: stable (120ms).";
      }
    });
  }

  const holdTouchEl = document.getElementById("da-settings-hold-touch");
  const holdMouseEl = document.getElementById("da-settings-hold-mouse");
  const holdStatus = document.getElementById("da-settings-hold-status");
  function clampHold(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.min(max, Math.max(min, Math.round(n)));
  }
  function readHoldPrefs() {
    let touch = 400;
    let mouse = 650;
    try {
      touch = clampHold(localStorage.getItem("zintriq-hold-touch-ms"), 200, 1200, 400);
      mouse = clampHold(localStorage.getItem("zintriq-hold-mouse-ms"), 300, 1500, 650);
    } catch (_err) {
      /* ignore */
    }
    if (holdTouchEl) holdTouchEl.value = String(touch);
    if (holdMouseEl) holdMouseEl.value = String(mouse);
  }
  function saveHoldPrefs() {
    const touch = clampHold(holdTouchEl && holdTouchEl.value, 200, 1200, 400);
    const mouse = clampHold(holdMouseEl && holdMouseEl.value, 300, 1500, 650);
    try {
      localStorage.setItem("zintriq-hold-touch-ms", String(touch));
      localStorage.setItem("zintriq-hold-mouse-ms", String(mouse));
    } catch (_err) {
      /* ignore */
    }
    if (holdTouchEl) holdTouchEl.value = String(touch);
    if (holdMouseEl) holdMouseEl.value = String(mouse);
    if (holdStatus) holdStatus.textContent = "Long-press: touch " + touch + "ms · mouse " + mouse + "ms.";
  }
  readHoldPrefs();
  if (holdTouchEl) holdTouchEl.addEventListener("change", saveHoldPrefs);
  if (holdMouseEl) holdMouseEl.addEventListener("change", saveHoldPrefs);

  function collectLocalPrefs() {
    return {
      kind: "zintriq-local-prefs",
      version: 1,
      communityPushMax: (function () {
        try {
          return localStorage.getItem("zintriq-community-push-max") || "8";
        } catch (_e) {
          return "8";
        }
      })(),
      layoutDebounce: (function () {
        try {
          return localStorage.getItem("zintriq-layout-debounce") || "stable";
        } catch (_e) {
          return "stable";
        }
      })(),
      holdTouchMs: clampHold(holdTouchEl && holdTouchEl.value, 200, 1200, 400),
      holdMouseMs: clampHold(holdMouseEl && holdMouseEl.value, 300, 1500, 650),
    };
  }

  function applyLocalPrefs(data) {
    if (!data || typeof data !== "object") return false;
    const push = String(data.communityPushMax == null ? data.pushMax : data.communityPushMax);
    const debounce = String(data.layoutDebounce || data.debounce || "stable");
    const touch = clampHold(data.holdTouchMs, 200, 1200, 400);
    const mouse = clampHold(data.holdMouseMs, 300, 1500, 650);
    try {
      if (push === "4" || push === "8" || push === "0") localStorage.setItem("zintriq-community-push-max", push);
      localStorage.setItem("zintriq-layout-debounce", debounce === "low" ? "low" : "stable");
      localStorage.setItem("zintriq-hold-touch-ms", String(touch));
      localStorage.setItem("zintriq-hold-mouse-ms", String(mouse));
    } catch (_err) {
      return false;
    }
    if (pushEl && (push === "4" || push === "8" || push === "0")) pushEl.value = push;
    if (debounceEl) debounceEl.value = debounce === "low" ? "low" : "stable";
    if (holdTouchEl) holdTouchEl.value = String(touch);
    if (holdMouseEl) holdMouseEl.value = String(mouse);
    return true;
  }

  const prefsExport = document.getElementById("da-settings-prefs-export");
  const prefsImport = document.getElementById("da-settings-prefs-import");
  const prefsFile = document.getElementById("da-settings-prefs-file");
  const prefsStatus = document.getElementById("da-settings-prefs-status");
  if (prefsExport) {
    prefsExport.addEventListener("click", function () {
      const blob = new Blob([JSON.stringify(collectLocalPrefs(), null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "zintriq-local-prefs.json";
      a.click();
      URL.revokeObjectURL(a.href);
      if (prefsStatus) prefsStatus.textContent = "Exported local prefs.";
    });
  }
  if (prefsImport && prefsFile) {
    prefsImport.addEventListener("click", function () {
      prefsFile.click();
    });
    prefsFile.addEventListener("change", async function () {
      const file = prefsFile.files && prefsFile.files[0];
      prefsFile.value = "";
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        if (applyLocalPrefs(data)) {
          if (prefsStatus) prefsStatus.textContent = "Imported local prefs.";
        } else if (prefsStatus) {
          prefsStatus.textContent = "Import failed.";
        }
      } catch (_err) {
        if (prefsStatus) prefsStatus.textContent = "Invalid prefs JSON.";
      }
    });
  }
})();