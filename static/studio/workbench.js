(function (root) {
  const views = {
    meta: { href: "/studio", id: "meta", name: "Meta" },
    code: { href: "/studio/meta", id: "code", name: "Code" },
    visual: { href: "/studio/meta", id: "visual", name: "Visual" },
    graph: { href: "/studio/meta", id: "graph", name: "Graph" },
    diagram: { href: "/studio/meta", id: "diagram", name: "Diagram" },
    uir: { href: "/studio/meta", id: "uir", name: "UIR" },
    simulation: { href: "/studio/simulate", id: "simulation", name: "Simulation" },
    page: { href: "/studio/meta", id: "page", name: "Page" },
    artifact: { href: "/studio/instantiate", id: "artifact", name: "Artifact" },
  };
  const surfaces = {
    library: { href: "/studio", id: "library", name: "Library" },
    describe: { href: "/studio/meta", id: "describe", name: "Describe" },
    simulate: { href: "/studio/simulate", id: "simulate", name: "Simulate" },
    instantiate: { href: "/studio/instantiate", id: "instantiate", name: "Instantiate" },
    space: { href: "/studio/space", id: "space", name: "Space" },
    community: { href: "/app/community", id: "community", name: "Community" },
  };
  root.ZintriqWorkbench = {
    activeView: "meta",
    documentKind: "description",
    views: views,
    surfaces: surfaces,
    switchView: function (id) {
      const view = views[id];
      if (root.ZintriqEditorViews) {
        root.ZintriqEditorViews.activate(id);
        this.activeView = id;
        return;
      }
      let slug = (document.body && document.body.getAttribute("data-draft-slug")) || "";
      if (!slug) {
        try {
          slug = sessionStorage.getItem("zintriq-draft-slug") || "";
        } catch (_err) {
          slug = "";
        }
      }
      if (!slug) {
        try {
          slug = new URLSearchParams(root.location.search).get("draft") || "";
        } catch (_err2) {
          slug = "";
        }
      }
      const href = (view && view.href) || "/studio/meta";
      const dest = slug ? "/studio/meta/" + encodeURIComponent(slug) : href;
      const join = dest.indexOf("?") >= 0 ? "&" : "?";
      root.location.assign(dest + join + "pane=" + encodeURIComponent(id));
    },
    switchSurface: function (id) {
      const surface = surfaces[id];
      if (!surface) return;
      let href = surface.href;
      if (id === "describe" || id === "simulate" || id === "instantiate") {
        const match = String(root.location.pathname || "").match(
          /\/studio\/(?:meta|simulate|instantiate|space)\/([^/]+)/
        );
        if (match) href += "/" + match[1];
      }
      if (id === "instantiate") {
        try {
          sessionStorage.setItem("zintriq-focus-hw", "1");
        } catch (_err) {
          /* ignore */
        }
      }
      if (href) root.location.assign(href);
    },
    layoutDebounceMs: function () {
      try {
        const mode = localStorage.getItem("zintriq-layout-debounce") || "stable";
        if (mode === "low") return 40;
      } catch (_err) {
        /* ignore */
      }
      return 120;
    },
    palette: {
      open: function () {
        const existing = document.getElementById("wb-palette");
        if (existing) {
          existing.remove();
          return;
        }
        const engine = root.ZintriqEngine;
        const wrap = document.createElement("div");
        wrap.id = "wb-palette";
        wrap.className = "wb-palette";
        wrap.innerHTML =
          '<label class="wb-palette__label">Command' +
          '<input id="wb-palette-q" type="search" autocomplete="off" spellcheck="false"></label>' +
          '<label class="wb-palette__label">workspace <input id="wb-palette-ws" type="search" autocomplete="off" spellcheck="false"></label>' +
          '<label class="wb-palette__label">form <input id="wb-q-form" type="search" placeholder="struct"></label>' +
          '<label class="wb-palette__label">kind <input id="wb-q-kind" type="search" placeholder="scene"></label>' +
          '<label class="wb-palette__label">fingerprint <input id="wb-q-fp" type="search"></label>' +
          '<label class="wb-palette__label">stamped <select id="wb-q-stamped"><option value="">any</option><option value="0">未盖章</option><option value="1">stamped</option></select></label>' +
          '<label class="wb-palette__label">meta_level <input id="wb-q-level" type="search" placeholder="exact"></label>' +
          '<label class="wb-palette__label">level min <input id="wb-q-level-min" type="search" placeholder="0"></label>' +
          '<label class="wb-palette__label">level max <input id="wb-q-level-max" type="search" placeholder="∞"></label>' +
          '<p class="wb-palette__fav" id="wb-q-fav"></p>' +
          '<p class="wb-palette__fav-io"><button type="button" id="wb-q-export">导出收藏</button> <button type="button" id="wb-q-import">导入收藏</button><input id="wb-q-import-file" type="file" accept="application/json,.json" hidden></p>' +
          '<button type="button" id="wb-q-save" class="wb-palette__save">存为收藏</button>' +
          '<p class="wb-palette__recent-label">最近</p>' +
          '<ul id="wb-palette-recent" class="wb-palette__list wb-palette__recent"></ul>' +
          '<ul id="wb-palette-list" class="wb-palette__list"></ul>';
        document.body.appendChild(wrap);
        const input = wrap.querySelector("#wb-palette-q");
        const list = wrap.querySelector("#wb-palette-list");
        const recentList = wrap.querySelector("#wb-palette-recent");
        function rows() {
          return engine && engine.command ? engine.command.list() : [];
        }
        function paintRecent() {
          if (!recentList) return;
          recentList.textContent = "";
          const available = {};
          rows().forEach(function (row) {
            available[row.id] = row;
          });
          const recents = root.ZintriqWorkbench.recentForWorkspace();
          recents.forEach(function (id) {
            const row = available[id];
            if (!row) return;
            const q = String(input.value || "").toLowerCase();
            if (q && String(row.id).toLowerCase().indexOf(q) < 0 && String(row.title || "").toLowerCase().indexOf(q) < 0) return;
            const li = document.createElement("li");
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = row.id + (row.keys ? "  " + row.keys : "");
            btn.addEventListener("click", function () {
              engine.command.run(row.id);
              wrap.remove();
            });
            li.appendChild(btn);
            recentList.appendChild(li);
          });
        }
        function paint() {
          const q = String(input.value || "").toLowerCase();
          list.textContent = "";
          paintRecent();
          rows()
            .filter(function (row) {
              return !q || String(row.id).toLowerCase().indexOf(q) >= 0 || String(row.title || "").toLowerCase().indexOf(q) >= 0;
            })
            .slice(0, 24)
            .forEach(function (row) {
              const li = document.createElement("li");
              const btn = document.createElement("button");
              btn.type = "button";
              btn.textContent = row.id + (row.keys ? "  " + row.keys : "");
              btn.addEventListener("click", function () {
                engine.command.run(row.id);
                wrap.remove();
              });
              li.appendChild(btn);
              list.appendChild(li);
            });
          if ((q || form || kind || fp || stamped) && root.zintriq && root.zintriq.http && root.zintriq.http.get) {
            const form = (document.getElementById("wb-q-form") || {}).value || "";
            const kind = (document.getElementById("wb-q-kind") || {}).value || "";
            const fp = (document.getElementById("wb-q-fp") || {}).value || "";
            const stamped = (document.getElementById("wb-q-stamped") || {}).value || "";
            const level = (document.getElementById("wb-q-level") || {}).value || "";
            const levelMin = (document.getElementById("wb-q-level-min") || {}).value || "";
            const levelMax = (document.getElementById("wb-q-level-max") || {}).value || "";
            const qs =
              "/api/builder-core/meta/search?q=" +
              encodeURIComponent(q) +
              "&form=" +
              encodeURIComponent(form) +
              "&kind=" +
              encodeURIComponent(kind) +
              "&fingerprint=" +
              encodeURIComponent(fp) +
              "&stamped=" +
              encodeURIComponent(stamped) +
              "&meta_level=" +
              encodeURIComponent(level) +
              "&meta_level_min=" +
              encodeURIComponent(levelMin) +
              "&meta_level_max=" +
              encodeURIComponent(levelMax);
            root.zintriq.http.get(qs).then(function (res) {
              return res.json();
            }).then(function (data) {
              ((data && data.hits) || []).slice(0, 16).forEach(function (hit) {
                if (hit.kind && hit.kind !== "draft") return;
                const li = document.createElement("li");
                const btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = "draft " + (hit.slug || "");
                btn.addEventListener("click", function () {
                  if (hit.slug) window.location.href = "/studio/meta/" + encodeURIComponent(hit.slug);
                  wrap.remove();
                });
                li.appendChild(btn);
                list.appendChild(li);
              });
            }).catch(function () {});
          }
        }
        function paintFav() {
          const fav = wrap.querySelector("#wb-q-fav");
          if (!fav) return;
          fav.textContent = "";
          (root.ZintriqWorkbench._queries || []).forEach(function (row, index) {
            const line = document.createElement("span");
            line.className = "wb-fav-row";
            const handle = document.createElement("span");
            handle.className = "wb-fav-drag";
            handle.textContent = "⋮⋮";
            handle.setAttribute("aria-hidden", "true");
            line.draggable = true;
            line.addEventListener("dragstart", function (ev) {
              ev.dataTransfer.setData("text/plain", String(index));
              ev.dataTransfer.effectAllowed = "move";
            });
            line.addEventListener("dragover", function (ev) {
              ev.preventDefault();
            });
            line.addEventListener("drop", function (ev) {
              ev.preventDefault();
              const from = Number(ev.dataTransfer.getData("text/plain"));
              if (!Number.isFinite(from) || from === index) return;
              const queries = (root.ZintriqWorkbench._queries || []).slice(0, 24);
              if (from < 0 || from >= queries.length) return;
              const moved = queries.splice(from, 1)[0];
              queries.splice(index, 0, moved);
              root.ZintriqWorkbench._queries = queries.slice(0, 24);
              root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
              paintFav();
            });
            const name = document.createElement("input");
            name.type = "text";
            name.value = row.id || "query";
            name.setAttribute("aria-label", "Rename favorite");
            name.draggable = false;
            name.addEventListener("change", function () {
              const queries = (root.ZintriqWorkbench._queries || []).slice();
              queries[index] = Object.assign({}, queries[index], { id: String(name.value || "query").slice(0, 64) });
              root.ZintriqWorkbench._queries = queries;
              root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
            });
            const open = document.createElement("button");
            open.type = "button";
            open.textContent = row.id || "query";
            open.addEventListener("click", function () {
              if (row.slug) {
                window.location.href = "/studio/meta/" + encodeURIComponent(row.slug);
                return;
              }
              const kindEl = document.getElementById("wb-q-kind");
              const stampedEl = document.getElementById("wb-q-stamped");
              const formEl = document.getElementById("wb-q-form");
              const levelEl = document.getElementById("wb-q-level");
              if (kindEl) kindEl.value = row.kind || "";
              if (stampedEl) stampedEl.value = row.stamped || "";
              if (formEl) formEl.value = row.form || "";
              if (levelEl) levelEl.value = row.meta_level || "";
              const minEl = document.getElementById("wb-q-level-min");
              const maxEl = document.getElementById("wb-q-level-max");
              if (minEl) minEl.value = row.meta_level_min || "";
              if (maxEl) maxEl.value = row.meta_level_max || "";
              paint();
            });
            const del = document.createElement("button");
            del.type = "button";
            del.textContent = "删除";
            del.addEventListener("click", function () {
              const queries = (root.ZintriqWorkbench._queries || []).slice();
              queries.splice(index, 1);
              root.ZintriqWorkbench._queries = queries;
              root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
              paintFav();
            });
            line.appendChild(handle);
            line.appendChild(name);
            line.appendChild(open);
            line.appendChild(del);
            fav.appendChild(line);
          });
        }
        wrap._paint = paint;
        wrap._paintFav = paintFav;
        wrap._paintRecent = paintRecent;
        input.value = root.ZintriqWorkbench._paletteQ || "";
        input.addEventListener("input", function () {
          root.ZintriqWorkbench._paletteQ = input.value;
          paint();
        });
        const wsEl = wrap.querySelector("#wb-palette-ws");
        if (wsEl) {
          wsEl.value = root.ZintriqWorkbench._workspace || "default";
          wsEl.addEventListener("change", function () {
            root.ZintriqWorkbench.renameWorkspace(wsEl.value);
          });
        }
        wrap.querySelectorAll("#wb-q-form, #wb-q-kind, #wb-q-fp, #wb-q-stamped, #wb-q-level, #wb-q-level-min, #wb-q-level-max").forEach(function (el) {
          el.addEventListener("input", paint);
          el.addEventListener("change", paint);
        });
        const saveFav = wrap.querySelector("#wb-q-save");
        if (saveFav) {
          saveFav.addEventListener("click", function () {
            const engine = root.ZintriqEngine;
            const slug =
              (engine && engine.store && engine.store.get && engine.store.get().slug) ||
              (document.getElementById("me-slug") || {}).value ||
              "";
            const row = {
              id: ((document.getElementById("wb-q-kind") || {}).value || "query") + (slug ? "-" + slug : ""),
              form: (document.getElementById("wb-q-form") || {}).value || "",
              kind: (document.getElementById("wb-q-kind") || {}).value || "",
              stamped: (document.getElementById("wb-q-stamped") || {}).value || "",
              meta_level: (document.getElementById("wb-q-level") || {}).value || "",
              meta_level_min: (document.getElementById("wb-q-level-min") || {}).value || "",
              meta_level_max: (document.getElementById("wb-q-level-max") || {}).value || "",
              slug: String(slug || "").trim(),
            };
            const queries = (root.ZintriqWorkbench._queries || []).slice();
            queries.unshift(row);
            root.ZintriqWorkbench._queries = queries.slice(0, 24);
            root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
            paintFav();
          });
        }
        const expFav = wrap.querySelector("#wb-q-export");
        const impFav = wrap.querySelector("#wb-q-import");
        const impFile = wrap.querySelector("#wb-q-import-file");
        if (expFav) {
          expFav.addEventListener("click", function () {
            const blob = new Blob(
              [JSON.stringify({ queries: root.ZintriqWorkbench.mergeQueries(root.ZintriqWorkbench._queries || [], []).filter(function (row) { return row && String(row.id || "").trim(); }).slice(0, 24) }, null, 2)],
              { type: "application/json" }
            );
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "zintriq-queries.json";
            a.click();
            URL.revokeObjectURL(a.href);
          });
        }
        if (impFav && impFile) {
          impFav.addEventListener("click", function () {
            impFile.click();
          });
          impFile.addEventListener("change", function () {
            const file = impFile.files && impFile.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function () {
              try {
                const data = JSON.parse(String(reader.result || "{}"));
                const raw = Array.isArray(data) ? data : data.queries;
                if (!Array.isArray(raw)) return;
                const incoming = raw.filter(function (item) {
                  return item && typeof item === "object" && String(item.id || "").trim();
                });
                root.ZintriqWorkbench._queries = root.ZintriqWorkbench.mergeQueries(root.ZintriqWorkbench._queries || [], incoming).slice(0, 24);
                root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
                paintFav();
              } catch (err) {
                /* keep current queries */
              }
              impFile.value = "";
            };
            reader.readAsText(file);
          });
        }
        wrap.addEventListener("keydown", function (ev) {
          if (ev.key === "Escape") wrap.remove();
        });
        paintFav();
        paint();
        input.focus();
      },
      repaint: function () {
        const wrap = document.getElementById("wb-palette");
        if (!wrap) return;
        const input = wrap.querySelector("#wb-palette-q");
        if (input && root.ZintriqWorkbench._paletteQ != null && input.value !== root.ZintriqWorkbench._paletteQ) {
          if (!String(input.value || "")) input.value = root.ZintriqWorkbench._paletteQ;
          else root.ZintriqWorkbench._paletteQ = input.value;
        }
        if (typeof wrap._paint === "function") wrap._paint();
        if (typeof wrap._paintRecent === "function") wrap._paintRecent();
        if (input && root.ZintriqWorkbench._paletteQ != null) input.value = root.ZintriqWorkbench._paletteQ;
        const wsEl = wrap.querySelector("#wb-palette-ws");
        if (wsEl && document.activeElement !== wsEl) {
          wsEl.value = root.ZintriqWorkbench._workspace || "default";
        }
      },
    },
    recentForWorkspace: function () {
      const ws = root.ZintriqWorkbench._workspace || "default";
      const by = root.ZintriqWorkbench._recentByWorkspace || {};
      if (by[ws] && by[ws].length) return by[ws];
      return (root.ZintriqEngine && root.ZintriqEngine.command && root.ZintriqEngine.command._recent) || root.ZintriqWorkbench._recentCommands || [];
    },
    renameWorkspace: function (name) {
      const next = String(name || "").trim() || "default";
      const prev = root.ZintriqWorkbench._workspace || "default";
      root.ZintriqWorkbench.setRecentForWorkspace(root.ZintriqWorkbench.recentForWorkspace());
      const by = root.ZintriqWorkbench._recentByWorkspace || {};
      if (prev !== next) {
        if (by[next] && by[next].length) {
          root.ZintriqWorkbench._workspace = next;
          root.ZintriqWorkbench.setRecentForWorkspace(by[next] || []);
        } else {
          by[next] = by[prev] || [];
          delete by[prev];
          root.ZintriqWorkbench._recentByWorkspace = by;
          root.ZintriqWorkbench._workspace = next;
          root.ZintriqWorkbench.setRecentForWorkspace(by[next] || []);
        }
        if (typeof root.ZintriqWorkbench.persistDock === "function" && typeof root.ZintriqWorkbench.snapshotLayout === "function") {
          root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
        }
      }
      if (root.ZintriqWorkbench.palette && typeof root.ZintriqWorkbench.palette.repaint === "function") {
        root.ZintriqWorkbench.palette.repaint();
      }
    },
    switchWorkspace: function (name) {
      const next = String(name || "").trim() || "default";
      const prev = root.ZintriqWorkbench._workspace || "default";
      if (prev !== next) {
        root.ZintriqWorkbench.setRecentForWorkspace(root.ZintriqWorkbench.recentForWorkspace());
        root.ZintriqWorkbench._workspace = next;
        const by = root.ZintriqWorkbench._recentByWorkspace || {};
        root.ZintriqWorkbench.setRecentForWorkspace(by[next] || []);
        if (typeof root.ZintriqWorkbench.persistDock === "function" && typeof root.ZintriqWorkbench.snapshotLayout === "function") {
          root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
        }
      }
      if (root.ZintriqWorkbench.palette && typeof root.ZintriqWorkbench.palette.repaint === "function") {
        root.ZintriqWorkbench.palette.repaint();
      }
    },
    setRecentForWorkspace: function (ids) {
      const ws = root.ZintriqWorkbench._workspace || "default";
      const recents = (ids || []).map(function (id) { return String(id || ""); }).filter(Boolean).slice(0, 8);
      root.ZintriqWorkbench._recentByWorkspace = root.ZintriqWorkbench._recentByWorkspace || {};
      root.ZintriqWorkbench._recentByWorkspace[ws] = recents;
      root.ZintriqWorkbench._recentCommands = recents;
      if (root.ZintriqEngine && root.ZintriqEngine.command) root.ZintriqEngine.command._recent = recents;
    },
    mergeQueries: function (current, incoming) {
      const have = {};
      (current || []).forEach(function (row) {
        if (row && row.id) have[String(row.id)] = true;
      });
      const fresh = [];
      const over = {};
      (incoming || []).forEach(function (item) {
        if (!item || typeof item !== "object") return;
        const ident = item.id != null ? String(item.id) : "";
        if (ident && have[ident]) over[ident] = item;
        else fresh.push(item);
      });
      const kept = (current || []).map(function (row) {
        if (row && row.id && over[String(row.id)]) return Object.assign({}, row, over[String(row.id)]);
        return row;
      });
      return fresh.concat(kept).filter(function (item) { return item && typeof item === "object"; }).slice(0, 24);
    },
    restoreStamp: function (row) {
      const engine = root.ZintriqEngine;
      const state = engine ? engine.store.get() : {};
      const slug = (state && state.slug) || (document.getElementById("me-slug") || {}).value || "";
      const bar = document.getElementById("me-statusbar");
      if (!row || !slug || !row.fingerprint || !root.zintriq || !root.zintriq.http || !root.zintriq.http.post) return;
      root.zintriq.http
        .post("/api/builder-core/meta/plugins/timeline/restore", { slug: slug, fingerprint: row.fingerprint })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          const dest = (data && data.slug) || slug;
          if (data && data.restored && dest === slug) {
            window.location.href = "/studio/meta/" + encodeURIComponent(slug);
            return;
          }
          if (bar) bar.setAttribute("data-stamp", row.fingerprint || "");
          root.ZintriqWorkbench.paintStatus();
        })
        .catch(function () {
          if (bar) bar.setAttribute("data-stamp", row.fingerprint || "");
          root.ZintriqWorkbench.paintStatus();
        });
    },
    closeRebindDrawer: function () {
      const drawer = document.getElementById("wb-rebind-drawer");
      if (drawer) drawer.remove();
    },
    refreshRebinds: function (opts) {
      const options = opts || {};
      const applyLocal = function (rows) {
        let next = Array.isArray(rows) ? rows.slice() : [];
        if (options.clearedId || options.clearedSlug) {
          next = next.filter(function (row) {
            if (!row) return false;
            if (options.clearedId && row.id === options.clearedId) return false;
            if (options.clearedSlug && (row.to === options.clearedSlug || row.from === options.clearedSlug)) {
              return false;
            }
            return true;
          });
        }
        root.ZintriqWorkbench._rebinds = next;
        root.ZintriqWorkbench.paintStatus();
      };
      if (options.rows) {
        applyLocal(options.rows);
        return;
      }
      if (!(root.zintriq && root.zintriq.http && root.zintriq.http.get)) {
        applyLocal(root.ZintriqWorkbench._rebinds || []);
        return;
      }
      root.zintriq.http
        .get("/api/plugin/rebind-timeline")
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          applyLocal((data && data.rows) || []);
        })
        .catch(function () {
          applyLocal(root.ZintriqWorkbench._rebinds || []);
        });
    },
    openRebindDrawer: function () {
      root.ZintriqWorkbench.closeRebindDrawer();
      const rows = (root.ZintriqWorkbench._rebinds || []).slice().reverse();
      const drawer = document.createElement("div");
      drawer.id = "wb-rebind-drawer";
      drawer.className = "wb-rebind-drawer";
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-label", "Use rebind timeline");
      const head = document.createElement("div");
      head.className = "wb-rebind-drawer__head";
      const title = document.createElement("strong");
      title.textContent = "Rebind timeline";
      const close = document.createElement("button");
      close.type = "button";
      close.textContent = "Close";
      close.addEventListener("click", function () {
        root.ZintriqWorkbench.closeRebindDrawer();
      });
      head.appendChild(title);
      head.appendChild(close);
      drawer.appendChild(head);
      const list = document.createElement("div");
      list.className = "wb-rebind-drawer__list";
      if (!rows.length) {
        const empty = document.createElement("p");
        empty.textContent = "No Use rebinds yet.";
        list.appendChild(empty);
      } else {
        const groups = {};
        const order = [];
        rows.forEach(function (row) {
          const id = String((row && row.id) || "pack");
          if (!groups[id]) {
            groups[id] = [];
            order.push(id);
          }
          groups[id].push(row);
        });
        let remembered = "";
        try {
          remembered = localStorage.getItem("zintriq-rebind-open-pack") || "";
        } catch (_mem) {
          remembered = "";
        }
        const openId = remembered && groups[remembered] ? remembered : order[0];
        order.forEach(function (id) {
          const details = document.createElement("details");
          details.className = "wb-rebind-group";
          details.setAttribute("data-rebind-pack", id);
          details.open = id === openId;
          const summary = document.createElement("summary");
          summary.textContent = id + " · " + groups[id].length;
          details.appendChild(summary);
          details.addEventListener("toggle", function () {
            if (!details.open) return;
            try {
              localStorage.setItem("zintriq-rebind-open-pack", id);
            } catch (_save) {
              /* ignore */
            }
            list.querySelectorAll("details.wb-rebind-group").forEach(function (other) {
              if (other !== details) other.open = false;
            });
          });
          const ul = document.createElement("ul");
          groups[id].forEach(function (row) {
            const li = document.createElement("li");
            const btn = document.createElement("button");
            btn.type = "button";
            const fromSlug = row.from || "∅";
            const toSlug = row.to || "";
            const when = row.at ? new Date(Number(row.at) * 1000).toISOString() : "";
            btn.textContent = fromSlug + " → " + toSlug + (when ? " · " + when : "");
            btn.addEventListener("click", function () {
              if (toSlug) window.location.href = "/studio/meta/" + encodeURIComponent(toSlug);
            });
            li.appendChild(btn);
            ul.appendChild(li);
          });
          details.appendChild(ul);
          list.appendChild(details);
        });
      }
      drawer.appendChild(list);
      document.body.appendChild(drawer);
      close.focus();
    },
    paintStatus: function () {
      const bar = document.getElementById("me-statusbar");
      if (!bar) return;
      const engine = root.ZintriqEngine;
      const state = engine ? engine.store.get() : {};
      const sel = engine && engine.selection ? engine.selection.ids.length : 0;
      const view = (document.body && document.body.getAttribute("data-editor-view")) || "meta";
      const stamp = bar.getAttribute("data-stamp") || "";
      const dirty = root.ZintriqWorkbench._gitDirty || [];
      const stamps = root.ZintriqWorkbench._timeline || [];
      if (root.ZintriqWorkbench._stampIndex == null) root.ZintriqWorkbench._stampIndex = 0;
      if (stamps.length) {
        root.ZintriqWorkbench._stampIndex = ((root.ZintriqWorkbench._stampIndex % stamps.length) + stamps.length) % stamps.length;
      }
      bar.textContent = "";
      bar.tabIndex = 0;
      const selectedStamp = stamps[root.ZintriqWorkbench._stampIndex] || null;
      const when = selectedStamp && selectedStamp.at ? new Date(Number(selectedStamp.at) * 1000).toISOString() : "";
      const fp8 = selectedStamp && selectedStamp.fingerprint ? String(selectedStamp.fingerprint).slice(0, 8) : "";
      const packId = selectedStamp && selectedStamp.pack_id ? String(selectedStamp.pack_id) : "";
      const label = document.createElement("span");
      label.textContent =
        view +
        " · " +
        (state.slug || "untitled") +
        " · sel " +
        sel +
        " · " +
        (stamp || "local") +
        (when ? " · " + when : "") +
        (fp8 ? " · " + fp8 : "") +
        " · " +
        (document.documentElement.getAttribute("data-theme") || "theme");
      bar.appendChild(label);
      if (packId) {
        const packBtn = document.createElement("button");
        packBtn.type = "button";
        packBtn.className = "wb-stamp-pack";
        packBtn.textContent = packId;
        packBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          const el = document.getElementById("da-installed-packs");
          if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "nearest" });
          else window.location.href = "/app/community#da-installed-packs";
        });
        bar.appendChild(packBtn);
      }
      dirty.forEach(function (slug) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "wb-git-file";
        btn.textContent = slug;
        btn.addEventListener("click", function () {
          window.location.href = "/studio/meta/" + encodeURIComponent(slug);
        });
        bar.appendChild(btn);
      });
      const rebinds = root.ZintriqWorkbench._rebinds || [];
      if (rebinds.length) {
        const openBtn = document.createElement("button");
        openBtn.type = "button";
        openBtn.className = "wb-rebind";
        const last = rebinds[rebinds.length - 1] || {};
        openBtn.textContent = (last.from || "∅") + "→" + (last.to || "");
        openBtn.title = "Open rebind timeline (" + rebinds.length + ")";
        openBtn.setAttribute("aria-haspopup", "dialog");
        openBtn.addEventListener("click", function (ev) {
          ev.preventDefault();
          ev.stopPropagation();
          root.ZintriqWorkbench.openRebindDrawer();
        });
        bar.appendChild(openBtn);
        rebinds.slice(-3, -1).forEach(function (row) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "wb-rebind";
          const fromSlug = row.from || "∅";
          const toSlug = row.to || "";
          btn.textContent = fromSlug + "→" + toSlug;
          btn.title = (row.id || "pack") + " " + fromSlug + " → " + toSlug + " · open timeline";
          btn.addEventListener("click", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            root.ZintriqWorkbench.openRebindDrawer();
          });
          bar.appendChild(btn);
        });
      }
      stamps.forEach(function (row, index) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "wb-stamp-fp" + (index === root.ZintriqWorkbench._stampIndex ? " is-selected" : "");
        btn.textContent = String(row.fingerprint || "").slice(0, 8);
        btn.title = String(row.fingerprint || "");
        btn.setAttribute("aria-selected", index === root.ZintriqWorkbench._stampIndex ? "true" : "false");
        btn.addEventListener("click", function () {
          root.ZintriqWorkbench._stampIndex = index;
          root.ZintriqWorkbench.paintStatus();
        });
        bar.appendChild(btn);
      });
      bar.onkeydown = function (ev) {
        if (!stamps.length) return;
        if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
          ev.preventDefault();
          const n = stamps.length;
          const cur = Number(root.ZintriqWorkbench._stampIndex) || 0;
          root.ZintriqWorkbench._stampIndex = ev.key === "ArrowRight" ? (cur + 1) % n : (cur - 1 + n) % n;
          root.ZintriqWorkbench.paintStatus();
          const next = document.getElementById("me-statusbar");
          if (next) next.focus();
        }
        if (ev.key === "Enter") {
          ev.preventDefault();
          const row = stamps[root.ZintriqWorkbench._stampIndex] || stamps[0];
          root.ZintriqWorkbench.restoreStamp(row);
        }
      };
    },
    bind: function () {
      if (document.documentElement.getAttribute("data-workbench-bound") === "1") return;
      document.documentElement.setAttribute("data-workbench-bound", "1");
      const engine = root.ZintriqEngine;
      if (engine && engine.command) {
        engine.command.register("workbench.palette", function () {
          root.ZintriqWorkbench.palette.open();
        }, { title: "Command palette", keys: "Ctrl+K" }, "workbench");
      }
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape" && document.getElementById("wb-rebind-drawer")) {
          ev.preventDefault();
          root.ZintriqWorkbench.closeRebindDrawer();
          return;
        }
        const typing = ev.target && (ev.target.tagName === "INPUT" || ev.target.tagName === "TEXTAREA" || ev.target.isContentEditable);
        if ((ev.metaKey || ev.ctrlKey) && String(ev.key || "").toLowerCase() === "k" && !typing) {
          ev.preventDefault();
          root.ZintriqWorkbench.palette.open();
        }
      });
      if (engine && engine.on) engine.on(function () {
        root.ZintriqWorkbench.paintStatus();
        if (root.zintriqDesktop && root.zintriqDesktop.setDirty) {
          root.zintriqDesktop.setDirty(true);
        }
      });
      root.ZintriqWorkbench.paintStatus();
      root.ZintriqWorkbench.bindDock();
      document.querySelectorAll(".wb-modes [data-editor-view]").forEach(function (button) {
        button.addEventListener("click", function () {
          if (root.ZintriqEditorViews) return;
          root.ZintriqWorkbench.switchView(button.getAttribute("data-editor-view") || "");
        });
      });
      const modesRail = document.querySelector(".wb-modes");
      function restoreModesScroll(layout) {
        if (!modesRail) return;
        let scroll = 0;
        if (layout && layout.modesScroll != null) scroll = Number(layout.modesScroll) || 0;
        else {
          try {
            scroll = Number(localStorage.getItem("zintriq-modes-scroll") || 0) || 0;
          } catch (_err) {
            scroll = 0;
          }
        }
        root.ZintriqWorkbench._modesScroll = scroll;
        modesRail.scrollLeft = scroll;
        let pane = "";
        try {
          pane = new URLSearchParams(root.location.search).get("pane") || "";
        } catch (_err2) {
          pane = "";
        }
        if (!pane && layout && layout.pane) pane = layout.pane;
        if (!pane) {
          try {
            pane = localStorage.getItem("zintriq-modes-pane") || "";
          } catch (_err3) {
            pane = "";
          }
        }
        const modeBtn = pane ? document.querySelector('.wb-modes [data-editor-view="' + pane + '"]') : null;
        if (modeBtn && typeof modeBtn.scrollIntoView === "function") {
          modeBtn.scrollIntoView({ inline: "nearest", block: "nearest" });
          modeBtn.classList.add("is-current");
        }
      }
      if (modesRail && modesRail.getAttribute("data-scroll-bound") !== "1") {
        modesRail.setAttribute("data-scroll-bound", "1");
        let scrollTimer;
        modesRail.addEventListener(
          "scroll",
          function () {
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(function () {
              const left = Math.max(0, Math.floor(modesRail.scrollLeft || 0));
              root.ZintriqWorkbench._modesScroll = left;
              try {
                localStorage.setItem("zintriq-modes-scroll", String(left));
                const pane =
                  (document.body && document.body.getAttribute("data-editor-view")) ||
                  (document.querySelector(".wb-modes .is-current") &&
                    document.querySelector(".wb-modes .is-current").getAttribute("data-editor-view")) ||
                  "";
                if (pane) localStorage.setItem("zintriq-modes-pane", pane);
              } catch (_err) {
                /* ignore */
              }
              if (typeof root.ZintriqWorkbench.persistDock === "function") {
                root.ZintriqWorkbench.persistDock(root.ZintriqWorkbench.snapshotLayout());
              }
            }, 120);
          },
          { passive: true }
        );
      }
      try {
        restoreModesScroll(null);
      } catch (_err) {
        /* ignore */
      }
      function refreshGit() {
        if (!root.zintriqDesktop || !root.zintriqDesktop.gitStatus) return;
        root.zintriqDesktop.gitStatus().then(function (row) {
          const dirty = [];
          String((row && row.text) || "")
            .split("\n")
            .forEach(function (line) {
              const match = line.match(/drafts\/([A-Za-z0-9._-]+)\.json/);
              if (match) dirty.push(match[1]);
            });
          root.ZintriqWorkbench._gitDirty = dirty;
          root.ZintriqWorkbench.paintStatus();
        }).catch(function () {});
      }
      refreshGit();
      root.setInterval(refreshGit, 8000);
      if (root.zintriqDesktop && root.zintriqDesktop.loadLayout) {
        root.zintriqDesktop.loadLayout().then(function (layout) {
          root.ZintriqWorkbench.applyDock(layout || {});
          root.ZintriqWorkbench.bindDock();
          restoreModesScroll(layout || {});
        }).catch(function () {});
      }
      if (root.zintriq && root.zintriq.http && root.zintriq.http.get) {
        root.zintriq.http.get("/api/builder-core/meta/layout").then(function (res) {
          return res.json();
        }).then(function (layout) {
          if (layout && (layout.tree || layout.edge || (layout.groups && layout.groups.length))) {
            root.ZintriqWorkbench.applyDock(layout);
            root.ZintriqWorkbench.bindDock();
          }
          if (layout) restoreModesScroll(layout);
        }).catch(function () {});
        root.ZintriqWorkbench.refreshRebinds();
      }
      function applyRemoteLayout(layout) {
        root.__zintriqPendingLayout = layout || {};
        clearTimeout(root.__zintriqLayoutTimer);
        const wait =
          typeof root.ZintriqWorkbench.layoutDebounceMs === "function"
            ? root.ZintriqWorkbench.layoutDebounceMs()
            : 120;
        root.__zintriqLayoutTimer = root.setTimeout(function () {
          const next = root.__zintriqPendingLayout || {};
          root.__zintriqPendingLayout = null;
          root.ZintriqWorkbench.applyDock(next);
          restoreModesScroll(next);
        }, wait);
      }
      if (root.zintriqDesktop && root.zintriqDesktop.onLayout) {
        root.zintriqDesktop.onLayout(function (layout) {
          applyRemoteLayout(layout || {});
        });
      }
      try {
        if (root.BroadcastChannel) {
          if (!root.__zintriqLayoutChannel) {
            root.__zintriqLayoutChannel = new BroadcastChannel("zintriq-layout");
          }
          root.__zintriqLayoutChannel.onmessage = function (ev) {
            const layout = (ev && ev.data) || {};
            if (!layout || layout.__from === root.__zintriqLayoutId) return;
            applyRemoteLayout(layout);
          };
          if (!root.__zintriqLayoutId) {
            root.__zintriqLayoutId = "w" + String(Date.now()) + Math.random().toString(16).slice(2);
          }
        }
      } catch (_layoutBus) {
        /* ignore */
      }
      if (!root.__zintriqWindowId) {
        root.__zintriqWindowId = "w" + String(Date.now()) + Math.random().toString(16).slice(2);
      }
      function onBindingCleared(detail, fromBus) {
        const row = detail || {};
        if (fromBus && row.__from && row.__from === root.__zintriqWindowId) return;
        root.ZintriqWorkbench.refreshRebinds({
          clearedId: row.id || "",
          clearedSlug: row.slug || "",
        });
      }
      root.addEventListener("zintriq-binding-cleared", function (ev) {
        onBindingCleared((ev && ev.detail) || {}, false);
      });
      try {
        if (root.BroadcastChannel) {
          if (!root.__zintriqBindingChannel) {
            root.__zintriqBindingChannel = new BroadcastChannel("zintriq-binding");
          }
          root.__zintriqBindingChannel.onmessage = function (ev) {
            onBindingCleared((ev && ev.data) || {}, true);
          };
        }
      } catch (_bindBus) {
        /* ignore */
      }
      if (root.zintriqDesktop && root.zintriqDesktop.probe) {
        root.zintriqDesktop.probe().then(function (info) {
          const bar = document.getElementById("me-statusbar");
          if (bar && info) bar.dataset.platform = info.platform || "";
        }).catch(function () {});
      }
      root.ZintriqWorkbench.bindAssistant();
      root.addEventListener("zintriq-plugins-changed", function () {
        if (root.ZintriqWorkbench.palette && typeof root.ZintriqWorkbench.palette.repaint === "function") {
          root.ZintriqWorkbench.palette.repaint();
        }
      });
    },
    applyDock: function (layout) {
      const split = document.querySelector(".me-split");
      if (!split) return;
      split.classList.add("wb-dock");
      if (layout && Array.isArray(layout.pinned)) root.ZintriqWorkbench._pinned = layout.pinned;
      if (layout && Array.isArray(layout.queries)) root.ZintriqWorkbench._queries = layout.queries;
      if (layout && layout.workspace) root.ZintriqWorkbench._workspace = String(layout.workspace || "default");
      if (layout && layout.recentByWorkspace && typeof layout.recentByWorkspace === "object") {
        root.ZintriqWorkbench._recentByWorkspace = layout.recentByWorkspace;
      }
      if (layout && Array.isArray(layout.recentCommands)) {
        const recents = layout.recentCommands.map(function (id) { return String(id || ""); }).filter(Boolean).slice(0, 8);
        if (typeof root.ZintriqWorkbench.setRecentForWorkspace === "function") root.ZintriqWorkbench.setRecentForWorkspace(recents);
        else {
          root.ZintriqWorkbench._recentCommands = recents;
          if (root.ZintriqEngine && root.ZintriqEngine.command) root.ZintriqEngine.command._recent = recents;
        }
      } else if (layout && layout.recentByWorkspace) {
        const ws = root.ZintriqWorkbench._workspace || "default";
        const recents = (layout.recentByWorkspace[ws] || []).slice(0, 8);
        if (typeof root.ZintriqWorkbench.setRecentForWorkspace === "function") root.ZintriqWorkbench.setRecentForWorkspace(recents);
      }
      if (layout && layout.pane && root.ZintriqEditorViews) {
        root.ZintriqEditorViews.activate(layout.pane);
      }
      if (layout && Array.isArray(layout.groups) && layout.groups.length) {
        root.ZintriqWorkbench._groups = layout.groups;
        root.ZintriqWorkbench._activeGroup = Math.max(0, parseInt(layout.activeGroup, 10) || 0);
        const group = layout.groups[root.ZintriqWorkbench._activeGroup] || layout.groups[0];
        if (group && group.tree) {
          layout = Object.assign({}, layout, { tree: group.tree, max: group.max || layout.max || "" });
        }
      }
      const tree = (layout && layout.tree) || root.ZintriqWorkbench.defaultTree(layout);
      root.ZintriqWorkbench._tree = tree;
      root.ZintriqWorkbench._max = (layout && layout.max) || "";
      root.ZintriqWorkbench.renderTree(split, tree);
      const edge = (layout && layout.edge) || "right";
      split.setAttribute("data-dock-edge", edge);
      if (!layout || !layout.tree) {
        const cols = (layout && layout.columns) || (edge === "left" ? "16rem 1fr" : edge === "bottom" ? "1fr" : "1fr 16rem");
        split.style.gridTemplateColumns = cols;
        if (edge === "bottom") split.style.gridTemplateRows = "1fr minmax(8rem, 14rem)";
        else split.style.gridTemplateRows = "";
      } else {
        split.style.gridTemplateColumns = "1fr";
        split.style.gridTemplateRows = "1fr";
      }
      if (layout && layout.pane && document.body) {
        document.body.setAttribute("data-editor-view", layout.pane);
      }
    },
    defaultTree: function (layout) {
      const split = document.querySelector(".me-split");
      const panes = split ? Array.prototype.slice.call(split.querySelectorAll(".me-pane")) : [];
      panes.forEach(function (pane, i) {
        if (!pane.getAttribute("data-dock-id")) {
          pane.setAttribute("data-dock-id", pane.getAttribute("data-editor-pane") || "pane-" + i);
        }
      });
      if (panes.length < 2) {
        return { type: "leaf", id: panes[0] ? panes[0].getAttribute("data-dock-id") : "code" };
      }
      const edge = (layout && layout.edge) || "right";
      const a = { type: "leaf", id: panes[0].getAttribute("data-dock-id") };
      const b = { type: "leaf", id: panes[1].getAttribute("data-dock-id") };
      if (edge === "left") return { type: "split", dir: "h", ratio: 0.28, a: b, b: a };
      if (edge === "bottom") return { type: "split", dir: "v", ratio: 0.68, a: a, b: b };
      return { type: "split", dir: "h", ratio: 0.55, a: a, b: b };
    },
    renderTree: function (split, tree) {
      const panes = {};
      Array.prototype.slice.call(split.querySelectorAll(".me-pane")).forEach(function (pane) {
        const id = pane.getAttribute("data-dock-id");
        if (id) panes[id] = pane;
      });
      Array.prototype.slice.call(split.querySelectorAll(".wb-tree, .wb-drop[data-leaf]")).forEach(function (node) {
        node.remove();
      });
      const host = document.createElement("div");
      host.className = "wb-tree";
      function mount(node, parent) {
        if (!node) return;
        if (node.type === "leaf" || node.type === "stack") {
          const ids = node.type === "stack" ? node.ids || [] : [node.id];
          const active = node.active || ids[0];
          const leaf = document.createElement("div");
          leaf.className = "wb-leaf";
          leaf.setAttribute("data-leaf", active || ids[0] || "");
          if (root.ZintriqWorkbench._max && ids.indexOf(root.ZintriqWorkbench._max) >= 0) {
            leaf.classList.add("is-max");
            host.classList.add("is-max");
          }
          if (ids.length > 1) {
            const tabs = document.createElement("div");
            tabs.className = "wb-tabs";
            ids.forEach(function (id) {
              const tab = document.createElement("button");
              tab.type = "button";
              tab.className = "wb-tab" + (id === active ? " is-active" : "");
              tab.textContent = id;
              tab.setAttribute("data-dock-tab", id);
              tab.addEventListener("click", function () {
                node.active = id;
                root.ZintriqWorkbench.applyDock({ tree: root.ZintriqWorkbench._tree, max: root.ZintriqWorkbench._max });
                root.ZintriqWorkbench.persistDock({ tree: root.ZintriqWorkbench._tree, max: root.ZintriqWorkbench._max });
              });
              tab.addEventListener("contextmenu", function (ev) {
                ev.preventDefault();
                root.ZintriqWorkbench.togglePin(id);
              });
              tabs.appendChild(tab);
            });
            const pinBtn = document.createElement("button");
            pinBtn.type = "button";
            pinBtn.className = "wb-tab wb-tab--pin";
            pinBtn.textContent = (root.ZintriqWorkbench._pinned || []).indexOf(active) >= 0 ? "Unpin" : "Pin";
            pinBtn.addEventListener("click", function () {
              root.ZintriqWorkbench.togglePin(active);
            });
            tabs.appendChild(pinBtn);
            const maxBtn = document.createElement("button");
            maxBtn.type = "button";
            maxBtn.className = "wb-tab wb-tab--max";
            maxBtn.textContent = root.ZintriqWorkbench._max ? "Restore" : "Max";
            maxBtn.addEventListener("click", function () {
              root.ZintriqWorkbench.toggleMax(active);
            });
            tabs.appendChild(maxBtn);
            leaf.appendChild(tabs);
          }
          ids.forEach(function (id) {
            const pane = panes[id];
            if (!pane) return;
            pane.hidden = id !== active;
            leaf.appendChild(pane);
          });
          ["left", "right", "top", "bottom", "stack"].forEach(function (edge) {
            const zone = document.createElement("div");
            zone.className = "wb-drop wb-drop--" + edge;
            zone.setAttribute("data-dock-drop", edge);
            zone.setAttribute("data-leaf", active || ids[0] || "");
            leaf.appendChild(zone);
          });
          parent.appendChild(leaf);
          return;
        }
        const wrap = document.createElement("div");
        wrap.className = "wb-split";
        wrap.setAttribute("data-dir", node.dir === "v" ? "v" : "h");
        const first = document.createElement("div");
        first.className = "wb-split__pane";
        first.style.flex = String(node.ratio || 0.5);
        const sash = document.createElement("div");
        sash.className = "wb-sash";
        sash.setAttribute("data-sash", node.dir === "v" ? "v" : "h");
        const second = document.createElement("div");
        second.className = "wb-split__pane";
        second.style.flex = String(1 - (node.ratio || 0.5));
        mount(node.a, first);
        mount(node.b, second);
        wrap.appendChild(first);
        wrap.appendChild(sash);
        wrap.appendChild(second);
        parent.appendChild(wrap);
      }
      mount(tree, host);
      split.insertBefore(host, split.firstChild);
    },
    removeLeaf: function (node, id) {
      if (!node) return null;
      if (node.type === "leaf") return node.id === id ? null : node;
      if (node.type === "stack") {
        const ids = (node.ids || []).filter(function (item) { return item !== id; });
        if (!ids.length) return null;
        if (ids.length === 1) return { type: "leaf", id: ids[0] };
        return { type: "stack", ids: ids, active: node.active === id ? ids[0] : node.active };
      }
      const a = root.ZintriqWorkbench.removeLeaf(node.a, id);
      const b = root.ZintriqWorkbench.removeLeaf(node.b, id);
      if (!a) return b;
      if (!b) return a;
      return { type: "split", dir: node.dir, ratio: node.ratio, a: a, b: b };
    },
    pushStack: function (node, targetId, movingId) {
      if (!node) return node;
      if (node.type === "leaf" && node.id === targetId) {
        return { type: "stack", ids: [targetId, movingId], active: movingId };
      }
      if (node.type === "stack" && (node.ids || []).indexOf(targetId) >= 0) {
        const ids = node.ids.slice();
        if (ids.indexOf(movingId) < 0) ids.push(movingId);
        return { type: "stack", ids: ids, active: movingId };
      }
      if (node.type === "split") {
        return {
          type: "split",
          dir: node.dir,
          ratio: node.ratio,
          a: root.ZintriqWorkbench.pushStack(node.a, targetId, movingId),
          b: root.ZintriqWorkbench.pushStack(node.b, targetId, movingId),
        };
      }
      return node;
    },
    snapshotLayout: function (partial) {
      const patch = partial || {};
      const groups = (root.ZintriqWorkbench._groups || []).slice();
      const active = root.ZintriqWorkbench._activeGroup || 0;
      const current = {
        editors: patch.editors || [{ id: (patch.tree && patch.tree.id) || "code", preview: false }],
        id: "g" + active,
        max: patch.max != null ? patch.max : root.ZintriqWorkbench._max || "",
        size: 1,
        tree: patch.tree || root.ZintriqWorkbench._tree,
      };
      if (!groups.length) groups.push(current);
      else groups[active] = Object.assign({}, groups[active] || {}, current);
      return {
        activeGroup: active,
        groups: groups,
        max: current.max,
        orientation: root.ZintriqWorkbench._orientation || "horizontal",
        tree: current.tree,
        version: 8,
        workspace: root.ZintriqWorkbench._workspace || "default",
        pinned: root.ZintriqWorkbench._pinned || [],
        activity: root.ZintriqWorkbench._activity || "explorer",
        sidebar: root.ZintriqWorkbench._sidebar !== false,
        panel: root.ZintriqWorkbench._panel || 0.28,
        zen: !!root.ZintriqWorkbench._zen,
        panelTab: root.ZintriqWorkbench._panelTab || "output",
        columns: root.ZintriqWorkbench._columns || 1,
        profiles: root.ZintriqWorkbench._profiles || {},
        mru: root.ZintriqWorkbench._mru || [],
        sidebarWidth: root.ZintriqWorkbench._sidebarWidth || 0.22,
        auxiliary: !!root.ZintriqWorkbench._auxiliary,
        sticky: root.ZintriqWorkbench._sticky || [],
        pane: (document.body && document.body.getAttribute("data-editor-view")) || "",
        modesScroll: (function () {
          const modes = document.querySelector(".wb-modes");
          return modes ? Math.max(0, Math.floor(modes.scrollLeft || 0)) : root.ZintriqWorkbench._modesScroll || 0;
        })(),
        queries: root.ZintriqWorkbench._queries || [],
        recentCommands: root.ZintriqWorkbench.recentForWorkspace ? root.ZintriqWorkbench.recentForWorkspace() : (root.ZintriqWorkbench._recentCommands || []),
        recentByWorkspace: (function () {
          const ws = root.ZintriqWorkbench._workspace || "default";
          const by = Object.assign({}, root.ZintriqWorkbench._recentByWorkspace || {});
          by[ws] = root.ZintriqWorkbench.recentForWorkspace ? root.ZintriqWorkbench.recentForWorkspace() : (root.ZintriqWorkbench._recentCommands || []);
          return by;
        })(),
      };
    },
    splitGroup: function (direction) {
      const snap = root.ZintriqWorkbench.snapshotLayout();
      const copy = Object.assign({}, snap.groups[snap.activeGroup] || {}, { id: "g" + snap.groups.length });
      if (direction === "left" || direction === "up") snap.groups.splice(snap.activeGroup, 0, copy);
      else {
        snap.groups.splice(snap.activeGroup + 1, 0, copy);
        snap.activeGroup += 1;
      }
      snap.orientation = direction === "up" || direction === "down" ? "vertical" : "horizontal";
      root.ZintriqWorkbench._orientation = snap.orientation;
      root.ZintriqWorkbench._groups = snap.groups;
      root.ZintriqWorkbench._activeGroup = snap.activeGroup;
      root.ZintriqWorkbench.applyDock(snap);
      root.ZintriqWorkbench.persistDock(snap);
    },
    togglePin: function (id) {
      const ident = String(id || "");
      const pinned = (root.ZintriqWorkbench._pinned || []).slice();
      const at = pinned.indexOf(ident);
      if (at >= 0) pinned.splice(at, 1);
      else if (ident) pinned.push(ident);
      root.ZintriqWorkbench._pinned = pinned;
      const snap = root.ZintriqWorkbench.snapshotLayout();
      snap.pinned = pinned;
      root.ZintriqWorkbench.applyDock(snap);
      root.ZintriqWorkbench.persistDock(snap);
    },
    closeGroup: function () {
      const snap = root.ZintriqWorkbench.snapshotLayout();
      if (snap.groups.length <= 1) return;
      snap.groups.splice(snap.activeGroup, 1);
      snap.activeGroup = Math.max(0, Math.min(snap.activeGroup, snap.groups.length - 1));
      root.ZintriqWorkbench._groups = snap.groups;
      root.ZintriqWorkbench._activeGroup = snap.activeGroup;
      root.ZintriqWorkbench.applyDock(snap);
      root.ZintriqWorkbench.persistDock(snap);
    },
    addGroup: function () {
      const snap = root.ZintriqWorkbench.snapshotLayout();
      snap.groups.push({ max: "", tree: root.ZintriqWorkbench.defaultTree({}) });
      snap.activeGroup = snap.groups.length - 1;
      root.ZintriqWorkbench._groups = snap.groups;
      root.ZintriqWorkbench._activeGroup = snap.activeGroup;
      root.ZintriqWorkbench.applyDock(snap);
      root.ZintriqWorkbench.persistDock(snap);
    },
    toggleMax: function (id) {
      root.ZintriqWorkbench._max = root.ZintriqWorkbench._max === id ? "" : id;
      const layout = root.ZintriqWorkbench.snapshotLayout({
        tree: root.ZintriqWorkbench._tree,
        max: root.ZintriqWorkbench._max,
      });
      root.ZintriqWorkbench.applyDock(layout);
      root.ZintriqWorkbench.persistDock(layout);
    },
    cycleMru: function () {
      const mru = root.ZintriqWorkbench._mru || [];
      if (mru.length < 2) return;
      root.ZintriqWorkbench._activeId = mru[1];
      const layout = root.ZintriqWorkbench.snapshotLayout({});
      layout.mru = mru.slice();
      root.ZintriqWorkbench.applyDock(layout);
      root.ZintriqWorkbench.persistDock(layout);
    },
    insertSplit: function (node, targetId, edge, movingId) {
      if (!node) return node;
      if (node.type === "leaf" && node.id === targetId) {
        const incoming = { type: "leaf", id: movingId };
        const stay = { type: "leaf", id: targetId };
        const dir = edge === "left" || edge === "right" ? "h" : "v";
        if (edge === "left" || edge === "top") return { type: "split", dir: dir, ratio: 0.5, a: incoming, b: stay };
        return { type: "split", dir: dir, ratio: 0.5, a: stay, b: incoming };
      }
      if (node.type === "stack" && (node.ids || []).indexOf(targetId) >= 0) {
        const incoming = { type: "leaf", id: movingId };
        const dir = edge === "left" || edge === "right" ? "h" : "v";
        if (edge === "left" || edge === "top") return { type: "split", dir: dir, ratio: 0.5, a: incoming, b: node };
        return { type: "split", dir: dir, ratio: 0.5, a: node, b: incoming };
      }
      if (node.type === "split") {
        return {
          type: "split",
          dir: node.dir,
          ratio: node.ratio,
          a: root.ZintriqWorkbench.insertSplit(node.a, targetId, edge, movingId),
          b: root.ZintriqWorkbench.insertSplit(node.b, targetId, edge, movingId),
        };
      }
      return node;
    },
    persistDock: function (layout) {
      const payload = root.ZintriqWorkbench.snapshotLayout(layout || {});
      root.ZintriqWorkbench._groups = payload.groups;
      if (root.zintriqDesktop && root.zintriqDesktop.saveLayout) {
        root.zintriqDesktop.saveLayout(payload);
      }
      if (root.zintriq && root.zintriq.http && root.zintriq.http.post) {
        root.zintriq.http.post("/api/builder-core/meta/layout", payload);
      }
      try {
        if (root.__zintriqLayoutChannel) {
          const msg = Object.assign({}, payload, { __from: root.__zintriqLayoutId || "" });
          root.__zintriqLayoutChannel.postMessage(msg);
        }
      } catch (_bus) {
        /* ignore */
      }
    },
    bindDock: function () {
      const split = document.querySelector(".me-split");
      if (!split) return;
      if (split.getAttribute("data-dock-bound") !== "1") {
        split.setAttribute("data-dock-bound", "1");
        ["left", "right", "bottom"].forEach(function (edge) {
          const zone = document.createElement("div");
          zone.className = "wb-drop wb-drop--" + edge;
          zone.setAttribute("data-dock-drop", edge);
          zone.setAttribute("aria-hidden", "true");
          split.appendChild(zone);
        });
        split.addEventListener("dragover", function (ev) {
          const zone = ev.target.closest("[data-dock-drop]");
          if (!zone) return;
          ev.preventDefault();
          zone.classList.add("is-over");
        });
        split.addEventListener("dragleave", function (ev) {
          const zone = ev.target.closest("[data-dock-drop]");
          if (zone) zone.classList.remove("is-over");
        });
        split.addEventListener("drop", function (ev) {
          const zone = ev.target.closest("[data-dock-drop]");
          if (!zone) return;
          ev.preventDefault();
          zone.classList.remove("is-over");
          const edge = zone.getAttribute("data-dock-drop");
          const leaf = zone.getAttribute("data-leaf");
          const moving = ev.dataTransfer.getData("text/plain") || "";
          let layout;
          if (leaf && moving && moving !== leaf) {
            let tree = root.ZintriqWorkbench.removeLeaf(root.ZintriqWorkbench._tree || root.ZintriqWorkbench.defaultTree(), moving);
            if (edge === "stack") tree = root.ZintriqWorkbench.pushStack(tree, leaf, moving);
            else tree = root.ZintriqWorkbench.insertSplit(tree, leaf, edge, moving);
            layout = root.ZintriqWorkbench.snapshotLayout({ tree: tree, max: root.ZintriqWorkbench._max || "" });
          } else {
            layout = { edge: edge };
          }
          root.ZintriqWorkbench.applyDock(layout);
          root.ZintriqWorkbench.persistDock(layout);
        });
      }
      split.querySelectorAll(".me-pane").forEach(function (pane) {
        pane.setAttribute("draggable", "true");
        pane.addEventListener("dragstart", function (ev) {
          ev.dataTransfer.setData("text/plain", pane.getAttribute("data-dock-id") || "pane");
          pane.classList.add("is-dragging");
        });
        pane.addEventListener("dragend", function () {
          pane.classList.remove("is-dragging");
        });
      });
    },
    bindAssistant: function (hooks) {
      const rootEl = document.querySelector(".me-body");
      if (!rootEl) {
        if (hooks) root.ZintriqWorkbench._assistantHooks = hooks;
        return;
      }
      if (rootEl.getAttribute("data-assistant-bound") === "1") {
        if (hooks) root.ZintriqWorkbench._assistantHooks = hooks;
        return;
      }
      rootEl.setAttribute("data-assistant-bound", "1");
      root.ZintriqWorkbench._assistantHooks = hooks || root.ZintriqWorkbench._assistantHooks || {};
      const panel = document.createElement("aside");
      panel.id = "wb-assistant";
      panel.className = "wb-assistant";
      panel.innerHTML =
        '<label class="wb-assistant__toggle"><input type="checkbox" data-assistant-on checked> Local assistant</label>' +
        '<textarea data-assistant-prompt rows="3" placeholder="Suggest a part, draft a Desc, or explain instantiate"></textarea>' +
        '<div class="wb-assistant__row">' +
        '<button type="button" data-assistant-act="add_part">Suggest part</button>' +
        '<button type="button" data-assistant-act="produce">Make</button>' +
        '<button type="button" data-assistant-act="draft">Draft Desc</button>' +
        '<button type="button" data-assistant-act="explain">Explain error</button>' +
        "</div>" +
        '<pre class="wb-assistant__log" data-assistant-log></pre>';
      rootEl.appendChild(panel);
      const on = panel.querySelector("[data-assistant-on]");
      const log = panel.querySelector("[data-assistant-log]");
      try {
        on.checked = window.localStorage.getItem("zintriq.assistant.off") !== "1";
      } catch (err) {
        on.checked = true;
      }
      panel.hidden = !on.checked;
      on.addEventListener("change", function () {
        panel.hidden = !on.checked;
        try {
          window.localStorage.setItem("zintriq.assistant.off", on.checked ? "0" : "1");
        } catch (err) {}
      });
      function http() {
        return root.zintriq && root.zintriq.http;
      }
      function code() {
        const hook = root.ZintriqWorkbench._assistantHooks || {};
        if (hook.getCode) return hook.getCode();
        const el = document.getElementById("me-code");
        return el ? el.value : "";
      }
      function setCode(text) {
        const hook = root.ZintriqWorkbench._assistantHooks || {};
        if (hook.setCode) {
          hook.setCode(text);
          return;
        }
        const el = document.getElementById("me-code");
        if (el) el.value = text;
      }
      panel.querySelectorAll("[data-assistant-act]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          const api = http();
          if (!api || !api.post) {
            log.textContent = "no desktop http";
            return;
          }
          if (!on.checked) {
            log.textContent = "assistant off";
            return;
          }
          const act = btn.getAttribute("data-assistant-act");
          const prompt = (panel.querySelector("[data-assistant-prompt]") || {}).value || "";
          if (act === "produce") {
            const slugEl = document.getElementById("me-slug");
            api
              .post("/api/builder-core/meta/produce", {
                prompt: prompt || "scene",
                slug: slugEl ? slugEl.value : "made",
              })
              .then(function (res) {
                return res.json().then(function (body) {
                  if (body && body.code) setCode(body.code);
                  log.textContent = JSON.stringify(body);
                  if (root.ZintriqWorkbench._assistantHooks && root.ZintriqWorkbench._assistantHooks.onProduce) {
                    root.ZintriqWorkbench._assistantHooks.onProduce(body, res.ok);
                  }
                });
              })
              .catch(function (err) {
                log.textContent = String(err && err.message ? err.message : err);
              });
            return;
          }
          if (act === "draft") {
            api
              .post("/api/builder-core/meta/ai/chat", {
                prompt: prompt || "scene with a cube",
                system: "Output only a Zintriq Desc JSON struct. Local weights. Not OpenAI.",
                max_tokens: 256,
              })
              .then(function (res) {
                return res.json();
              })
              .then(function (body) {
                const text = String((body && body.output) || "");
                const start = text.indexOf("{");
                const end = text.lastIndexOf("}");
                if (start >= 0 && end > start) setCode(text.slice(start, end + 1));
                log.textContent = text || JSON.stringify(body);
              })
              .catch(function (err) {
                log.textContent = String(err && err.message ? err.message : err);
              });
            return;
          }
          const tool = act === "explain" ? "explain" : "add_part";
          const args =
            tool === "explain"
              ? { error: prompt || (root._zintriqInstantiateError || "instantiate error") }
              : { key: "assistant-part", title: prompt || "Suggested", kind: "scene" };
          api
            .post("/api/builder-core/meta/ai/tools", { tool: tool, args: args, code: code() })
            .then(function (res) {
              return res.json();
            })
            .then(function (body) {
              if (body && body.code) setCode(body.code);
              log.textContent = JSON.stringify(body);
            })
            .catch(function (err) {
              log.textContent = String(err && err.message ? err.message : err);
            });
        });
      });
    },
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      root.ZintriqWorkbench.bind();
    });
  } else {
    root.ZintriqWorkbench.bind();
  }
})(window);
