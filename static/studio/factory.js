(function () {
  function postJson(url, body) {
    return window.zintriq.http.post(url, body);
  }

  function fillPackId() {
    return document.body.getAttribute("data-fill-pack") || "";
  }

  function fillPackLabel() {
    return document.body.getAttribute("data-fill-label") || "Fill";
  }

  function fillPackPane() {
    return document.body.getAttribute("data-fill-pane") || "";
  }

  async function loadTakenSlugSet(exceptSlug) {
    const taken = new Set();
    if (!(window.zintriq && window.zintriq.http && window.zintriq.http.get)) return taken;
    try {
      const res = await window.zintriq.http.get("/api/builder-core/meta/index");
      const data = await res.json().catch(function () {
        return {};
      });
      (data.drafts || []).forEach(function (row) {
        if (row && row.slug) taken.add(String(row.slug));
      });
      (data.artifacts || []).forEach(function (row) {
        if (row && row.slug) taken.add(String(row.slug));
      });
    } catch (_err) {
      /* ignore */
    }
    if (exceptSlug) taken.delete(String(exceptSlug));
    return taken;
  }

  function pickRenameSlot(slug, data) {
    return new Promise(function (resolve) {
      closeDraftMenu();
      const existing = document.getElementById("da-rename-slots");
      if (existing) existing.remove();
      const panel = document.createElement("div");
      panel.id = "da-rename-slots";
      panel.className = "da-draft-menu da-rename-slots";
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-label", "Rename conflict");
      const chain = Array.isArray(data.conflict_chain) ? data.conflict_chain.filter(Boolean) : [];
      const slots = Array.isArray(data.free_slots) && data.free_slots.length
        ? data.free_slots.filter(Boolean)
        : data.suggestion
          ? [data.suggestion]
          : [];
      const lead = document.createElement("p");
      lead.className = "da-rename-slots__lead";
      lead.textContent = chain.length
        ? "Occupied: " + chain.join(" → ") + ". Pick a free name:"
        : "Slug taken. Pick a free name:";
      panel.appendChild(lead);
      function finish(choice) {
        panel.remove();
        resolve(choice || "");
      }
      slots.forEach(function (slot) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = "Rename to " + slot;
        btn.setAttribute("data-rename-slot", slot);
        btn.addEventListener("click", function () {
          finish(slot);
        });
        panel.appendChild(btn);
      });
      const customRow = document.createElement("div");
      customRow.className = "da-rename-slots__custom";
      const customInput = document.createElement("input");
      customInput.type = "text";
      customInput.setAttribute("data-rename-custom", "1");
      customInput.placeholder = "Other name…";
      customInput.setAttribute("aria-label", "Other name");
      const customHint = document.createElement("span");
      customHint.className = "da-rename-slots__hint";
      customHint.setAttribute("data-rename-occupied", "0");
      customHint.hidden = true;
      customHint.textContent = "Occupied";
      const customBtn = document.createElement("button");
      customBtn.type = "button";
      customBtn.textContent = "Use";
      let takenSet = new Set(chain);
      function paintCustomState() {
        const value = String(customInput.value || "").trim();
        const occupied = !!(value && takenSet.has(value));
        customBtn.disabled = !value || occupied;
        customInput.classList.toggle("is-occupied", occupied);
        customHint.hidden = !occupied;
        customHint.setAttribute("data-rename-occupied", occupied ? "1" : "0");
      }
      customBtn.addEventListener("click", function () {
        const value = String(customInput.value || "").trim();
        if (!value || takenSet.has(value)) {
          customInput.focus();
          paintCustomState();
          return;
        }
        finish(value);
      });
      customInput.addEventListener("input", paintCustomState);
      customInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          customBtn.click();
        }
      });
      customRow.appendChild(customInput);
      customRow.appendChild(customBtn);
      panel.appendChild(customRow);
      panel.appendChild(customHint);
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.textContent = "Cancel";
      cancel.addEventListener("click", function () {
        finish("");
      });
      panel.appendChild(cancel);
      document.body.appendChild(panel);
      paintCustomState();
      loadTakenSlugSet(slug).then(function (set) {
        takenSet = set;
        chain.forEach(function (name) {
          takenSet.add(name);
        });
        paintCustomState();
      });
      try {
        customInput.focus();
      } catch (_err) {
        /* ignore */
      }
    });
  }

  async function renameDraftSlug(slug, next) {
    let res = await postJson("/api/builder-core/meta/drafts/rename", { slug: slug, to: next });
    let data = await res.json().catch(function () {
      return {};
    });
    if (res.status === 409 && (data.suggestion || (data.free_slots && data.free_slots.length))) {
      const picked = await pickRenameSlot(slug, data);
      if (!picked) return false;
      res = await postJson("/api/builder-core/meta/drafts/rename", { slug: slug, to: picked });
      data = await res.json().catch(function () {
        return {};
      });
    }
    if (!res.ok) {
      const chain = Array.isArray(data.conflict_chain) ? data.conflict_chain.filter(Boolean) : [];
      window.alert(
        (data.error || "Rename failed") +
          (data.suggestion ? " — try " + data.suggestion : "") +
          (chain.length ? " (occupied " + chain.join(", ") + ")" : "")
      );
      return false;
    }
    return true;
  }

  function paintFillInstallFail(slug, packId, err) {
    const probe = document.getElementById("da-probe");
    if (!probe) {
      window.alert((err || "Install failed") + " · draft " + slug + " kept");
      return;
    }
    probe.textContent = "";
    const lead = document.createElement("span");
    lead.textContent = (err || "Install failed") + " · pack " + packId + " · ";
    probe.appendChild(lead);
    const draftLink = document.createElement("a");
    draftLink.href = "/studio/meta/" + encodeURIComponent(slug);
    draftLink.className = "da-probe-draft";
    draftLink.setAttribute("data-fill-draft-link", slug);
    draftLink.textContent = "Open draft " + slug;
    probe.appendChild(draftLink);
    probe.appendChild(document.createTextNode(" kept "));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "da-btn da-btn--tiny";
    retry.setAttribute("data-fill-retry", packId);
    retry.setAttribute("data-fill-retry-slug", slug);
    retry.textContent = "Retry install & Fill";
    retry.addEventListener("click", async function () {
      retry.disabled = true;
      await installPackThenFill(slug, packId);
    });
    probe.appendChild(retry);
    probe.appendChild(document.createTextNode(" "));
    const again = document.createElement("button");
    again.type = "button";
    again.className = "da-btn da-btn--tiny";
    again.textContent = "Pick pack";
    again.addEventListener("click", function () {
      offerFillInstall(slug, {
        hint: "Install a view pack, then Fill. Draft " + slug + " is unchanged.",
        community: "/app/community",
        suggest_pack: packId,
      });
    });
    probe.appendChild(again);
  }

  async function installPackThenFill(slug, packId) {
    const probe = document.getElementById("da-probe");
    if (probe) probe.textContent = "Installing " + packId + " for " + slug + "…";
    const res = await postJson("/api/plugin/install", { id: packId });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      paintFillInstallFail(slug, packId, (data && data.error) || "Install failed");
      return;
    }
    notifyPluginsChanged();
    if (document.body) {
      document.body.setAttribute("data-fill-pack", packId);
      const pane = (data && data.pane) || (packId === "official-scene" ? "scene" : "ui");
      document.body.setAttribute("data-fill-pane", pane);
      document.body.setAttribute("data-fill-label", "Fill from " + (pane === "scene" ? "Scene" : "UI"));
    }
    await fillDraftSlug(slug);
  }

  function offerFillInstall(slug, data) {
    closeDraftMenu();
    const existing = document.getElementById("da-fill-install");
    if (existing) existing.remove();
    const panel = document.createElement("div");
    panel.id = "da-fill-install";
    panel.className = "da-draft-menu da-fill-install";
    panel.setAttribute("role", "dialog");
    const lead = document.createElement("p");
    lead.className = "da-rename-slots__lead";
    lead.textContent = data.hint || data.error || "Install a view pack, then Fill.";
    panel.appendChild(lead);
    [
      { id: "official-ui", label: "Install UI & Fill" },
      { id: "official-scene", label: "Install Scene & Fill" },
    ].forEach(function (row) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = row.label;
      btn.setAttribute("data-fill-install", row.id);
      btn.addEventListener("click", async function () {
        panel.remove();
        await installPackThenFill(slug, row.id);
      });
      panel.appendChild(btn);
    });
    if (data.community) {
      const community = document.createElement("button");
      community.type = "button";
      community.textContent = "Open Community";
      community.addEventListener("click", function () {
        panel.remove();
        const hash = data.suggest_pack ? "#" + encodeURIComponent(data.suggest_pack) : "";
        window.location.href = data.community + hash;
      });
      panel.appendChild(community);
    }
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", function () {
      panel.remove();
    });
    panel.appendChild(cancel);
    document.body.appendChild(panel);
  }

  async function fillDraftSlug(slug) {
    const pack = fillPackId();
    const res = await postJson("/api/builder-core/meta/drafts/fill", { slug: slug, id: pack || "auto" });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      if (data.community || /install a view pack/i.test(data.error || "")) {
        offerFillInstall(slug, data);
      } else {
        window.alert(data.hint || data.error || "Fill failed");
      }
      return;
    }
    const pane = data.pane || fillPackPane() || "";
    window.location.href =
      "/studio/meta/" +
      encodeURIComponent(data.slug || slug) +
      (pane && pane !== "code" ? "?pane=" + encodeURIComponent(pane) : "");
  }

  function notifyBindingCleared(packId, clearedSlug) {
    if (!window.__zintriqWindowId) {
      window.__zintriqWindowId = "w" + String(Date.now()) + Math.random().toString(16).slice(2);
    }
    const detail = { id: packId || "", slug: clearedSlug || "", __from: window.__zintriqWindowId };
    try {
      window.dispatchEvent(new CustomEvent("zintriq-binding-cleared", { detail: detail }));
    } catch (_err) {
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
      window.ZintriqWorkbench.refreshRebinds({ clearedId: packId, clearedSlug: clearedSlug });
    }
  }

  async function removeDraftSlug(slug) {
    if (!window.confirm("Remove draft " + slug + "?")) return;
    const res = await postJson("/api/builder-core/meta/drafts/remove", { slug: slug });
    if (res.ok) window.location.reload();
  }

  function bindDraftButtons(root) {
    (root || document).querySelectorAll("[data-remove-draft]").forEach(function (button) {
      if (button.getAttribute("data-bound") === "1") return;
      button.setAttribute("data-bound", "1");
      button.addEventListener("click", async function () {
        const slug = button.getAttribute("data-remove-draft") || "";
        if (!slug) return;
        await removeDraftSlug(slug);
      });
    });
    (root || document).querySelectorAll("[data-rename-draft]").forEach(function (button) {
      if (button.getAttribute("data-bound") === "1") return;
      button.setAttribute("data-bound", "1");
      button.addEventListener("click", async function () {
        const slug = button.getAttribute("data-rename-draft") || "";
        if (!slug) return;
        const next = window.prompt("Rename draft", slug);
        if (!next || next === slug) return;
        if (await renameDraftSlug(slug, next)) window.location.reload();
      });
    });
    (root || document).querySelectorAll("[data-fill-draft]").forEach(function (button) {
      if (button.getAttribute("data-bound") === "1") return;
      button.setAttribute("data-bound", "1");
      button.addEventListener("click", async function () {
        const slug = button.getAttribute("data-fill-draft") || "";
        if (!slug) return;
        await fillDraftSlug(slug);
      });
    });
  }
  bindDraftButtons(document);

  function closeDraftMenu() {
    const menu = document.getElementById("da-draft-menu");
    if (menu) menu.remove();
    document.querySelectorAll(".da-list li.is-menu-open, .da-list li.is-hold").forEach(function (row) {
      row.classList.remove("is-menu-open");
      row.classList.remove("is-hold");
    });
  }

  function openDraftMenu(li, clientX, clientY) {
    closeDraftMenu();
    document.querySelectorAll(".da-list li.is-menu-open").forEach(function (row) {
      row.classList.remove("is-menu-open");
    });
    if (li) li.classList.add("is-menu-open");
    const slug = li.getAttribute("data-draft-row") || "";
    if (!slug) return;
    const menu = document.createElement("div");
    menu.id = "da-draft-menu";
    menu.className = "da-draft-menu";
    menu.setAttribute("role", "menu");
    menu.style.left = Math.max(0, Number(clientX) || 0) + "px";
    menu.style.top = Math.max(0, Number(clientY) || 0) + "px";
    const actions = [
      { label: fillPackLabel(), run: function () { return fillDraftSlug(slug); } },
      {
        label: "Rename",
        run: async function () {
          const next = window.prompt("Rename draft", slug);
          if (!next || next === slug) return;
          if (await renameDraftSlug(slug, next)) window.location.reload();
        },
      },
      { label: "Remove", run: function () { return removeDraftSlug(slug); } },
    ];
    actions.forEach(function (action) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "menuitem");
      btn.textContent = action.label;
      btn.addEventListener("click", async function () {
        closeDraftMenu();
        await action.run();
      });
      menu.appendChild(btn);
    });
    document.body.appendChild(menu);
  }

  function bindDraftContextMenu(root) {
    (root || document).querySelectorAll("[data-draft-row][data-draft-empty='1']").forEach(function (li) {
      if (li.getAttribute("data-menu-bound") === "1") return;
      li.setAttribute("data-menu-bound", "1");
      li.addEventListener("contextmenu", function (event) {
        event.preventDefault();
        openDraftMenu(li, event.clientX, event.clientY);
      });
      /* Trackpad two-finger click fires contextmenu; long-press covers touch / Force Touch gaps. */
      let holdTimer = 0;
      let holdX = 0;
      let holdY = 0;
      li.addEventListener("pointerdown", function (event) {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        holdX = event.clientX;
        holdY = event.clientY;
        clearTimeout(holdTimer);
        li.classList.add("is-hold");
        /* Touch opens sooner; mouse/trackpad needs a longer hold. Settings can override. */
        let touchMs = 400;
        let mouseMs = 650;
        try {
          const t = Number(localStorage.getItem("zintriq-hold-touch-ms"));
          const m = Number(localStorage.getItem("zintriq-hold-mouse-ms"));
          if (t >= 200 && t <= 1200) touchMs = t;
          if (m >= 300 && m <= 1500) mouseMs = m;
        } catch (_holdPref) {
          /* ignore */
        }
        const holdMs =
          event.pointerType === "touch" ? touchMs : event.pointerType === "pen" ? Math.min(touchMs + 50, mouseMs) : mouseMs;
        holdTimer = window.setTimeout(function () {
          holdTimer = 0;
          li.classList.remove("is-hold");
          li.classList.add("is-menu-open");
          try {
            if (navigator.vibrate) navigator.vibrate(12);
          } catch (_vib) {
            /* ignore */
          }
          openDraftMenu(li, holdX, holdY);
        }, holdMs);
      });
      function clearHold() {
        if (holdTimer) {
          clearTimeout(holdTimer);
          holdTimer = 0;
        }
        li.classList.remove("is-hold");
      }
      li.addEventListener("pointerup", clearHold);
      li.addEventListener("pointercancel", clearHold);
      li.addEventListener("pointerleave", clearHold);
      li.addEventListener("pointermove", function (event) {
        if (!holdTimer) return;
        if (Math.abs(event.clientX - holdX) > 8 || Math.abs(event.clientY - holdY) > 8) clearHold();
      });
    });
  }
  bindDraftContextMenu(document);
  document.addEventListener("click", closeDraftMenu);

  document.querySelectorAll("[data-remove-site]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const slug = button.getAttribute("data-remove-site") || "";
      if (!slug) return;
      const res = await postJson(
        "/api/builder-core/meta/sites/" + encodeURIComponent(slug) + "/remove",
        {}
      );
      if (res.ok) window.location.reload();
    });
  });

  const importEl = document.getElementById("da-import");
  const fileEl = document.getElementById("da-import-file");
  const syncEl = document.getElementById("da-sync");
  const cloudEl = document.getElementById("da-cloud-drafts");

  async function fillCloudDrafts() {
    if (!cloudEl) return;
    const desktop = window.zintriqDesktop;
    if (!desktop || !desktop.listMine) return;
    const data = await desktop.listMine();
    if (!data || data.error === "not signed in" || data.status === 401) {
      cloudEl.innerHTML = '<li class="da-empty">Sign in to list drafts saved to your account.</li>';
      return;
    }
    const drafts = (data && data.drafts) || [];
    if (!drafts.length) {
      cloudEl.innerHTML = '<li class="da-empty">No cloud drafts yet. Save while signed in.</li>';
      return;
    }
    cloudEl.innerHTML = "";
    drafts.forEach(function (item) {
      const li = document.createElement("li");
      const link = document.createElement("a");
      link.href = "/studio/meta/" + encodeURIComponent(item.slug || "");
      link.textContent = item.title || item.slug;
      li.appendChild(link);
      if (item.updated_at) {
        const span = document.createElement("span");
        span.textContent = item.updated_at;
        li.appendChild(span);
      }
      cloudEl.appendChild(li);
    });
  }

  if (syncEl) {
    syncEl.addEventListener("click", async function () {
      const desktop = window.zintriqDesktop;
      if (!desktop || !desktop.syncNow) return;
      syncEl.disabled = true;
      try {
        await desktop.syncNow();
        window.location.reload();
      } finally {
        syncEl.disabled = false;
      }
    });
  }

  fillCloudDrafts();

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

  function packRowActions(li, packId) {
    const disable = document.createElement("button");
    disable.type = "button";
    disable.className = "da-btn da-btn--tiny";
    disable.setAttribute("data-pack-disable", packId);
    disable.textContent = "Disable";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "da-btn da-btn--tiny";
    remove.setAttribute("data-pack-remove", packId);
    remove.textContent = "Remove";
    li.appendChild(disable);
    li.appendChild(remove);
    bindPackButtons(li);
  }

  function bindPackButtons(root) {
    (root || document).querySelectorAll("[data-pack-disable]").forEach(function (button) {
      if (button.getAttribute("data-bound") === "1") return;
      button.setAttribute("data-bound", "1");
      button.addEventListener("click", async function () {
        const id = button.getAttribute("data-pack-disable") || "";
        if (!id || !window.zintriq || !window.zintriq.http) return;
        const res = await window.zintriq.http.post("/api/plugin/disable", { id: id });
        if (!res.ok) return;
        notifyPluginsChanged();
        await refreshFactory();
      });
    });
    (root || document).querySelectorAll("[data-pack-remove]").forEach(function (button) {
      if (button.getAttribute("data-bound") === "1") return;
      button.setAttribute("data-bound", "1");
      button.addEventListener("click", async function () {
        const id = button.getAttribute("data-pack-remove") || "";
        if (!id || !window.zintriq || !window.zintriq.http) return;
        const bound =
          button.getAttribute("data-bound-draft") ||
          (button.closest("[data-pack-row]") && button.closest("[data-pack-row]").getAttribute("data-draft-slug")) ||
          "";
        const dropDraft = window.confirm(
          "Remove plugin " +
            id +
            ".\nBound draft: " +
            (bound || "(none)") +
            "\nOK = also delete that draft\nCancel = remove plugin only, keep draft"
        );
        const res = await window.zintriq.http.post("/api/plugin/remove", { id: id, delete_draft: dropDraft });
        const data = await res.json().catch(function () {
          return {};
        });
        if (!res.ok) return;
        try {
          const last = JSON.parse(sessionStorage.getItem("zintriq-rebind-last") || "{}");
          if (last && last.id === id) sessionStorage.removeItem("zintriq-rebind-last");
        } catch (_err) {
          /* ignore */
        }
        const probe = document.getElementById("da-probe");
        if (probe && data.binding_cleared) {
          probe.textContent = "Removed " + id + " · cleared bind " + data.binding_cleared;
        }
        if (data.binding_cleared) notifyBindingCleared(id, data.binding_cleared);
        notifyPluginsChanged();
        await refreshFactory();
      });
    });
  }

  async function refreshCurrentDrafts() {
    const list = document.getElementById("da-factory");
    if (!list || !window.zintriq || !window.zintriq.http) return;
    const res = await window.zintriq.http.get("/api/builder-core/meta/drafts");
    const data = await res.json().catch(function () {
      return {};
    });
    const current = (data && data.current) || "";
    const drafts = (data && data.drafts) || [];
    if (current) {
      document.body.setAttribute("data-draft-slug", current);
      try {
        sessionStorage.setItem("zintriq-draft-slug", current);
      } catch (_err) {
        /* ignore */
      }
    }
    const seen = {};
    drafts.forEach(function (row) {
      if (row && row.slug) seen[row.slug] = row;
    });
    list.querySelectorAll("[data-draft-row]").forEach(function (li) {
      const slug = li.getAttribute("data-draft-row") || "";
      if (!seen[slug]) {
        li.remove();
        return;
      }
      const row = seen[slug];
      const isCurrent = !!current && slug === current;
      li.classList.toggle("is-current", isCurrent);
      li.classList.toggle("is-current-empty", isCurrent && !!row.empty);
      li.classList.toggle("is-empty", !isCurrent && !!row.empty);
      if (row.empty) {
        li.setAttribute("data-draft-empty", "1");
        let mark = li.querySelector(".da-draft-empty");
        if (!mark) {
          mark = document.createElement("span");
          mark.className = "da-draft-empty";
          const link = li.querySelector("a");
          if (link && link.nextSibling) li.insertBefore(mark, link.nextSibling);
          else li.appendChild(mark);
        }
        mark.textContent = isCurrent ? "Current · Empty" : "Empty";
        li.querySelectorAll("[data-fill-draft], [data-rename-draft], [data-remove-draft]").forEach(function (btn) {
          btn.remove();
        });
        if (!li.querySelector(".da-draft-hint")) {
          const hint = document.createElement("span");
          hint.className = "da-draft-hint";
          hint.textContent = "Right-click for Fill / Rename / Remove";
          li.appendChild(hint);
        }
        bindDraftContextMenu(li);
      } else {
        li.removeAttribute("data-draft-empty");
        li.removeAttribute("data-menu-bound");
        const mark = li.querySelector(".da-draft-empty");
        if (mark) mark.remove();
        const hint = li.querySelector(".da-draft-hint");
        if (hint) hint.remove();
        if (!li.querySelector("[data-rename-draft]")) {
          const rename = document.createElement("button");
          rename.type = "button";
          rename.className = "da-btn da-btn--tiny";
          rename.setAttribute("data-rename-draft", slug);
          rename.textContent = "Rename";
          li.appendChild(rename);
          const rm = document.createElement("button");
          rm.type = "button";
          rm.className = "da-btn da-btn--tiny";
          rm.setAttribute("data-remove-draft", slug);
          rm.textContent = "Remove";
          li.appendChild(rm);
          bindDraftButtons(li);
        }
      }
    });
    drafts.forEach(function (row) {
      if (!row || !row.slug) return;
      if (list.querySelector('[data-draft-row="' + row.slug + '"]')) return;
      const li = document.createElement("li");
      li.setAttribute("data-draft-row", row.slug);
      const isCurrent = !!current && row.slug === current;
      if (row.empty) li.setAttribute("data-draft-empty", "1");
      if (isCurrent) li.classList.add("is-current");
      if (isCurrent && row.empty) li.classList.add("is-current-empty");
      else if (row.empty) li.classList.add("is-empty");
      const link = document.createElement("a");
      link.href = "/studio/meta/" + encodeURIComponent(row.slug);
      link.textContent = row.slug;
      li.appendChild(link);
      if (row.empty) {
        const mark = document.createElement("span");
        mark.className = "da-draft-empty";
        mark.textContent = isCurrent ? "Current · Empty" : "Empty";
        li.appendChild(mark);
      }
      if (row.updated_at) {
        const span = document.createElement("span");
        span.textContent = row.updated_at;
        li.appendChild(span);
      }
      if (row.empty) {
        const hint = document.createElement("span");
        hint.className = "da-draft-hint";
        hint.textContent = "Right-click for Fill / Rename / Remove";
        li.appendChild(hint);
      } else {
        const rename = document.createElement("button");
        rename.type = "button";
        rename.className = "da-btn da-btn--tiny";
        rename.setAttribute("data-rename-draft", row.slug);
        rename.textContent = "Rename";
        const rm = document.createElement("button");
        rm.type = "button";
        rm.className = "da-btn da-btn--tiny";
        rm.setAttribute("data-remove-draft", row.slug);
        rm.textContent = "Remove";
        li.appendChild(rename);
        li.appendChild(rm);
        bindDraftButtons(li);
      }
      const empty = list.querySelector(".da-empty");
      if (empty) empty.remove();
      list.insertBefore(li, list.firstChild);
      if (row.empty) bindDraftContextMenu(li);
    });
  }

  async function refreshInstalledPacks() {
    const list = document.getElementById("da-factory");
    if (!list || !window.zintriq || !window.zintriq.http) return;
    const res = await window.zintriq.http.get("/api/plugin");
    const data = await res.json().catch(function () {
      return {};
    });
    const have = ((data && data.packs) || []).filter(function (row) {
      return row && row.installed && row.id;
    });
    const seen = {};
    have.forEach(function (row) {
      seen[row.id] = row;
    });
    list.querySelectorAll("[data-pack-row]").forEach(function (li) {
      const id = li.getAttribute("data-pack-id") || "";
      if (!seen[id]) li.remove();
    });
    have.forEach(function (pack) {
      let li = list.querySelector('[data-pack-row][data-pack-id="' + pack.id + '"]');
      if (!li) {
        li = document.createElement("li");
        li.setAttribute("data-pack-row", "1");
        li.setAttribute("data-pack-id", pack.id);
        const link = document.createElement("a");
        link.href = "/app/community#" + encodeURIComponent(pack.id);
        link.setAttribute("data-pack-id", pack.id);
        link.textContent = pack.name || pack.id;
        const mark = document.createElement("span");
        mark.textContent = "Plugin";
        li.appendChild(link);
        li.appendChild(mark);
        packRowActions(li, pack.id);
        const empty = list.querySelector(".da-empty");
        if (empty) empty.remove();
        list.appendChild(li);
      }
      if (pack.draft_slug) {
        li.setAttribute("data-draft-slug", pack.draft_slug);
        const rm = li.querySelector("[data-pack-remove]");
        if (rm) rm.setAttribute("data-bound-draft", pack.draft_slug);
      }
    });
    if (!list.querySelector("[data-draft-row], [data-pack-row], [data-remove-site]") && !list.querySelector(".da-empty")) {
      const li = document.createElement("li");
      li.className = "da-empty";
      li.textContent = "Nothing here yet. New opens a blank document. Community adds tools.";
      list.appendChild(li);
    }
  }

  async function refreshFactory() {
    await refreshCurrentDrafts();
    await refreshInstalledPacks();
  }

  window.addEventListener("zintriq-plugins-changed", refreshFactory);
  window.addEventListener("pageshow", refreshFactory);
  const bus = pluginChannel();
  if (bus) bus.addEventListener("message", refreshFactory);
  setInterval(refreshFactory, 4000);
  bindPackButtons(document);
  refreshFactory();

  function isPluginFile(file) {
    return /\.zintriq-plugin\.json$/i.test((file && file.name) || "");
  }

  function looksLikePluginPack(obj) {
    if (!obj || typeof obj !== "object") return false;
    const id = String(obj.id || "");
    const file = String(obj.file || "");
    if (id.indexOf("official-") === 0 || id.indexOf("community-") === 0) return true;
    if (/\.zintriq-plugin\.json$/i.test(file)) return true;
    if (obj.stamp || obj.signature) return true;
    if (obj.origin === "official" || obj.origin === "third" || obj.origin === "remote") return true;
    if (id && obj.view && obj.form) return true;
    return false;
  }

  async function installPluginFile(file, manifest, options) {
    const opts = options || {};
    let pack = manifest;
    if (!pack) {
      const text = await file.text();
      try {
        pack = JSON.parse(text);
      } catch (_err) {
        return null;
      }
    }
    const ident = (pack && pack.id) || "";
    const res = await window.zintriq.http.post("/api/plugin/install", { id: ident, manifest: pack });
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) return null;
    notifyPluginsChanged();
    if (opts.navigate === false) return data;
    const params = new URLSearchParams();
    const slug = document.body.getAttribute("data-draft-slug") || data.draft || "";
    const pane = data.pane || "";
    if (slug) params.set("draft", slug);
    if (pane && pane !== "code") params.set("pane", pane);
    const q = params.toString();
    window.location.href = "/studio" + (q ? "?" + q : "");
    return data;
  }

  async function importSiteFile(file, blob) {
    const form = new FormData();
    form.append("site", blob || file, (file && file.name) || "import.json");
    const res = await window.zintriq.http.post("/api/builder-core/meta/sites/import", form);
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) return null;
    return data;
  }

  const skippedQueue = [];
  let retryCancelFlag = false;

  function paintSkippedProbe(progress) {
    const probe = document.getElementById("da-probe");
    if (!probe) return;
    if (!skippedQueue.length && !(progress && progress.total)) return;
    probe.textContent = "";
    if (progress && progress.total) {
      const prog = document.createElement("span");
      prog.className = "da-retry-progress";
      prog.setAttribute("data-retry-progress", "1");
      prog.textContent =
        "Retrying " +
        Math.min(progress.done || 0, progress.total) +
        "/" +
        progress.total +
        (progress.name ? " · " + progress.name : "") +
        " ";
      probe.appendChild(prog);
      if (progress.running) {
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "da-btn da-btn--tiny";
        cancelBtn.setAttribute("data-retry-cancel", "1");
        cancelBtn.textContent = "Cancel";
        cancelBtn.addEventListener("click", function () {
          if (cancelBtn.getAttribute("data-confirming") === "1") {
            retryCancelFlag = true;
            cancelBtn.disabled = true;
            cancelBtn.textContent = "Cancelling…";
            return;
          }
          cancelBtn.setAttribute("data-confirming", "1");
          cancelBtn.textContent = "Confirm cancel?";
          cancelBtn.classList.add("is-confirm");
          window.setTimeout(function () {
            if (cancelBtn.getAttribute("data-confirming") === "1" && !retryCancelFlag) {
              cancelBtn.removeAttribute("data-confirming");
              cancelBtn.classList.remove("is-confirm");
              cancelBtn.textContent = "Cancel";
            }
          }, 2800);
        });
        probe.appendChild(cancelBtn);
        probe.appendChild(document.createTextNode(" "));
      }
    }
    if (!skippedQueue.length) return;
    const lead = document.createElement("span");
    lead.id = "da-skipped-lead";
    lead.setAttribute("tabindex", "-1");
    lead.textContent = "Skipped " + skippedQueue.length + " file" + (skippedQueue.length === 1 ? "" : "s") + ": ";
    probe.appendChild(lead);
    if (skippedQueue.length > 1 && !(progress && progress.running)) {
      const allBtn = document.createElement("button");
      allBtn.type = "button";
      allBtn.className = "da-btn da-btn--tiny";
      allBtn.textContent = "Retry all";
      allBtn.setAttribute("data-retry-all", "1");
      allBtn.addEventListener("click", async function () {
        allBtn.disabled = true;
        const batch = skippedQueue.slice().map(function (row) {
          return row.file;
        }).filter(Boolean);
        skippedQueue.length = 0;
        await openLocalFiles(batch, { fromRetry: true, retryAll: true });
      });
      probe.appendChild(allBtn);
      probe.appendChild(document.createTextNode(" "));
    }
    skippedQueue.forEach(function (item, index) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "da-btn da-btn--tiny";
      btn.textContent = "Retry " + (item.name || "file");
      btn.setAttribute("data-retry-skip", String(index));
      if (progress && progress.running) btn.disabled = true;
      btn.addEventListener("click", async function () {
        const row = skippedQueue[index];
        if (!row || !row.file) return;
        btn.disabled = true;
        await openLocalFiles([row.file], { fromRetry: true, retryIndex: index });
      });
      probe.appendChild(btn);
      probe.appendChild(document.createTextNode(" "));
    });
  }

  async function openLocalFiles(fileList, options) {
    const opts = options || {};
    const files = Array.prototype.slice.call(fileList || []).filter(Boolean);
    if (!files.length) return;
    let installed = 0;
    let lastOpen = null;
    let lastPane = "";
    if (!opts.fromRetry) skippedQueue.length = 0;
    const total = files.length;
    const showProgress = !!opts.retryAll && total > 1;
    if (opts.retryAll) retryCancelFlag = false;
    let wasCancelled = false;
    for (let i = 0; i < files.length; i += 1) {
      if (opts.retryAll && retryCancelFlag) {
        wasCancelled = true;
        for (let j = i; j < files.length; j += 1) {
          const left = files[j];
          skippedQueue.push({ file: left, name: (left && left.name) || "" });
        }
        break;
      }
      const file = files[i];
      const name = (file && file.name) || "";
      if (showProgress) {
        paintSkippedProbe({
          done: i,
          total: total,
          name: name,
          running: true,
        });
      }
      let ok = false;
      try {
        if (/\.json$/i.test(name)) {
          let text;
          try {
            text = await file.text();
          } catch (_readErr) {
            text = "";
          }
          let obj = null;
          if (text) {
            try {
              obj = JSON.parse(text);
            } catch (_err) {
              obj = null;
            }
          }
          if (!text || obj == null) {
            /* bad json */
          } else if (isPluginFile(file) || looksLikePluginPack(obj)) {
            const data = await installPluginFile(file, obj, { navigate: false });
            if (data) {
              installed += 1;
              if (data.pane) lastPane = data.pane;
              ok = true;
            }
          } else {
            const blob = new Blob([text], { type: "application/json" });
            const data = await importSiteFile(file, blob);
            if (data) {
              lastOpen = data;
              ok = true;
            }
          }
        } else if (isPluginFile(file)) {
          const data = await installPluginFile(file, null, { navigate: false });
          if (data) {
            installed += 1;
            if (data.pane) lastPane = data.pane;
            ok = true;
          }
        } else {
          const data = await importSiteFile(file);
          if (data) {
            lastOpen = data;
            ok = true;
          }
        }
      } catch (_itemErr) {
        ok = false;
      }
      if (!ok) {
        if (opts.fromRetry && opts.retryIndex != null) {
          /* keep slot until success */
        } else {
          skippedQueue.push({ file: file, name: name });
        }
      } else if (opts.fromRetry && opts.retryIndex != null) {
        skippedQueue.splice(opts.retryIndex, 1);
      }
      if (showProgress) {
        paintSkippedProbe({
          done: i + 1,
          total: total,
          name: name,
          running: i + 1 < total,
        });
      }
    }
    await refreshFactory();
    paintSkippedProbe();
    if (wasCancelled && skippedQueue.length) {
      const probe = document.getElementById("da-probe");
      const lead = document.getElementById("da-skipped-lead");
      if (probe && typeof probe.scrollIntoView === "function") {
        probe.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
      if (lead) {
        try {
          lead.focus({ preventScroll: true });
        } catch (_focusErr) {
          try {
            lead.focus();
          } catch (_focusErr2) {
            /* ignore */
          }
        }
      }
    }
    if (lastOpen) {
      if (lastOpen.studio) {
        window.location.href = lastOpen.studio;
      } else if (lastOpen.slug) {
        window.location.href = "/studio/meta/" + encodeURIComponent(lastOpen.slug);
      } else {
        window.location.reload();
      }
      return;
    }
    if (installed && !opts.fromRetry) {
      const params = new URLSearchParams();
      const slug = document.body.getAttribute("data-draft-slug") || "";
      if (slug) params.set("draft", slug);
      if (lastPane && lastPane !== "code") params.set("pane", lastPane);
      const q = params.toString();
      window.location.href = "/studio" + (q ? "?" + q : "");
    } else if (installed && opts.fromRetry) {
      paintSkippedProbe();
    }
  }

  async function openLocalFile(file) {
    await openLocalFiles(file ? [file] : []);
  }

  const stage = document.querySelector(".da-welcome-stage");
  if (stage) {
    stage.addEventListener("dragover", function (event) {
      event.preventDefault();
    });
    stage.addEventListener("drop", function (event) {
      event.preventDefault();
      const files = event.dataTransfer && event.dataTransfer.files;
      openLocalFiles(files);
    });
  }

  const probeEl = document.getElementById("da-probe");
  let lastProbe = null;
  async function copyDiag() {
    const info = lastProbe || {};
    const text =
      "exit " +
      (info.exitCode == null ? "?" : info.exitCode) +
      "\nreason " +
      (info.reason || "") +
      "\nportInUse " +
      (info.portInUse ? "true" : "false") +
      "\ntokenOk " +
      (info.tokenOk === false ? "false" : "true") +
      "\nlogPath " +
      (info.logPath || "") +
      "\n" +
      (info.logTail || "");
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) await navigator.clipboard.writeText(text);
    } catch {
      /* ignore */
    }
  }
  const copyLogEl = document.getElementById("da-copy-log");
  if (copyLogEl) copyLogEl.addEventListener("click", copyDiag);
  async function checkHost() {
    if (!probeEl) return;
    try {
      const desktop = window.zintriqDesktop;
      if (desktop && desktop.probe) {
        const info = await desktop.probe();
        lastProbe = info || lastProbe;
        if (info && info.ok === false) {
          probeEl.textContent = info.next || "Local host is not running. Quit Zintriq and open it again.";
          probeEl.classList.add("is-down");
          const diag = document.getElementById("da-diag");
          if (diag) {
            diag.hidden = false;
            const reason = document.getElementById("da-diag-reason");
            const next = document.getElementById("da-diag-next");
            const log = document.getElementById("da-diag-log");
            if (reason) reason.textContent = "reason: " + (info.reason || "flask_down") + " · exit " + (info.exitCode == null ? "?" : info.exitCode) + " · token " + (info.tokenOk === false ? "mismatch" : "ok") + " · port " + (info.portInUse ? "in use" : "free");
            if (next) next.textContent = info.next || "";
            if (log) log.textContent = info.logTail || info.logPath || "";
          }
          return;
        }
        if (info && info.host) {
          probeEl.textContent = "Local host: " + info.host;
          probeEl.classList.remove("is-down");
        }
      }
      const res = await window.zintriq.http.get("/healthz");
      if (!res.ok) throw new Error("down");
      if (!probeEl.textContent || probeEl.textContent.indexOf("checking") !== -1) {
        probeEl.textContent = "Local host: running";
      }
      probeEl.classList.remove("is-down");
    } catch {
      probeEl.textContent = "Local host stopped. Quit Zintriq and open it again. If the port is in use, close the other copy. Check userData/logs/flask.log.";
      probeEl.classList.add("is-down");
    }
  }
  checkHost();
  setInterval(checkHost, 4000);

  const stampForm = document.getElementById("da-stamp");
  const savePlugin = document.getElementById("da-save-plugin");
  const stampStatus = document.getElementById("da-stamp-status");
  const exportStatus = document.getElementById("da-export-status");

  if (savePlugin && stampForm) {
    savePlugin.addEventListener("click", function () {
      stampForm.hidden = !stampForm.hidden;
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
      if (stampStatus) stampStatus.textContent = "Saving…";
      const res = await postJson("/api/plugin/stamp", { name: name, form: form });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        if (stampStatus) stampStatus.textContent = data.error || "Save failed";
        return;
      }
      window.location.href = "/app/community";
    });
  }

  document.querySelectorAll("[data-export]").forEach(function (button) {
    button.addEventListener("click", async function () {
      const kind = button.getAttribute("data-export") || "";
      if (exportStatus) exportStatus.textContent = "Exporting…";
      const res = await postJson("/api/builder-core/meta/produce", {
        kind: kind === "webpage" ? "page" : kind === "app" ? "engine" : "plugin",
        title: kind === "plugin" ? "Exported plugin" : kind === "app" ? "Exported app" : "Exported page",
        prompt: kind === "plugin" ? "view" : "",
        slug: kind === "webpage" ? "export-page" : kind === "app" ? "export-app" : "export-plugin",
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        if (exportStatus) exportStatus.textContent = data.error || "Export failed";
        return;
      }
      if (kind === "plugin") {
        window.location.href = "/app/community";
        return;
      }
      if (kind === "webpage" && data.studio) {
        if (data.zip_url) {
          const link = document.createElement("a");
          link.href = data.zip_url;
          link.setAttribute("download", (data.slug || "site") + ".zip");
          document.body.appendChild(link);
          link.click();
          link.remove();
        }
        window.location.href = data.studio;
        return;
      }
      if (data.zip_url) {
        window.location.href = data.zip_url;
        return;
      }
      if (data.studio) {
        window.location.href = data.studio;
        return;
      }
      if (data.public_url) {
        window.location.href = data.public_url + (String(data.public_url).indexOf("/build/") === 0 ? "/home" : "");
        return;
      }
      if (exportStatus) exportStatus.textContent = "Exported " + (data.slug || data.kind || kind);
    });
  });

  const relaunchEl = document.getElementById("da-relaunch");
  if (relaunchEl && window.zintriqDesktop && window.zintriqDesktop.relaunch) {
    relaunchEl.addEventListener("click", function () {
      window.zintriqDesktop.relaunch();
    });
  }
  const keymapConflictsEl = document.getElementById("da-keymap-conflicts");
  const keymapExport = document.getElementById("da-keymap-export");
  const keymapImport = document.getElementById("da-keymap-import");
  const keymapFile = document.getElementById("da-keymap-file");
  if (keymapExport && window.zintriqDesktop && window.zintriqDesktop.exportKeymap) {
    keymapExport.addEventListener("click", function () {
      window.zintriqDesktop.exportKeymap();
    });
  }
  if (keymapImport && keymapFile) {
    keymapImport.addEventListener("click", function () {
      keymapFile.click();
    });
    keymapFile.addEventListener("change", async function () {
      const file = keymapFile.files && keymapFile.files[0];
      keymapFile.value = "";
      if (!file || !window.zintriqDesktop || !window.zintriqDesktop.importKeymap) return;
      const text = await file.text();
      const result = await window.zintriqDesktop.importKeymap(text);
      if (keymapConflictsEl) {
        if (result && result.conflicts && result.conflicts.length) {
          keymapConflictsEl.textContent = "Conflict: " + result.conflicts.map(function (row) {
            return row.keys + " " + row.a + " / " + row.b;
          }).join("; ");
        } else {
          keymapConflictsEl.textContent = result && result.ok ? "Keymap saved on this machine." : (result && result.error) || "";
        }
      }
    });
  }

  if (!importEl || !fileEl) return;
  importEl.addEventListener("click", function () {
    fileEl.click();
  });
  fileEl.addEventListener("change", async function () {
    const files = fileEl.files;
    fileEl.value = "";
    openLocalFiles(files);
  });
})();
