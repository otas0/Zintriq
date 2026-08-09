import * as store from "../core/store.js";
import { getDefaultUi, setModuleUi } from "../core/ui-state.js";
import { captureScroll, restoreScroll, setActionMode } from "../core/continuity.js";
import { renderCardGrid, renderFilterBar, statusBadge, emptyState, showContextMenu, tag } from "../components/index.js";
import { renderAdvancedTable, resolveColumns, renderColumnPicker } from "../components/advanced-table.js";
import { showToast, renderActionBar, openDrawer, closeDrawer } from "../services/api.js";
import { escapeHtml } from "../services/search.js";
import { selection } from "../services/selection.js";
import { exportRecords, openWorkspacePicker, openTagPicker } from "../services/batch-actions.js";
import { openObjectDetail, openCreateObject } from "../platform/object-detail.js";
import { getObjectTitle, getObjectType } from "../platform/object-types.js";

const BULK = [
  { label: "Edit", action: "edit", variant: "primary" },
  { label: "Move", action: "move" },
  { label: "Archive", action: "archive" },
  { label: "Restore", action: "restore" },
  { label: "Duplicate", action: "duplicate" },
  { label: "Export", action: "export" },
  { label: "Tag", action: "tag" },
  { label: "Delete", action: "delete", variant: "danger" },
];

function haystack(row) {
  return Object.values(row)
    .flatMap((v) => (Array.isArray(v) ? v : [v]))
    .filter((v) => typeof v === "string" || typeof v === "number")
    .join(" ")
    .toLowerCase();
}

