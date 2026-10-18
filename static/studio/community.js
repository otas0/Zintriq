(function () {
  const desktop = window.zintriqDesktop;
  const catalogEl = document.getElementById("da-catalog");
  const mineEl = document.getElementById("da-mine");
  const pluginEl = document.getElementById("da-plugins");
  const statusEl = document.getElementById("da-status");
  const searchEl = document.getElementById("da-search");
  const publishBtn = document.getElementById("da-publish");
  const filters = document.querySelectorAll(".da-filter[data-kind]");
  const stampForm = document.getElementById("da-stamp");
  const saveBtn = document.getElementById("da-save-plugin");
  const reloadBtn = document.getElementById("da-reload");
  let kind = "";
  try {
    const params = new URLSearchParams(location.search || "");
    kind = params.get("kind") || sessionStorage.getItem("zintriq-community-kind") || "";
    const qParam = params.get("q");
    if (searchEl && qParam != null && !searchEl.value) searchEl.value = qParam;
    else if (searchEl && !searchEl.value) {
      searchEl.value = sessionStorage.getItem("zintriq-community-q") || "";
    }
  } catch (_err) {
    try {
      kind = sessionStorage.getItem("zintriq-community-kind") || "";
    } catch (_err2) {
      kind = "";
    }
  }

  function communityPushMax() {
    try {
      const raw = localStorage.getItem("zintriq-community-push-max");
      if (raw === "0" || raw === "inf" || raw === "∞") return 0;
      const n = Number(raw);
      if (n === 4 || n === 8) return n;
    } catch (_err) {
      /* ignore */
    }
    return 8;
  }

  function communityPushDepth() {
    try {
      return Math.max(0, Number(sessionStorage.getItem("zintriq-community-push-depth") || 0) || 0);
    } catch (_err) {
      return 0;
    }
  }

  function setCommunityPushDepth(value) {
    try {
      sessionStorage.setItem("zintriq-community-push-depth", String(Math.max(0, value || 0)));
    } catch (_err) {
      /* ignore */
    }
  }

  function syncCommunityUrl(mode) {
    try {
      const params = new URLSearchParams();
      const q = searchEl && searchEl.value ? searchEl.value.trim() : "";
      if (q) params.set("q", q);
      if (kind) params.set("kind", kind);
      const next = "/app/community" + (params.toString() ? "?" + params.toString() : "") + (location.hash || "");
      if (location.pathname + location.search + location.hash !== next) {
        const state = { community: 1, q: q, kind: kind };
        /* Kind filter = navigation (push); search typing / share = replace. Cap push depth. */
        if (mode === "push") {
          const max = communityPushMax();
          const depth = communityPushDepth();
          if (max > 0 && depth >= max) history.replaceState(state, "", next);
          else {
            history.pushState(state, "", next);
            setCommunityPushDepth(depth + 1);
          }
        } else {
          history.replaceState(state, "", next);
        }
      }
      sessionStorage.setItem("zintriq-community-kind", kind);
      sessionStorage.setItem("zintriq-community-q", q);
    } catch (_err) {
      /* ignore */
    }
  }

  function applyCommunityUrlState() {
    try {
      const params = new URLSearchParams(location.search || "");
      kind = params.get("kind") || "";
      if (searchEl) searchEl.value = params.get("q") || "";
      applyKindFilter();
      loadCatalog().then(applyPackFocus);
    } catch (_err) {
      /* ignore */
    }
  }

  function http() {
    return window.zintriq && window.zintriq.http;
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  async function requireAccountToPublish() {
    const user = desktop && desktop.getUser ? await desktop.getUser() : null;
    if (!user) {
      setStatus("Sign in to publish to your account");
      if (desktop && desktop.login) await desktop.login();
      return false;
    }
    if (!(await paintPublishGate())) {
      setStatus("Cloud subscription required for Publish & sync. Local export stays free.");
      return false;
    }
    return true;
  }

  async function paintPublishGate() {
    if (!publishBtn) return true;
    if (!desktop || !desktop.cloudEntitlement) {
      publishBtn.disabled = false;
      publishBtn.removeAttribute("title");
      return true;
    }
    const ent = await desktop.cloudEntitlement();
    const data = (ent && ent.data) || {};
    const allowed = !(data.billing_enabled && !data.publish);
    publishBtn.disabled = !allowed;
    if (allowed) {
      publishBtn.removeAttribute("title");
      publishBtn.removeAttribute("aria-disabled");
    } else {
      publishBtn.setAttribute(
        "title",
        "Cloud subscription required for Publish & sync. Local export stays free."
      );
      publishBtn.setAttribute("aria-disabled", "true");
    }
    return allowed;
  }

  function pluginChannel() {
    try {
      if (!window.BroadcastChannel) return null;
      if (!window.__zintriqPluginChannel) window.__zintriqPluginChannel = new BroadcastChannel("zintriq-plugins");
      return window.__zintriqPluginChannel;
    } catch (_err) {
      return null;
    }
  }

  function notifyPluginsChanged() {
    window.dispatchEvent(new Event("zintriq-plugins-changed"));
    const bus = pluginChannel();
    if (bus) bus.postMessage("changed");
  }

  function goHomeAfterInstall(data, item) {
    const params = new URLSearchParams();
    let slug = "";
    try {
      slug = sessionStorage.getItem("zintriq-draft-slug") || "";
    } catch (_err) {
      slug = "";
    }
    if (!slug && data && data.draft) slug = data.draft;
    const pane = (data && data.pane) || (item && item.view) || "";
    if (slug) params.set("draft", slug);
    if (pane && pane !== "code") params.set("pane", pane);
    const q = params.toString();
    window.location.href = "/studio" + (q ? "?" + q : "");
  }

  function csrfToken() {
    const node = document.querySelector('meta[name="csrf-token"]');
    return node ? node.getAttribute("content") || "" : "";
  }

  function row(item, mine) {
    const li = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = item.name || item.title || item.slug || item.id;
    const meta = document.createElement("span");
    meta.textContent = [item.kind || "", item.author || item.publisher || ""].filter(Boolean).join(" · ");
    li.appendChild(title);
    li.appendChild(meta);
    const open = document.createElement("button");
    open.type = "button";
    open.className = "da-btn da-btn--tiny";
    open.textContent = "Open";
    open.addEventListener("click", async function () {
      if (!desktop || !desktop.openShare) return;
      setStatus("Opening…");
      await desktop.openShare(item.id, "describe");
    });
    li.appendChild(open);
    if (mine && item.url) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "da-btn da-btn--tiny";
      copy.textContent = "Copy /c/ link";
      copy.addEventListener("click", async function () {
        const cfg = desktop.getConfig ? await desktop.getConfig() : {};
        const origin = String((cfg && cfg.accountOrigin) || "").replace(/\/$/, "");
        const href = origin && item.url.startsWith("/") ? origin + item.url : item.url;
        try {
          await navigator.clipboard.writeText(href);
          setStatus("Copied " + href);
        } catch {
          setStatus(href);
        }
      });
      li.appendChild(copy);
      const drop = document.createElement("button");
      drop.type = "button";
      drop.className = "da-btn da-btn--tiny";
      drop.textContent = "Unpublish";
      drop.addEventListener("click", async function () {
        if (!desktop.unpublish) return;
        setStatus("Unpublishing…");
        const result = await desktop.unpublish(item.id);
        if (result && result.ok) {
          setStatus("Unpublished " + item.id);
          await loadMine();
          await loadCatalog();
        } else {
          setStatus((result && (result.error || (result.data && result.data.error))) || "Unpublish failed");
        }
      });
      li.appendChild(drop);
    }
    return li;
  }

  function addInstallButton(li, item) {
    const install = document.createElement("button");
    install.type = "button";
    install.className = "da-btn da-btn--tiny";
    install.textContent = "Install";
    install.addEventListener("click", async function () {
      setStatus("Installing…");
      let result;
      if (item.origin === "account" && desktop && desktop.installSharePlugin) {
        result = await desktop.installSharePlugin(item.id, csrfToken());
      } else if (desktop && desktop.installPlugin) {
        result = await desktop.installPlugin(item.id, csrfToken());
      } else if (http()) {
        const res = await http().post("/api/plugin/install", { id: item.id, manifest: item.manifest || undefined });
        const data = await res.json().catch(function () {
          return {};
        });
        result = { ok: res.ok, data: data, error: data.error };
      }
      if (result && result.ok) {
        setStatus("Installed " + ((result.data && result.data.slug) || item.id));
        notifyPluginsChanged();
        goHomeAfterInstall(result.data, item);
        return;
      } else {
        setStatus((result && result.error) || "Install failed");
      }
    });
    li.appendChild(install);
  }

  function pluginRow(item) {
    const li = document.createElement("li");
    if (item.id) li.setAttribute("data-pack-id", item.id);
    if (item.installed) li.classList.add("is-installed");
    const title = document.createElement("strong");
    title.textContent = item.name || item.id;
    const meta = document.createElement("span");
    meta.textContent = [
      item.form || "view",
      item.installed ? "installed" : "not installed",
      item.draft_slug ? "draft " + item.draft_slug : "no draft",
      item.draft_updated_at || "",
      item.origin || "",
    ]
      .filter(Boolean)
      .join(" · ");
    li.appendChild(title);
    li.appendChild(meta);
    if (item.status === "approved" || item.kind === "plugin") {
      if (item.installed) {
        const disable = document.createElement("button");
        disable.type = "button";
        disable.className = "da-btn da-btn--tiny";
        disable.textContent = "Disable";
        disable.addEventListener("click", async function () {
          setStatus("Disabling…");
          let result;
          if (desktop && desktop.disablePlugin) {
            result = await desktop.disablePlugin(item.id, csrfToken());
          } else if (http()) {
            const res = await http().post("/api/plugin/disable", { id: item.id });
            const data = await res.json().catch(function () {
              return {};
            });
            result = { ok: res.ok, data: data, error: data.error };
          }
          if (result && result.ok) {
            setStatus("Disabled " + item.id);
            notifyPluginsChanged();
            await loadPlugins();
          } else {
            setStatus((result && result.error) || "Disable failed");
          }
        });
        li.appendChild(disable);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "da-btn da-btn--tiny";
        remove.textContent = "Remove";
        remove.addEventListener("click", async function () {
          const bound = item.draft_slug || "(none)";
          const dropDraft = window.confirm(
            "Remove plugin " +
              item.id +
              ".\nBound draft: " +
              bound +
              "\nOK = also delete that draft\nCancel = remove plugin only, keep draft"
          );
          setStatus("Removing…");
          let result;
          if (desktop && desktop.removePlugin) {
            result = await desktop.removePlugin(item.id, csrfToken(), dropDraft);
          } else if (http()) {
            const res = await http().post("/api/plugin/remove", { id: item.id, delete_draft: dropDraft });
            const data = await res.json().catch(function () {
              return {};
            });
            result = { ok: res.ok, data: data, error: data.error };
          }
          if (result && result.ok) {
            const cleared =
              (result.data && result.data.binding_cleared) ||
              (dropDraft && item.draft_slug ? item.draft_slug : "");
            try {
              const last = JSON.parse(sessionStorage.getItem("zintriq-rebind-last") || "{}");
              if (last && last.id === item.id) sessionStorage.removeItem("zintriq-rebind-last");
            } catch (_err) {
              /* ignore */
            }
            item.draft_slug = "";
            setStatus(
              "Removed " +
                item.id +
                (dropDraft && cleared ? " and draft " + cleared : "") +
                (cleared && !dropDraft ? " · cleared bind " + cleared : "")
            );
            if (cleared) {
              if (!window.__zintriqWindowId) {
                window.__zintriqWindowId = "w" + String(Date.now()) + Math.random().toString(16).slice(2);
              }
              const detail = { id: item.id, slug: cleared, __from: window.__zintriqWindowId };
              try {
                window.dispatchEvent(new CustomEvent("zintriq-binding-cleared", { detail: detail }));
              } catch (_evErr) {
                /* ignore */
              }
              try {
                if (window.BroadcastChannel) {
                  if (!window.__zintriqBindingChannel) {
                    window.__zintriqBindingChannel = new BroadcastChannel("zintriq-binding");
                  }
                  window.__zintriqBindingChannel.postMessage(detail);
                }
              } catch (_bus) {
                /* ignore */
              }
              if (window.ZintriqWorkbench && typeof window.ZintriqWorkbench.refreshRebinds === "function") {
                window.ZintriqWorkbench.refreshRebinds({ clearedId: item.id, clearedSlug: cleared });
              }
            }
            notifyPluginsChanged();
            await loadPlugins();
          } else {
            setStatus((result && result.error) || "Remove failed");
          }
        });
        li.appendChild(remove);
        if (item.stamp || item.origin === "third") {
          addInstallButton(li, item);
        }
      } else {
        addInstallButton(li, item);
      }
      if (item.status === "approved") {
        const use = document.createElement("button");
        use.type = "button";
        use.className = "da-btn da-btn--tiny";
        use.textContent = "Use";
        use.addEventListener("click", async function () {
          if (!item.installed) {
            setStatus("Install this plugin first");
            return;
          }
          const pane = item.view || "";
          const bound = item.draft_slug || "";
          let openNew = !bound;
          if (bound) {
            openNew = !window.confirm(
              "This plugin is bound to draft " +
                bound +
                ".\nOK = open that draft\nCancel = New with this plugin skeleton"
            );
          }
          if (openNew && http()) {
            setStatus("Opening New with " + (item.name || item.id));
            const res = await http().post("/api/plugin/use", { id: item.id, rebind: true });
            const data = await res.json().catch(function () {
              return {};
            });
            if (!res.ok) {
              setStatus(data.error || "Use failed");
              return;
            }
            if (data.slug) {
              try {
                sessionStorage.setItem("zintriq-draft-slug", data.slug);
              } catch (_err) {
                /* ignore */
              }
              item.draft_slug = data.slug;
            }
            const fromSlug = data.from || bound || "";
            const toSlug = data.to || data.slug || "";
            setStatus(
              (fromSlug ? fromSlug + " → " : "bound → ") +
                toSlug +
                (data.rebound ? " · rebound" : "")
            );
            try {
              sessionStorage.setItem(
                "zintriq-rebind-last",
                JSON.stringify({ id: item.id, from: fromSlug, to: toSlug })
              );
            } catch (_storeErr) {
              /* ignore */
            }
            window.location.href = data.studio || "/studio/meta/" + encodeURIComponent(data.slug || "");
            return;
          }
          const slug = bound;
          const dest = slug
            ? "/studio/meta/" + encodeURIComponent(slug) + (pane ? "?pane=" + encodeURIComponent(pane) : "")
            : "/studio/meta" + (pane ? "?pane=" + encodeURIComponent(pane) : "");
          setStatus("Opening " + (item.name || item.id));
          window.location.href = dest;
        });
        li.appendChild(use);
      }
      if (item.origin !== "account" && desktop && desktop.publishPlugin) {
        const pub = document.createElement("button");
        pub.type = "button";
        pub.className = "da-btn da-btn--tiny";
        pub.textContent = "Publish";
        pub.addEventListener("click", async function () {
          if (!(await requireAccountToPublish())) return;
          setStatus("Publishing…");
          const result = await desktop.publishPlugin(item);
          if (result && result.ok) {
            setStatus("Published " + ((result.data && result.data.url) || item.id));
            await loadPlugins();
          } else {
            setStatus((result && result.error) || "Sign in to publish to your account");
          }
        });
        li.appendChild(pub);
      }
    }
    return li;
  }

  function fill(node, items, empty, mine) {
    if (!node) return;
    node.innerHTML = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "da-empty";
      li.textContent = empty;
      node.appendChild(li);
      return;
    }
    items.forEach(function (item) {
      node.appendChild(row(item, mine));
    });
  }

  function packHash() {
    return String(location.hash || "").replace(/^#/, "");
  }

  function applyPackFocus() {
    const hash = packHash();
    document.querySelectorAll(".is-pack-focus").forEach(function (node) {
      node.classList.remove("is-pack-focus");
    });
    if (!hash) return;
    const target =
      hash === "da-installed-packs"
        ? document.getElementById("da-installed-packs")
        : document.querySelector('[data-pack-id="' + hash.replace(/"/g, "") + '"]');
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ block: "nearest" });
      target.classList.add("is-pack-focus");
      if (target.getAttribute("data-pack-id")) target.classList.add("is-installed");
    }
  }

  function fillPlugins(items) {
    if (!pluginEl) return;
    const keep = packHash();
    pluginEl.innerHTML = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "da-empty";
      li.textContent = "No plugins yet. Save as plugin, or install an official pack.";
      pluginEl.appendChild(li);
      if (keep && location.hash !== "#" + keep) location.hash = keep;
      applyPackFocus();
      return;
    }
    items.forEach(function (item) {
      pluginEl.appendChild(pluginRow(item));
    });
    if (keep && location.hash !== "#" + keep) location.hash = keep;
    applyPackFocus();
  }

  async function loadPlugins() {
    if (!pluginEl) return;
    let data = null;
    if (desktop && desktop.listPlugins) {
      data = await desktop.listPlugins();
    } else if (http()) {
      const res = await http().get("/api/plugin");
      data = await res.json().catch(function () {
        return {};
      });
    }
    fillPlugins((data && data.packs) || []);
    const user = desktop && desktop.getUser ? await desktop.getUser() : null;
    if (user && desktop && desktop.listCatalog) {
      const remote = await desktop.listCatalog({ type: "plugin" });
      const extra = ((remote && (remote.packages || remote.descriptions)) || []).map(function (row) {
        return {
          id: row.id,
          name: row.name,
          form: row.form || "plugin",
          origin: "account",
          status: "approved",
          kind: "plugin",
        };
      });
      if (extra.length) {
        const local = (data && data.packs) || [];
        const seen = {};
        local.concat(extra).forEach(function (row) {
          seen[row.id] = row;
        });
        fillPlugins(Object.keys(seen).map(function (key) { return seen[key]; }));
      }
    }
  }

  async function loadCatalog() {
    if (!catalogEl) return;
    if (!desktop || !desktop.listCatalog) {
      fill(catalogEl, [], "Published descriptions need the Studio app.", false);
      return;
    }
    const data = await desktop.listCatalog({
      q: searchEl && searchEl.value ? searchEl.value.trim() : "",
      type: kind,
    });
    const items = (data && (data.descriptions || data.packages)) || [];
    fill(catalogEl, items, "No published descriptions yet.", false);
  }

  async function loadMine() {
    if (!mineEl) return;
    if (!desktop || !desktop.listMine) {
      fill(mineEl, [], "Sign in to list what you published.", true);
      return;
    }
    const data = await desktop.listMine();
    if (!data || data.error === "not signed in" || data.status === 401) {
      fill(mineEl, [], "Sign in to publish descriptions from this machine.", true);
      return;
    }
    const items = (data && data.shares) || [];
    fill(mineEl, items, "You have not published a description yet.", true);
  }

  function applyKindFilter() {
    filters.forEach(function (item) {
      const on = (item.getAttribute("data-kind") || "") === kind;
      item.classList.toggle("is-current", on);
      item.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  applyKindFilter();

  filters.forEach(function (button) {
    button.addEventListener("click", function () {
      const keep = packHash();
      kind = button.getAttribute("data-kind") || "";
      applyKindFilter();
      syncCommunityUrl("push");
      loadCatalog().then(function () {
        if (keep && location.hash !== "#" + keep) location.hash = keep;
        applyPackFocus();
      });
    });
  });

  if (reloadBtn) {
    reloadBtn.addEventListener("click", async function () {
      const keep = packHash();
      try {
        const params = new URLSearchParams(location.search || "");
        kind = params.get("kind") || sessionStorage.getItem("zintriq-community-kind") || kind;
        const savedQ = params.get("q");
        if (searchEl) {
          searchEl.value =
            savedQ != null ? savedQ : sessionStorage.getItem("zintriq-community-q") || searchEl.value || "";
        }
      } catch (_err) {
        /* ignore */
      }
      applyKindFilter();
      syncCommunityUrl("replace");
      setStatus("Reloading…");
      await Promise.all([loadCatalog(), loadMine(), loadPlugins()]);
      if (keep && location.hash !== "#" + keep) location.hash = keep;
      applyPackFocus();
      const q = searchEl && searchEl.value ? searchEl.value.trim() : "";
      setStatus("Reloaded" + (kind ? " · kind " + kind : "") + (q ? " · q " + q : ""));
    });
  }
  if (searchEl) {
    let timer;
    searchEl.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        const keep = packHash();
        syncCommunityUrl("replace");
        loadCatalog().then(function () {
          if (keep && location.hash !== "#" + keep) location.hash = keep;
          applyPackFocus();
        });
      }, 200);
    });
  }
  syncCommunityUrl("replace");

  window.addEventListener("hashchange", applyPackFocus);
  window.addEventListener("popstate", function () {
    setCommunityPushDepth(Math.max(0, communityPushDepth() - 1));
    applyCommunityUrlState();
  });

  if (publishBtn) {
    publishBtn.addEventListener("click", async function () {
      if (!desktop || !desktop.publish) {
        setStatus("Publish from File → Publish… in Studio.");
        return;
      }
      if (!(await requireAccountToPublish())) return;
      publishBtn.disabled = true;
      setStatus("Publishing…");
      try {
        const result = await desktop.publish();
        if (result && result.ok) {
          setStatus("Published " + ((result.data && result.data.url) || ""));
          await loadMine();
          await loadCatalog();
        } else {
          setStatus((result && result.error) || "Publish failed. Log in and save a description first.");
        }
      } catch (err) {
        setStatus(err && err.message ? err.message : "Publish failed");
      } finally {
        await paintPublishGate();
      }
    });
  }

  async function refreshStampTarget() {
    const idEl = document.getElementById("da-stamp-id");
    const nameEl = document.getElementById("da-stamp-name");
    if (!idEl || !nameEl || !http()) return;
    const name = (nameEl.value || "").trim();
    if (!name) {
      idEl.textContent = "Will save as community-…";
      return;
    }
    const res = await http().get("/api/plugin/stamp-target?name=" + encodeURIComponent(name));
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || !data.id) {
      idEl.textContent = "Will save as community-…";
      return;
    }
    idEl.textContent = data.overwrite
      ? "Will overwrite " + data.id
      : "Will save as " + data.id;
  }

  async function prefillStampName() {
    const nameEl = document.getElementById("da-stamp-name");
    if (!nameEl || nameEl.value) return;
    let slug = "";
    try {
      slug = sessionStorage.getItem("zintriq-draft-slug") || "";
    } catch (_err) {
      slug = "";
    }
    if (!slug && http()) {
      const res = await http().get("/api/builder-core/meta/drafts");
      const data = await res.json().catch(function () {
        return {};
      });
      slug = (data && data.current) || "";
    }
    if (slug) nameEl.value = slug;
  }

  if (saveBtn && stampForm) {
    saveBtn.addEventListener("click", async function () {
      stampForm.hidden = !stampForm.hidden;
      if (!stampForm.hidden) {
        await prefillStampName();
        refreshStampTarget();
      }
    });
  }
  const stampNameEl = document.getElementById("da-stamp-name");
  if (stampNameEl) {
    let stampTimer;
    stampNameEl.addEventListener("input", function () {
      clearTimeout(stampTimer);
      stampTimer = setTimeout(refreshStampTarget, 150);
    });
  }
  document.querySelectorAll("#da-stamp-chips [data-form]").forEach(function (button) {
    button.addEventListener("click", function () {
      const input = document.getElementById("da-stamp-form");
      if (input) input.value = button.getAttribute("data-form") || "";
    });
  });
  if (stampForm) {
    stampForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const name = (document.getElementById("da-stamp-name") || {}).value || "";
      const form = (document.getElementById("da-stamp-form") || {}).value || "";
      if (!http()) {
        setStatus("Save as plugin needs Studio.");
        return;
      }
      setStatus("Saving plugin…");
      const res = await http().post("/api/plugin/stamp", { name: name, form: form });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        setStatus(data.error || "Save failed");
        return;
      }
      const ident = (data.pack && data.pack.id) || name;
      setStatus((data.replaced ? "Updated " : "Saved ") + ident + ". Install to use this copy.");
      stampForm.hidden = true;
      await loadPlugins();
    });
  }

  loadCatalog();
  loadMine();
  loadPlugins();
  applyPackFocus();
  paintPublishGate();

  const pending = document.body.getAttribute("data-open-share") || "";
  if (pending && desktop && desktop.openShare) {
    desktop.openShare(pending);
  }
})();
