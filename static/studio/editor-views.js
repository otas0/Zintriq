(function (root) {
  const plugins = {};
  const hostBindings = new WeakMap();
  const sandboxes = {};
  let documentApi = null;
  let bootTimer = 0;

  function surfaceOf() {
    return document.body.getAttribute("data-meta-view") || "describe";
  }

  function rememberPane(id) {
    try {
      const url = new URL(root.location.href);
      url.searchParams.set("pane", id);
      root.history.replaceState({}, "", url);
    } catch (_err) {
      /* ignore */
    }
  }

  function hostOf(plugin) {
    if (!plugin) return null;
    if (plugin.pane === "plugin") return document.getElementById("me-plugin-host");
    return document.querySelector('[data-editor-pane="' + plugin.pane + '"]');
  }

  function clearHost(host) {
    if (!host) return;
    host.innerHTML = "";
    const bound = hostBindings.get(host);
    if (bound) {
      bound.forEach(function (row) {
        host.removeEventListener(row.type, row.fn);
      });
      hostBindings.delete(host);
    }
    host.removeAttribute("data-plugin-bound");
  }

  function contextFor(plugin) {
    const api = documentApi || {};
    return {
      surface: surfaceOf(),
      plugin: plugin,
      host: hostOf(plugin),
      visual: typeof api.visual === "function" ? api.visual() : null,
      preview: typeof api.preview === "function" ? api.preview() : null,
      applyVisual: api.applyVisual,
      applyCode: api.applyCode,
      engine: root.ZintriqEngine || null,
    };
  }

  function bindPropsPanel(panel) {
    if (!panel || panel.getAttribute("data-props-bound") === "1") return;
    panel.setAttribute("data-props-bound", "1");
    panel.addEventListener("change", function (event) {
      const el = event.target;
      if (!el) return;
      const current = activePlugin();
      if (!current || typeof current.edit !== "function") return;
      const ctx = contextFor(current);
      if (el.getAttribute("data-field-id")) {
        current.edit(
          {
            type: "set",
            id: el.getAttribute("data-field-id"),
            fieldType: el.getAttribute("data-field-type"),
            value: el.value,
          },
          ctx
        );
      }
      if (el.getAttribute("data-view-node")) {
        current.edit(
          {
            type: "view",
            id: el.getAttribute("data-view-node"),
            field: el.getAttribute("data-view-field"),
            value: el.value,
            panel: panel,
          },
          ctx
        );
      }
    });
  }

  function paint(plugin) {
    if (!plugin || typeof plugin.render !== "function") return;
    const ctx = contextFor(plugin);
    if (!ctx.host) return;
    plugin.render(ctx.host, ctx);
    const panel = document.getElementById("me-props");
    if (panel && typeof plugin.getPropertyPanel === "function") {
      panel.hidden = false;
      panel.innerHTML = plugin.getPropertyPanel(ctx) || "";
      bindPropsPanel(panel);
    } else if (panel) {
      panel.innerHTML = "";
    }
  }

  function activePlugin() {
    return plugins[document.body.getAttribute("data-editor-view") || ""] || null;
  }

  function bindHost(plugin) {
    const host = hostOf(plugin);
    if (!host || host.getAttribute("data-plugin-bound") === "1") return;
    host.setAttribute("data-plugin-bound", "1");
    const onPointer = function (event) {
      const current = activePlugin();
      if (!current || typeof current.hitTest !== "function") return;
      if (hostOf(current) !== host) return;
      const hit = current.hitTest(event, contextFor(current));
      if (!hit || !hit.id) return;
      event.preventDefault();
      if (root.ZintriqEngine) root.ZintriqEngine.selection.set([hit.id]);
      if (typeof current.edit === "function") {
        current.edit({ type: "select", id: hit.id, node: hit.node || null }, contextFor(current));
      }
      paint(current);
    };
    const onDbl = function (event) {
      const current = activePlugin();
      if (!current || typeof current.hitTest !== "function" || typeof current.edit !== "function") return;
      if (hostOf(current) !== host) return;
      const hit = current.hitTest(event, contextFor(current));
      if (!hit || !hit.id) return;
      event.preventDefault();
      current.edit({ type: "open", id: hit.id, node: hit.node || null }, contextFor(current));
    };
    host.addEventListener("pointerdown", onPointer);
    host.addEventListener("dblclick", onDbl);
    hostBindings.set(host, [
      { type: "pointerdown", fn: onPointer },
      { type: "dblclick", fn: onDbl },
    ]);
  }

  function destroySandbox(id) {
    const frame = sandboxes[id];
    if (!frame) return;
    if (frame.parentNode) frame.parentNode.removeChild(frame);
    delete sandboxes[id];
  }

  function mountSandbox(plugin) {
    destroySandbox(plugin.id);
    if (!plugin.sandbox) return null;
    const host = hostOf(plugin);
    if (!host) return null;
    const frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts");
    frame.setAttribute("title", plugin.name + " sandbox");
    frame.setAttribute("data-plugin-sandbox", plugin.id);
    frame.style.width = "100%";
    frame.style.height = "100%";
    frame.style.border = "0";
    host.appendChild(frame);
    sandboxes[plugin.id] = frame;
    return frame;
  }

  function unloadPlugin(id, keepRegistered) {
    const plugin = plugins[id];
    if (!plugin) return false;
    const wasActive = document.body.getAttribute("data-editor-view") === id;
    destroySandbox(id);
    if (!keepRegistered && root.ZintriqEngine && typeof root.ZintriqEngine.command.unregisterOwner === "function") {
      root.ZintriqEngine.command.unregisterOwner(id);
    }
    if (typeof plugin.deactivate === "function") {
      try {
        plugin.deactivate();
      } catch (_err) {
        /* unload must continue */
      }
    }
    if (!keepRegistered && typeof plugin.dispose === "function") {
      try {
        plugin.dispose();
      } catch (_err) {
        /* unload must continue */
      }
    }
    // Only wipe the shared plugin host; dedicated panes (code/visual/…) keep their DOM.
    if (plugin.pane === "plugin") {
      const host = hostOf(plugin);
      if (host) clearHost(host);
    }
    const panel = document.getElementById("me-props");
    if (panel && wasActive) panel.innerHTML = "";
    if (!keepRegistered) delete plugins[id];
    if (wasActive) {
      document.body.removeAttribute("data-editor-view");
      document.body.setAttribute("data-editor-plugin", "0");
    }
    return true;
  }

  root.ZintriqEditorViews = {
    register: function (plugin) {
      if (!plugin || !plugin.id || !plugin.name || !plugin.pane) return;
      if (!plugin.surfaces || !plugin.surfaces.length) return;
      if (plugins[plugin.id]) unloadPlugin(plugin.id, false);
      plugins[plugin.id] = plugin;
      if (plugin.sandbox) mountSandbox(plugin);
      else bindHost(plugin);
      if (typeof plugin.commands === "object" && plugin.commands && root.ZintriqEngine) {
        Object.keys(plugin.commands).forEach(function (cmd) {
          root.ZintriqEngine.command.register(cmd, plugin.commands[cmd], { plugin: plugin.id }, plugin.id);
        });
      }
    },
    unregister: function (id) {
      return unloadPlugin(id, false);
    },
    unload: function (id) {
      return unloadPlugin(id, true);
    },
    dispose: function () {
      Object.keys(plugins).slice().forEach(function (id) {
        unloadPlugin(id, false);
      });
      documentApi = null;
      if (bootTimer) {
        root.clearTimeout(bootTimer);
        bootTimer = 0;
      }
    },
    list: function (surface) {
      const wanted = surface || surfaceOf();
      return Object.keys(plugins)
        .map(function (id) {
          return plugins[id];
        })
        .filter(function (item) {
          return !wanted || (item.surfaces || []).indexOf(wanted) >= 0;
        });
    },
    get: function (id) {
      return plugins[id] || null;
    },
    activate: function (id) {
      const locked = document.querySelector('button[data-editor-view="' + id + '"]');
      if (locked && locked.hidden) return;
      const plugin = plugins[id];
      const surface = surfaceOf();
      if (!plugin) return;
      if ((plugin.surfaces || []).indexOf(surface) < 0) return;
      const previous = activePlugin();
      if (previous && previous.id !== id) {
        if (typeof previous.deactivate === "function") {
          try {
            previous.deactivate();
          } catch (_err) {
            /* switch must continue */
          }
        }
        if (previous.pane === "plugin" && plugin.pane !== "plugin") {
          clearHost(hostOf(previous));
        }
        destroySandbox(previous.id);
      }
      document.body.setAttribute("data-editor-view", id);
      document.body.setAttribute("data-editor-plugin", plugin.pane === "plugin" ? "1" : "0");
      document.querySelectorAll("[data-editor-view]").forEach(function (node) {
        if (node === document.body) return;
        const on = node.getAttribute("data-editor-view") === id;
        node.classList.toggle("is-current", on);
        if (node.tagName === "BUTTON") node.setAttribute("aria-pressed", on ? "true" : "false");
      });
      rememberPane(id);
      const pluginHost = document.getElementById("me-plugin-host");
      if (pluginHost) pluginHost.hidden = plugin.pane !== "plugin";
      if (plugin.sandbox) mountSandbox(plugin);
      else bindHost(plugin);
      if (typeof plugin.activate === "function") plugin.activate();
      paint(plugin);
    },
    bindDocument: function (api) {
      documentApi = api || null;
      paint(activePlugin());
    },
    sync: function () {
      paint(activePlugin());
    },
  };

  function panePlugin(spec) {
    return Object.assign({}, spec, {
      render: function () {},
      hitTest: function (event) {
        const row = event.target && event.target.closest && event.target.closest("[data-node-id]");
        if (!row) return null;
        return { id: row.getAttribute("data-node-id") };
      },
      edit: function (op) {
        if (op && op.id && root.ZintriqEngine) root.ZintriqEngine.selection.set([op.id]);
      },
      getPropertyPanel: function (ctx) {
        const id = root.ZintriqEngine ? root.ZintriqEngine.selection.primary() : "";
        const visual = ctx && ctx.visual;
        const node = ((visual && visual.nodes) || []).find(function (item) {
          return item.id === id;
        });
        if (!node) return "<p class='me-props-empty'>Select a node</p>";
        const view = (node.properties && node.properties.view) || {};
        const marks = (view.marks || []).join(", ");
        return (
          "<p>" +
          (node.kind || "") +
          " · " +
          (node.id || "") +
          (marks ? " · marks: " + marks : "") +
          "</p>"
        );
      },
    });
  }

  [
    { id: "space", name: "Space", surfaces: ["space"], pane: "space" },
    { id: "code", name: "Code", surfaces: ["describe", "space"], pane: "code" },
    { id: "visual", name: "Visual", surfaces: ["describe", "simulate"], pane: "visual" },
    { id: "graph", name: "Graph", surfaces: ["describe", "simulate", "space"], pane: "graph" },
    { id: "uir", name: "UIR", surfaces: ["describe", "space"], pane: "uir" },
    { id: "simulation", name: "Simulation", surfaces: ["simulate"], pane: "simulation" },
    { id: "page", name: "Page", surfaces: ["describe", "instantiate"], pane: "page" },
    { id: "artifact", name: "Artifact", surfaces: ["instantiate"], pane: "artifact" },
  ].forEach(function (plugin) {
    root.ZintriqEditorViews.register(panePlugin(plugin));
  });

  document.querySelectorAll("button[data-editor-view]").forEach(function (button) {
    button.addEventListener("click", function () {
      root.ZintriqEditorViews.activate(button.getAttribute("data-editor-view"));
    });
  });

  function boot() {
    let initial = document.body.getAttribute("data-editor-view") || "";
    try {
      initial = new URL(root.location.href).searchParams.get("pane") || initial;
    } catch (_err) {
      /* ignore */
    }
    if (initial && plugins[initial]) root.ZintriqEditorViews.activate(initial);
    else {
      const first = document.querySelector("button[data-editor-view].is-current") || document.querySelector("button[data-editor-view]");
      if (first) root.ZintriqEditorViews.activate(first.getAttribute("data-editor-view"));
    }
  }

  function syncUnlocked() {
    if (!root.zintriq || !root.zintriq.http || !root.zintriq.http.get) return;
    root.zintriq.http
      .get("/api/builder-core/meta/views")
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        const ids = {};
        ((data && data.views) || []).forEach(function (row) {
          if (row && row.id) ids[row.id] = true;
        });
        Object.keys(plugins).forEach(function (id) {
          const plugin = plugins[id];
          if (!ids[id]) {
            if (root.ZintriqEngine && root.ZintriqEngine.command && typeof root.ZintriqEngine.command.unregisterOwner === "function") {
              root.ZintriqEngine.command.unregisterOwner(id);
            }
          } else if (plugin && typeof plugin.syncCommands === "function") {
            plugin.syncCommands();
          }
        });
        document.querySelectorAll("button[data-editor-view]").forEach(function (button) {
          const id = button.getAttribute("data-editor-view") || "";
          button.hidden = !ids[id];
        });
        const corePanes = { code: 1, visual: 1, graph: 1, diagram: 1, uir: 1, simulation: 1, page: 1, artifact: 1, space: 1 };
        document.querySelectorAll("[data-editor-pane]").forEach(function (el) {
          const pane = el.getAttribute("data-editor-pane") || "";
          if (pane === "plugin") return;
          if (corePanes[pane]) el.hidden = !ids[pane];
        });
        const inserts = document.querySelector(".me-insert");
        if (inserts) inserts.hidden = !ids.code;
        const tools = document.querySelector(".me-host-tools");
        if (tools) tools.hidden = Object.keys(ids).length === 0;
        const hw = document.getElementById("me-hw");
        if (hw) {
          const surface = document.body.getAttribute("data-meta-view") || "";
          const hardwareOn = !!data.hardware;
          if (root.__zintriqHardwareWas === true && !hardwareOn && surface === "instantiate") {
            const status = document.getElementById("me-status");
            if (status) {
              status.textContent = "Hardware bar hidden — Robotics unloaded";
              status.className = "me-status is-ok";
            }
            const bar = document.getElementById("me-statusbar");
            if (bar) {
              let tip = bar.querySelector(".wb-hw-tip");
              if (!tip) {
                tip = document.createElement("span");
                tip.className = "wb-hw-tip";
                bar.appendChild(tip);
              }
              tip.textContent = "ESP32 hidden";
              let undo = bar.querySelector(".wb-hw-undo");
              if (!undo) {
                undo = document.createElement("button");
                undo.type = "button";
                undo.className = "wb-hw-undo";
                undo.textContent = "Reinstall Robotics";
                undo.addEventListener("click", function () {
                  if (!root.zintriq || !root.zintriq.http) return;
                  undo.disabled = true;
                  root.zintriq.http
                    .post("/api/plugin/install", { id: "official-robotics" })
                    .then(function (res) {
                      return res.json().then(function (body) {
                        return { ok: res.ok, body: body };
                      });
                    })
                    .then(function (result) {
                      if (result.ok) {
                        root.dispatchEvent(new Event("zintriq-plugins-changed"));
                        try {
                          if (root.BroadcastChannel) {
                            if (!root.__zintriqPluginChannel) {
                              root.__zintriqPluginChannel = new BroadcastChannel("zintriq-plugins");
                            }
                            root.__zintriqPluginChannel.postMessage("changed");
                          }
                        } catch (_err) {
                          /* ignore */
                        }
                        if (status) {
                          status.textContent = "Robotics reinstalled — hardware bar back";
                          status.className = "me-status is-ok";
                        }
                        syncUnlocked();
                        root.setTimeout(function () {
                          function paintHwMiss(message) {
                            const goInstantiate = function () {
                              try {
                                sessionStorage.setItem("zintriq-focus-hw", "1");
                              } catch (_err) {
                                /* ignore */
                              }
                              if (
                                root.ZintriqWorkbench &&
                                typeof root.ZintriqWorkbench.switchSurface === "function"
                              ) {
                                root.ZintriqWorkbench.switchSurface("instantiate");
                                return;
                              }
                              const slug =
                                (document.body && document.body.getAttribute("data-draft-slug")) ||
                                (root.ZintriqEngine &&
                                  root.ZintriqEngine.store &&
                                  root.ZintriqEngine.store.get &&
                                  root.ZintriqEngine.store.get().slug) ||
                                "";
                              root.location.href = slug
                                ? "/studio/instantiate/" + encodeURIComponent(slug)
                                : "/studio/instantiate";
                            };
                            const probe = document.getElementById("da-probe");
                            if (probe) {
                              probe.textContent = "";
                              probe.appendChild(document.createTextNode(message + " "));
                              const btn = document.createElement("button");
                              btn.type = "button";
                              btn.className = "da-btn da-btn--tiny";
                              btn.setAttribute("data-hw-open-instantiate", "1");
                              btn.textContent = "Open Instantiate";
                              btn.addEventListener("click", goInstantiate);
                              probe.appendChild(btn);
                            }
                            if (status) {
                              status.textContent = "";
                              status.className = "me-status is-err";
                              status.appendChild(document.createTextNode(message + " "));
                              const btn2 = document.createElement("button");
                              btn2.type = "button";
                              btn2.className = "me-btn";
                              btn2.setAttribute("data-hw-open-instantiate", "1");
                              btn2.textContent = "Open Instantiate";
                              btn2.addEventListener("click", goInstantiate);
                              status.appendChild(btn2);
                            }
                          }
                          const barHw = document.getElementById("me-hw");
                          if (!barHw) {
                            paintHwMiss(
                              "Hardware bar #me-hw missing after Robotics reinstall — open Instantiate"
                            );
                            return;
                          }
                          barHw.hidden = false;
                          if (!barHw.hasAttribute("tabindex")) barHw.setAttribute("tabindex", "-1");
                          if (typeof barHw.scrollIntoView === "function") {
                            barHw.scrollIntoView({ block: "nearest", behavior: "smooth" });
                          }
                          try {
                            barHw.focus({ preventScroll: true });
                          } catch (_focusErr) {
                            try {
                              barHw.focus();
                            } catch (_focusErr2) {
                              paintHwMiss(
                                "Hardware bar #me-hw present but focus failed after Robotics reinstall"
                              );
                            }
                          }
                        }, 80);
                      } else if (status) {
                        status.textContent = (result.body && result.body.error) || "Reinstall failed";
                        status.className = "me-status is-err";
                        undo.disabled = false;
                      }
                    })
                    .catch(function () {
                      undo.disabled = false;
                    });
                });
                bar.appendChild(undo);
              }
              root.setTimeout(function () {
                if (tip && tip.parentNode) tip.remove();
              }, 8000);
            }
          }
          if (hardwareOn) {
            const bar = document.getElementById("me-statusbar");
            if (bar) {
              const undo = bar.querySelector(".wb-hw-undo");
              if (undo) undo.remove();
              const tip = bar.querySelector(".wb-hw-tip");
              if (tip) tip.remove();
            }
          }
          root.__zintriqHardwareWas = hardwareOn;
          hw.hidden = !hardwareOn || surface !== "instantiate";
          if (surface === "instantiate" && hardwareOn && !hw.hidden) {
            let wantFocus = false;
            try {
              wantFocus = sessionStorage.getItem("zintriq-focus-hw") === "1";
              if (wantFocus) sessionStorage.removeItem("zintriq-focus-hw");
            } catch (_focusStore) {
              wantFocus = false;
            }
            if (wantFocus) {
              root.setTimeout(function () {
                function paintFocusFail(message) {
                  const probe = document.getElementById("da-probe");
                  const statusEl = document.getElementById("me-status");
                  if (probe) {
                    probe.textContent = "";
                    probe.appendChild(document.createTextNode(message + " "));
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "da-btn da-btn--tiny";
                    btn.setAttribute("data-hw-open-instantiate", "1");
                    btn.textContent = "Open Instantiate";
                    btn.addEventListener("click", function () {
                      try {
                        sessionStorage.setItem("zintriq-focus-hw", "1");
                      } catch (_e) {
                        /* ignore */
                      }
                      if (root.ZintriqWorkbench && root.ZintriqWorkbench.switchSurface) {
                        root.ZintriqWorkbench.switchSurface("instantiate");
                      }
                    });
                    probe.appendChild(btn);
                  }
                  if (statusEl) {
                    statusEl.textContent = "";
                    statusEl.className = "me-status is-err";
                    statusEl.appendChild(document.createTextNode(message + " "));
                    const btn2 = document.createElement("button");
                    btn2.type = "button";
                    btn2.className = "me-btn";
                    btn2.setAttribute("data-hw-open-instantiate", "1");
                    btn2.textContent = "Open Instantiate";
                    btn2.addEventListener("click", function () {
                      try {
                        sessionStorage.setItem("zintriq-focus-hw", "1");
                      } catch (_e2) {
                        /* ignore */
                      }
                      if (root.ZintriqWorkbench && root.ZintriqWorkbench.switchSurface) {
                        root.ZintriqWorkbench.switchSurface("instantiate");
                      }
                    });
                    statusEl.appendChild(btn2);
                  }
                }
                const barHw = document.getElementById("me-hw");
                if (!barHw || barHw.hidden) {
                  paintFocusFail("Hardware bar #me-hw missing after Open Instantiate");
                  return;
                }
                if (!barHw.hasAttribute("tabindex")) barHw.setAttribute("tabindex", "-1");
                if (typeof barHw.scrollIntoView === "function") {
                  barHw.scrollIntoView({ block: "nearest", behavior: "smooth" });
                }
                try {
                  barHw.focus({ preventScroll: true });
                } catch (_f1) {
                  try {
                    barHw.focus();
                  } catch (_f2) {
                    paintFocusFail("Hardware bar #me-hw present but focus failed after Open Instantiate");
                  }
                }
              }, 60);
            }
          }
        }
        const empty = document.getElementById("me-host-empty");
        const split = document.querySelector(".me-split");
        const hasViews = Object.keys(ids).length > 0;
        if (empty) empty.hidden = hasViews;
        if (split) split.hidden = !hasViews;
        const current = document.body.getAttribute("data-editor-view") || "";
        const active = document.querySelector('button[data-editor-view="' + current + '"]');
        if ((!current || (active && active.hidden)) && root.ZintriqEditorViews && root.ZintriqEditorViews.activate) {
          const first = document.querySelector("button[data-editor-view]:not([hidden])");
          if (first) root.ZintriqEditorViews.activate(first.getAttribute("data-editor-view"));
        }
        if (root.ZintriqWorkbench && root.ZintriqWorkbench.palette && typeof root.ZintriqWorkbench.palette.repaint === "function") {
          root.ZintriqWorkbench.palette.repaint();
        }
      })
      .catch(function () {});
  }

  bootTimer = root.setTimeout(boot, 0);
  syncUnlocked();
  root.addEventListener("zintriq-plugins-changed", syncUnlocked);
  try {
    if (root.BroadcastChannel) {
      if (!root.__zintriqPluginChannel) root.__zintriqPluginChannel = new BroadcastChannel("zintriq-plugins");
      root.__zintriqPluginChannel.addEventListener("message", syncUnlocked);
    }
  } catch (_err) {
    /* ignore */
  }
  root.setInterval(syncUnlocked, 4000);

  root.addEventListener("pagehide", function () {
    root.ZintriqEditorViews.dispose();
    if (root.ZintriqEngine && typeof root.ZintriqEngine.dispose === "function") {
      root.ZintriqEngine.dispose();
    }
  });
})(window);