export function mountInteractiveModule(root, moduleId, config) {
  const ui = getDefaultUi(moduleId);
  let localSearch = ui.search || "";
  let lastClickedId = null;
  let cachedItems = [];

  document.getElementById("bos-filter-row")?.classList.remove("hidden");
  const filterBar = document.getElementById("bos-filter-bar");
  const searchInput = document.getElementById("bos-search-input");
  const toolbarActions = document.getElementById("bos-page-actions-mount");
  const workspace = document.getElementById("bos-workspace");

  root.innerHTML = `<div class="bos-module-toolbar" id="bos-module-toolbar"></div><div class="bos-module-content" id="bos-module-content"></div>`;
  const content = document.getElementById("bos-module-content");
  const moduleToolbar = document.getElementById("bos-module-toolbar");

  const persistUi = (patch) => {
    Object.assign(ui, patch);
    setModuleUi(moduleId, patch);
  };

  const refreshOpts = { refresh: () => renderList() };

  const openRecord = (record) => {
    openObjectDetail(config.collection, record.id, refreshOpts);
  };

  const syncSelectionUi = () => {
    setActionMode(selection.size > 0);
    if (content) {
      content.querySelectorAll("tr[data-clickable], .bos-card").forEach((el) => {
        const id = el.getAttribute("data-id");
        el.classList.toggle("is-selected", id != null && selection.has(id));
      });
      content.querySelectorAll('input[type="checkbox"][data-id], input[data-select-id]').forEach((input) => {
        const id = input.getAttribute("data-id") || input.getAttribute("data-select-id");
        if (id && input instanceof HTMLInputElement) input.checked = selection.has(id);
      });
    }
    renderActionBar(selection.size, BULK, handleBulkAction);
  };

  const handleBulkAction = (action) => {
    const ids = [...selection.selected];
    if (!ids.length) return;

    if (action === "edit") {
      openBatchEdit(ids);
      return;
    }
    if (action === "export") {
      exportRecords(config.collection, ids);
      showToast(`Exported ${ids.length} record(s)`);
      selection.clear();
      renderList();
      return;
    }
    if (action === "move") {
      const typeDef = getObjectType(config.collection);
      const canMove = typeDef?.properties.some((p) => p.key === "workspaceId");
      if (!canMove) { showToast("Move not available for this module"); return; }
      if (!openWorkspacePicker((wsId) => {
        ids.forEach((id) => store.update(config.collection, id, { workspaceId: wsId }, { action: "moved" }));
        showToast(`Moved ${ids.length} to ${store.resolveRelation("workspaces", wsId)}`);
        selection.clear();
        renderList();
      })) showToast("No workspaces available");
      return;
    }
    if (action === "tag") {
      if (!openTagPicker((tagId) => {
        store.batch(config.collection, ids, "tag", { tagId });
        showToast(`Tagged ${ids.length} record(s)`);
        selection.clear();
        renderList();
      })) showToast("No tags available");
      return;
    }
    if (action === "delete") {
      if (!window.confirm(`Delete ${ids.length} selected record(s)?`)) return;
      const snapshots = ids.map((id) => store.getById(config.collection, id)).filter(Boolean);
      store.batch(config.collection, ids, "delete");
      showToast(`Deleted ${ids.length} record(s)`, {
        undoLabel: "Undo delete",
        undo: () => {
          snapshots.forEach((row) => store.insertRecord(config.collection, row));
          renderList();
        },
      });
      selection.clear();
      renderList();
      return;
    }
    store.batch(config.collection, ids, action);
    showToast(`${action} — ${ids.length} record(s)`);
    selection.clear();
    renderList();
  };

  const openBatchEdit = (ids) => {
    const sample = store.getById(config.collection, ids[0]);
    if (!sample) return;
    const statuses = [...new Set(cachedItems.map((r) => r.status).filter(Boolean))];
    openDrawer(`Edit ${ids.length} selected`, `
      <form class="bos-batch-edit" id="bos-batch-edit-form">
        <p class="bos-empty__text">Changes apply to all ${ids.length} selected records.</p>
        ${sample.status != null ? `<label class="bos-sort-label">Status
          <select class="os-select" name="status">
            <option value="">— No change —</option>
            ${statuses.map((s) => `<option value="${escapeHtml(String(s))}">${escapeHtml(String(s))}</option>`).join("")}
            <option value="archived">archived</option>
            <option value="active">active</option>
          </select>
        </label>` : ""}
        <div class="bos-drawer-form__actions">
          <button type="button" class="os-btn os-btn-ghost os-btn-sm" id="bos-batch-cancel">Cancel</button>
          <button type="submit" class="os-btn os-btn-primary os-btn-sm">Apply</button>
        </div>
      </form>`);
    document.getElementById("bos-batch-cancel")?.addEventListener("click", closeDrawer);
    document.getElementById("bos-batch-edit-form")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const status = String(fd.get("status") || "");
      if (status) ids.forEach((id) => store.update(config.collection, id, { status }));
      showToast(`Updated ${ids.length} record(s)`);
      closeDrawer();
      selection.clear();
      renderList();
    });
  };

  const toggleSelect = (id, shiftKey = false) => {
    if (shiftKey && lastClickedId != null) {
      const ids = cachedItems.map((r) => r.id);
      const a = ids.indexOf(lastClickedId);
      const b = ids.indexOf(id);
      if (a >= 0 && b >= 0) {
        const [start, end] = a < b ? [a, b] : [b, a];
        ids.slice(start, end + 1).forEach((rid) => selection.selected.add(rid));
        selection.notify();
        lastClickedId = id;
        syncSelectionUi();
        return;
      }
    }
    lastClickedId = id;
    selection.toggle(id);
    syncSelectionUi();
  };

  const renderToolbar = () => {
    if (toolbarActions) {
      let createBtn = document.getElementById("bos-create-btn");
      if (!createBtn) {
        createBtn = document.createElement("button");
        createBtn.type = "button";
        createBtn.id = "bos-create-btn";
        createBtn.className = "os-btn os-btn-primary os-btn-sm";
        toolbarActions.appendChild(createBtn);
      }
      createBtn.textContent = config.createLabel || "Create";
      createBtn.onclick = () => openCreateObject(config.collection, refreshOpts);
    }
    if (moduleToolbar) {
      const sortOptions = [
        { key: config.sortKey || "name", label: "Default" },
        { key: "updatedAt", label: "Updated" },
        { key: "status", label: "Status" },
      ].filter((o, i, arr) => arr.findIndex((x) => x.key === o.key) === i);

      const tagFilter = config.collection !== "tags" ? store.getCollection("tags") : [];
      const browseHidden = selection.size > 0 ? " hidden" : "";

      moduleToolbar.innerHTML = `<div class="bos-module-toolbar__controls">
        <div class="bos-view-toggle bos-browse-tools${browseHidden}" id="bos-browse-tools">
          <button type="button" class="bos-filter-chip${ui.view === "table" ? " is-active" : ""}" data-view="table">Table</button>
          <button type="button" class="bos-filter-chip${ui.view === "card" ? " is-active" : ""}" data-view="card">Cards</button>
        </div>
        <label class="bos-sort-label bos-browse-tools${browseHidden}">Sort
          <select class="os-select os-select-sm" id="bos-sort-select">
            ${sortOptions.map((o) => `<option value="${o.key}"${(ui.sortKey || config.sortKey) === o.key ? " selected" : ""}>${escapeHtml(o.label)}</option>`).join("")}
          </select>
        </label>
        ${tagFilter.length ? `<label class="bos-sort-label bos-browse-tools${browseHidden}">Tag
          <select class="os-select os-select-sm" id="bos-tag-filter">
            <option value="">All tags</option>
            ${tagFilter.map((t) => `<option value="${t.id}"${ui.tagId === t.id ? " selected" : ""}>${escapeHtml(String(t.name))}</option>`).join("")}
          </select>
        </label>` : ""}
        <button type="button" class="bos-filter-chip bos-browse-tools${browseHidden}${ui.groupBy ? " is-active" : ""}" data-group-toggle>Group by status</button>
        <span id="bos-col-picker-host" class="bos-browse-tools${browseHidden}"></span>
        <div class="bos-density-toggle bos-browse-tools${browseHidden}">
          <button type="button" class="bos-filter-chip${ui.density === "compact" ? " is-active" : ""}" data-density="compact" title="Compact">Compact</button>
          <button type="button" class="bos-filter-chip${ui.density === "comfortable" ? " is-active" : ""}" data-density="comfortable" title="Comfortable">Comfortable</button>
        </div>
        ${selection.size > 0 ? `<span class="bos-selection-hint">${selection.size} selected · <button type="button" class="bos-link-btn" id="bos-clear-selection">Clear</button></span>` : ""}
      </div>`;

      moduleToolbar.querySelectorAll("[data-view]").forEach((btn) => {
        btn.addEventListener("click", () => {
          ui.view = btn.getAttribute("data-view") || "table";
          persistUi({ view: ui.view });
          renderList();
        });
      });
      moduleToolbar.querySelector("#bos-sort-select")?.addEventListener("change", (e) => {
        if (!(e.target instanceof HTMLSelectElement)) return;
        ui.sortKey = e.target.value;
        persistUi({ sortKey: ui.sortKey });
        renderList();
      });
      moduleToolbar.querySelector("#bos-tag-filter")?.addEventListener("change", (e) => {
        if (!(e.target instanceof HTMLSelectElement)) return;
        ui.tagId = e.target.value || "";
        persistUi({ tagId: ui.tagId });
        renderList();
      });
      moduleToolbar.querySelector("[data-group-toggle]")?.addEventListener("click", () => {
        ui.groupBy = !ui.groupBy;
        persistUi({ groupBy: ui.groupBy });
        renderList();
      });
      moduleToolbar.querySelectorAll("[data-density]").forEach((btn) => {
        btn.addEventListener("click", () => {
          ui.density = btn.getAttribute("data-density") || "comfortable";
          persistUi({ density: ui.density });
          renderList();
        });
      });
      moduleToolbar.querySelector("#bos-clear-selection")?.addEventListener("click", () => {
        selection.clear();
      });

      if (ui.view === "table" && config.columns?.length) {
        renderColumnPicker(
          moduleToolbar.querySelector("#bos-col-picker-host"),
          config.columns,
          ui.tableLayout,
          (patch) => {
            ui.tableLayout = { ...ui.tableLayout, ...patch };
            persistUi({ tableLayout: ui.tableLayout });
            renderList();
          }
        );
      }
    }
  };

  const handleRowAction = (action, id) => {
    if (!id) return;
    if (action === "edit") {
      const row = store.getById(config.collection, id);
      if (row) openRecord(row);
      return;
    }
    if (action === "duplicate") store.duplicate(config.collection, id);
    if (action === "delete") {
      const row = store.getById(config.collection, id);
      if (!row) return;
      if (!window.confirm("Delete this record permanently?")) return;
      store.remove(config.collection, id);
      showToast("Deleted", {
        undoLabel: "Undo",
        undo: () => { store.insertRecord(config.collection, row); renderList(); },
      });
      renderList();
      return;
    }
    showToast(action);
    renderList();
  };

  const renderItems = (rows, target = content) => {
    if (!target) return;
    const typeDef = getObjectType(config.collection);

    if (ui.view === "card") {
      renderCardGrid(target, rows, (row) => {
        const selected = selection.has(row.id);
        return `<article class="bos-card${selected ? " is-selected" : ""}" data-id="${escapeHtml(String(row.id))}">
          <div class="bos-card__head"><h3 class="bos-card__title">${escapeHtml(getObjectTitle(row, typeDef))}</h3>${row.status ? statusBadge(String(row.status)) : ""}</div>
          <p class="bos-card__meta">${escapeHtml(String(row.email || row.sku || row.type || ""))}</p>
          ${row.tagIds?.length ? `<div class="bos-card__tags">${row.tagIds.map((tid) => tag(store.resolveRelation("tags", tid))).join(" ")}</div>` : ""}
          <label class="bos-card-check"><input type="checkbox"${selected ? " checked" : ""} data-select-id="${escapeHtml(String(row.id))}"> Select</label>
        </article>`;
      });
      target.querySelectorAll(".bos-card").forEach((card) => {
        card.addEventListener("click", (e) => {
          if (e.target instanceof HTMLInputElement) return;
          const row = rows.find((i) => i.id === card.getAttribute("data-id"));
          if (row) openRecord(row);
        });
        card.addEventListener("contextmenu", (e) => {
          e.preventDefault();
          showContextMenu(e, [
            { label: "Open", action: "edit" },
            { label: "Duplicate", action: "duplicate" },
            { label: "Delete", action: "delete" },
          ], (action) => handleRowAction(action, card.getAttribute("data-id")));
        });
      });
      target.querySelectorAll("[data-select-id]").forEach((input) => {
        input.addEventListener("click", (e) => {
          e.stopPropagation();
          const id = input.getAttribute("data-select-id");
          if (id) toggleSelect(id, e.shiftKey);
        });
      });
    } else {
      const cols = resolveColumns(config.columns || [], ui.tableLayout);
      renderAdvancedTable(
        target,
        rows,
        cols,
        {
          selectable: true,
          selected: selection.selected,
          density: ui.density,
          layout: ui.tableLayout,
          virtualize: true,
          onToggle: (id, shiftKey) => toggleSelect(id, shiftKey),
          onSelectAll: (checked, listRows) => {
            if (checked) selection.setAll(listRows.map((r) => r.id));
            else selection.clear();
            syncSelectionUi();
            renderToolbar();
          },
          onRowClick: (row, e) => {
            if (e.metaKey || e.ctrlKey) {
              toggleSelect(row.id, false);
              return;
            }
            openRecord(row);
          },
        },
        (patch) => {
          ui.tableLayout = { ...ui.tableLayout, ...patch };
          persistUi({ tableLayout: ui.tableLayout });
          renderList();
        }
      );
      target.querySelectorAll("tr[data-clickable]").forEach((tr) => {
        tr.addEventListener("contextmenu", (e) => {
          e.preventDefault();
          showContextMenu(e, [
            { label: "Open", action: "edit" },
            { label: "Duplicate", action: "duplicate" },
            { label: "Delete", action: "delete" },
          ], (action) => handleRowAction(action, tr.getAttribute("data-id")));
        });
      });
    }
  };

  const renderList = () => {
    if (!content) return;
    const scrollEl = workspace || content;
    const scrollTop = captureScroll(scrollEl);

    cachedItems = store.query(config.collection, {
      search: localSearch,
      filter: ui.filter,
      tagId: ui.tagId,
      sortKey: ui.sortKey || config.sortKey,
      sortAsc: ui.sortAsc,
      haystack,
    });

    renderFilterBar(filterBar, config.filters || [], ui.filter, (f) => {
      ui.filter = f;
      persistUi({ filter: f });
      renderList();
    });

    if (searchInput && document.activeElement !== searchInput) searchInput.value = localSearch;

    renderToolbar();

    if (!cachedItems.length) {
      content.innerHTML = emptyState({
        title: `No ${config.labelPlural || "items"} yet`,
        text: "Create your first record or adjust filters.",
        actionHtml: `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="bos-empty-create">${escapeHtml(config.createLabel || "Create")}</button>`,
      });
      document.getElementById("bos-empty-create")?.addEventListener("click", () => openCreateObject(config.collection, refreshOpts));
      renderActionBar(0, [], () => {});
      setActionMode(false);
      restoreScroll(scrollEl, scrollTop);
      persistUi({ scrollTop });
      return;
    }

    if (ui.groupBy) {
      const groups = new Map();
      cachedItems.forEach((row) => {
        const key = String(row.status || row.type || "Other");
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(row);
      });
      content.innerHTML = [...groups.entries()].map(([label, groupRows]) => `
        <section class="bos-group-section">
          <h3 class="bos-section-title">${escapeHtml(label)} <span class="bos-group-count">${groupRows.length}</span></h3>
          <div class="bos-group-body" data-group="${escapeHtml(label)}"></div>
        </section>`).join("");
      content.querySelectorAll(".bos-group-body").forEach((host) => {
        renderItems(groups.get(host.getAttribute("data-group")) || [], host);
      });
    } else {
      content.innerHTML = "";
      renderItems(cachedItems, content);
    }

    syncSelectionUi();
    restoreScroll(scrollEl, ui.scrollTop || scrollTop);
    persistUi({ scrollTop: captureScroll(scrollEl) });
  };

  searchInput?.addEventListener("input", () => {
    localSearch = searchInput.value;
    persistUi({ search: localSearch });
    renderList();
  });
  if (searchInput) searchInput.placeholder = `Search ${config.labelPlural || "items"}… (press /)`;

  workspace?.addEventListener("scroll", () => {
    persistUi({ scrollTop: captureScroll(workspace) });
  }, { passive: true });

  selection.subscribe(() => {
    syncSelectionUi();
    renderToolbar();
  });

  store.subscribe((col) => {
    if (!col || col === config.collection || col === "tags") renderList();
  });

  window.addEventListener("bos:select-all", () => {
    selection.setAll(cachedItems.map((r) => r.id));
  });

  window.addEventListener("bos:clear-selection", () => {
    selection.clear();
  });

  window.addEventListener("bos:batch-action", (e) => {
    const action = e.detail?.action;
    if (!action || !selection.size) return;
    handleBulkAction(action);
  });

  document.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    if (e.key === "n" && !e.metaKey && !e.ctrlKey) {
      e.preventDefault();
      openCreateObject(config.collection, refreshOpts);
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "a") {
      e.preventDefault();
      selection.setAll(cachedItems.map((r) => r.id));
    }
    if (e.key === "Escape" && selection.size > 0) {
      selection.clear();
    }
    if (e.key === "Delete" && selection.size > 0) {
      handleBulkAction("delete");
    }
  });

  renderList();
}
