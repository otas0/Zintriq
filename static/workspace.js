(() => {
  const root = document.getElementById('workspace');
  if (!root || !window.WORKSPACE_BOOT) return;

  const csrf = root.dataset.csrf;
  const mode = root.dataset.mode;
  const focusGroupId = root.dataset.focusGroup ? Number(root.dataset.focusGroup) : null;

  let state = {
    stores: WORKSPACE_BOOT.stores || [],
    groups: WORKSPACE_BOOT.groups || [],
    labels: WORKSPACE_BOOT.labels || [],
    view: mode === 'group' ? 'group' : 'all',
    groupId: focusGroupId,
    labelIds: [],
    search: '',
    selected: new Set(),
    drawerStoreId: null,
    contextStoreId: null,
  };

  const els = {
    storeList: document.getElementById('store-list'),
    search: document.getElementById('workspace-search'),
    selectAll: document.getElementById('workspace-select-all'),
    actionBar: document.getElementById('action-bar'),
    actionBarCount: document.getElementById('action-bar-count'),
    empty: document.getElementById('workspace-empty'),
    activeFilters: document.getElementById('active-filters'),
    drawer: document.getElementById('store-drawer'),
    drawerBody: document.getElementById('drawer-body'),
    drawerTitle: document.getElementById('drawer-title'),
    drawerClose: document.getElementById('drawer-close'),
    popover: document.getElementById('workspace-popover'),
    popoverTitle: document.getElementById('popover-title'),
    popoverBody: document.getElementById('popover-body'),
    contextMenu: document.getElementById('context-menu'),
    toast: document.getElementById('workspace-toast'),
    actionBarManage: document.getElementById('action-bar-manage'),
    actionBarMoreBtn: document.getElementById('action-bar-more-btn'),
    actionBarMoreMenu: document.getElementById('action-bar-more-menu'),
    actionBarClear: document.getElementById('action-bar-clear'),
    statusFilters: document.getElementById('workspace-status-filters'),
  };

  const api = async (payload) => {
    const response = await fetch('/api/workspace/batch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify({ ...payload, csrf_token: csrf }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
  };

  const toast = (message) => {
    els.toast.textContent = message;
    els.toast.classList.remove('hidden');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => els.toast.classList.add('hidden'), 2400);
  };

  const syncBoot = (data) => {
    state.stores = data.stores;
    state.groups = data.groups;
    state.labels = data.labels;
    render();
  };

  const storeHaystack = (store) => {
    return [
      store.name,
      store.description,
      store.group_name,
      store.address,
      store.status,
      store.qr_names,
      ...(store.labels || []).map((l) => l.name),
    ].filter(Boolean).join(' ').toLowerCase();
  };

  const filteredStores = () => {
    let list = [...state.stores];
    if (state.view === 'active') list = list.filter((s) => s.status === 'active');
    if (state.view === 'archived') list = list.filter((s) => s.status === 'archived');
    if (state.view === 'ungrouped') list = list.filter((s) => !s.group_id);
    if (state.view === 'recent') list = list.sort((a, b) => String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at)));
    if (state.view === 'group' && state.groupId) list = list.filter((s) => s.group_id === state.groupId);
    if (state.groupId && state.view !== 'group') list = list.filter((s) => s.group_id === state.groupId);
    if (state.labelIds.length) {
      list = list.filter((s) => state.labelIds.every((id) => (s.labels || []).some((l) => l.id === id)));
    }
    if (state.search.trim()) {
      const q = state.search.trim().toLowerCase();
      const tokens = q.split(/\s+/);
      list = list.filter((s) => tokens.every((token) => storeHaystack(s).includes(token)));
    }
    return list;
  };

  const rowMetaLine = (store) => {
    const parts = [store.status, `${store.item_count || 0} items`];
    const labels = store.labels || [];
    labels.slice(0, 2).forEach((label) => parts.push(label.name));
    if (labels.length > 2) parts.push(`+${labels.length - 2}`);
    return parts.join(' · ');
  };

  const contextMenuOpen = () => !els.contextMenu.classList.contains('hidden');

  const hideActionBarMore = () => {
    els.actionBarMoreMenu?.classList.add('hidden');
    els.actionBarMoreBtn?.setAttribute('aria-expanded', 'false');
  };

  const updateSelectionUI = () => {
    const count = state.selected.size;
    const showBar = count > 0 && !contextMenuOpen();
    els.actionBar.classList.toggle('hidden', !showBar);
    els.actionBarCount.textContent = `${count} store${count === 1 ? '' : 's'} selected`;
    document.body.classList.toggle('has-action-bar', showBar);
    if (els.actionBarManage) {
      if (count === 1) {
        const store = state.stores.find((s) => s.id === [...state.selected][0]);
        els.actionBarManage.href = store?.manage_url || '#';
        els.actionBarManage.classList.remove('hidden');
      } else {
        els.actionBarManage.classList.add('hidden');
      }
    }
    if (!showBar) hideActionBarMore();
  };

  const renderFilters = () => {
    const chips = [];
    if (state.view !== 'all' && state.view !== 'group') chips.push({ type: 'view', label: state.view });
    if (state.view === 'group' && state.groupId) {
      const group = state.groups.find((g) => g.id === state.groupId);
      if (group) chips.push({ type: 'group', label: group.name });
    }
    state.labelIds.forEach((id) => {
      const label = state.labels.find((l) => l.id === id);
      if (label) chips.push({ type: 'label', id, label: label.name });
    });
    if (state.search) chips.push({ type: 'search', label: `"${state.search}"` });
    els.activeFilters.innerHTML = chips.map((chip) => `
      <button type="button" class="chip active" data-clear="${chip.type}" data-id="${chip.id || ''}">${escapeHtml(chip.label)} ×</button>
    `).join('');
  };

  const renderStores = () => {
    const list = filteredStores();
    els.empty.classList.toggle('hidden', list.length > 0);
    els.storeList.innerHTML = list.map((store) => `
      <article class="workspace-row workspace-row--slim${state.selected.has(store.id) ? ' selected' : ''}"
               data-store-id="${store.id}"
               data-manage-url="${escapeAttr(store.manage_url || '')}">
        <label class="checkbox-label row-check" onclick="event.stopPropagation()">
          <input type="checkbox" class="store-select" data-id="${store.id}" ${state.selected.has(store.id) ? 'checked' : ''}>
        </label>
        <div class="item-icon">${escapeHtml(store.name[0]?.toUpperCase() || '?')}</div>
        <div class="workspace-row-main">
          <div class="workspace-row-title">
            <span class="workspace-row-name">${escapeHtml(store.name)}</span>
          </div>
          <p class="workspace-row-desc">${escapeHtml(store.description || 'No description')}</p>
          <p class="workspace-row-meta">${escapeHtml(rowMetaLine(store))}</p>
        </div>
        <button type="button" class="workspace-row-menu" data-store-menu="${store.id}" aria-label="Store actions">⋯</button>
      </article>
    `).join('');
    updateSelectionUI();
  };

  const renderDrawer = () => {
    const store = state.stores.find((s) => s.id === state.drawerStoreId);
    if (!store) return;
    els.drawerTitle.textContent = store.name;
    els.drawerBody.innerHTML = `
      <dl class="meta-list">
        <div><dt>Status</dt><dd><span class="tag tag-${store.status}">${store.status}</span></dd></div>
        <div><dt>Group</dt><dd>${escapeHtml(store.group_name || '—')}</dd></div>
        <div><dt>Labels</dt><dd>${(store.labels || []).map((l) => l.name).join(', ') || '—'}</dd></div>
        <div><dt>Items</dt><dd>${store.item_count || 0}</dd></div>
        <div><dt>Address</dt><dd>${escapeHtml(store.address || '—')}</dd></div>
        <div><dt>Contact</dt><dd>${escapeHtml(store.contact || '—')}</dd></div>
        <div><dt>QR codes</dt><dd>${escapeHtml(store.qr_names || '—')}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(store.updated_at || store.created_at || '—')}</dd></div>
      </dl>
      <div class="drawer-actions">
        <a class="button" href="${store.manage_url}">Manage store <span>→</span></a>
        <button type="button" class="outline" data-drawer-preview="${store.id}">Customer preview</button>
      </div>
    `;
  };

  const render = () => {
    renderFilters();
    renderStores();
    if (state.drawerStoreId) renderDrawer();
    document.querySelectorAll('#workspace-status-filters .workspace-status-chip').forEach((btn) => {
      const active = btn.dataset.view === state.view && state.labelIds.length === 0;
      btn.classList.toggle('active', active);
    });
  };

  const escapeHtml = (value) => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const escapeAttr = (value) => escapeHtml(value).replace(/"/g, '&quot;');

  const batch = async (action, extra = {}) => {
    const store_ids = [...state.selected];
    if (!store_ids.length && !['create_group', 'create_label', 'rename_group', 'delete_group', 'rename_label', 'delete_label'].includes(action)) {
      toast('Select at least one store.');
      return;
    }
    if (action === 'delete' && !window.confirm(`Permanently delete ${store_ids.length} store(s)?`)) return;
    try {
      const data = await api({ action, store_ids, ...extra });
      if (action === 'export') {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `marketqr-stores-${Date.now()}.json`;
        link.click();
        toast(`Exported ${store_ids.length} store(s).`);
        return;
      }
      state.selected.clear();
      syncBoot(data);
      toast('Done.');
      if (action === 'delete_group') window.location.href = '/app/store/organize';
    } catch (error) {
      toast(error.message);
    }
  };

  const showPopover = (kind, anchor) => {
    els.popover.classList.remove('hidden');
    const rect = anchor.getBoundingClientRect();
    els.popover.style.top = `${Math.min(rect.top, window.innerHeight - 280)}px`;
    els.popover.style.left = `${Math.min(rect.left, window.innerWidth - 280)}px`;
    if (kind === 'move-group') {
      els.popoverTitle.textContent = 'Move to group';
      els.popoverBody.innerHTML = `
        <div class="popover-list">
          <button type="button" class="popover-item" data-move-group="">No group</button>
          ${state.groups.map((g) => `<button type="button" class="popover-item" data-move-group="${g.id}">${escapeHtml(g.name)}</button>`).join('')}
          <button type="button" class="popover-item popover-create" data-create-group-inline>+ Create new group</button>
          <a class="popover-item" href="/app/store/organize">Manage groups &amp; labels</a>
        </div>
      `;
    } else if (kind === 'labels') {
      els.popoverTitle.textContent = 'Add labels';
      const selectedStores = state.stores.filter((s) => state.selected.has(s.id));
      const assignedLabelIds = new Set(
        selectedStores.flatMap((s) => (s.labels || []).map((l) => l.id))
      );
      els.popoverBody.innerHTML = `
        <div class="popover-list">
          ${state.labels.length ? state.labels.map((l) => `
            <label class="popover-check">
              <input type="checkbox" value="${l.id}"${assignedLabelIds.has(l.id) ? ' checked' : ''}>
              <span class="popover-check-label">${escapeHtml(l.name)}</span>
            </label>
          `).join('') : '<p class="tiny popover-empty">No labels yet. Create one below.</p>'}
          <button type="button" class="popover-item popover-create" data-create-label-inline>+ Create new label</button>
          <a class="popover-item" href="/app/store/organize">Manage groups &amp; labels</a>
          <button type="button" class="button small" data-apply-labels>Add selected labels</button>
          <button type="button" class="outline small" data-remove-labels>Remove selected labels</button>
        </div>
      `;
    }
  };

  const hidePopover = () => els.popover.classList.add('hidden');

  const hideContextMenu = () => {
    els.contextMenu.classList.add('hidden');
    state.contextStoreId = null;
    updateSelectionUI();
  };

  const positionFloatingMenu = (menu, x, y) => {
    menu.classList.remove('hidden');
    const pad = 8;
    const rect = menu.getBoundingClientRect();
    let left = x;
    let top = y;
    if (left + rect.width > window.innerWidth - pad) left = window.innerWidth - rect.width - pad;
    if (top + rect.height > window.innerHeight - pad) top = window.innerHeight - rect.height - pad;
    menu.style.left = `${Math.max(pad, left)}px`;
    menu.style.top = `${Math.max(pad, top)}px`;
  };

  const storeMenuHtml = () => `
    <button type="button" data-context="details">Store details</button>
    <button type="button" data-context="manage">Manage store</button>
    <button type="button" data-context="customer-qr">Customer QR</button>
    <button type="button" data-context="duplicate">Duplicate</button>
    <button type="button" data-context="archive">Archive</button>
  `;

  const showStoreMenu = (storeId, x, y) => {
    hideActionBarMore();
    hidePopover();
    state.contextStoreId = storeId;
    els.contextMenu.innerHTML = storeMenuHtml();
    els.contextMenu.style.top = '0';
    els.contextMenu.style.left = '0';
    positionFloatingMenu(els.contextMenu, x, y);
    updateSelectionUI();
  };

  const runContextAction = async (action, storeId) => {
    const store = state.stores.find((s) => s.id === storeId);
    if (!store) return;
    if (action === 'details') {
      hideContextMenu();
      openDrawer(storeId);
      return;
    }
    if (action === 'manage') {
      window.location.href = store.manage_url;
      return;
    }
    if (action === 'customer-qr') {
      window.location.href = `/manage/${encodeURIComponent(store.slug)}/qr`;
      return;
    }
    state.selected = new Set([storeId]);
    updateSelectionUI();
    await batch(action === 'duplicate' ? 'duplicate' : 'archive');
  };

  const openDrawer = (storeId) => {
    state.drawerStoreId = storeId;
    els.drawer.classList.remove('hidden');
    els.drawer.setAttribute('aria-hidden', 'false');
    renderDrawer();
  };

  const closeDrawer = () => {
    state.drawerStoreId = null;
    els.drawer.classList.add('hidden');
    els.drawer.setAttribute('aria-hidden', 'true');
  };

  els.search?.addEventListener('input', (event) => {
    state.search = event.target.value;
    renderFilters();
    renderStores();
  });

  els.selectAll?.addEventListener('change', (event) => {
    const list = filteredStores();
    if (event.target.checked) list.forEach((s) => state.selected.add(s.id));
    else state.selected.clear();
    renderStores();
  });

  els.statusFilters?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-view]');
    if (!btn) return;
    state.view = btn.dataset.view;
    if (state.view !== 'group') state.groupId = null;
    state.labelIds = [];
    render();
  });

  els.activeFilters?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-clear]');
    if (!btn) return;
    const type = btn.dataset.clear;
    if (type === 'view') state.view = 'all';
    if (type === 'group') {
      state.groupId = null;
      state.view = 'all';
    }
    if (type === 'label') state.labelIds = state.labelIds.filter((id) => id !== Number(btn.dataset.id));
    if (type === 'search') { state.search = ''; els.search.value = ''; }
    render();
  });

  els.storeList?.addEventListener('click', (event) => {
    const menuBtn = event.target.closest('.workspace-row-menu');
    if (menuBtn) {
      event.preventDefault();
      event.stopPropagation();
      const rect = menuBtn.getBoundingClientRect();
      showStoreMenu(Number(menuBtn.dataset.storeMenu), rect.right - 180, rect.bottom + 4);
      return;
    }
    if (event.target.closest('.row-check')) return;
    const row = event.target.closest('[data-store-id]');
    if (!row || event.target.closest('a, button, input, label')) return;
    const url = row.dataset.manageUrl;
    if (url) window.location.href = url;
  });

  els.storeList?.addEventListener('change', (event) => {
    if (!event.target.matches('.store-select')) return;
    const id = Number(event.target.dataset.id);
    if (event.target.checked) state.selected.add(id);
    else state.selected.delete(id);
    updateSelectionUI();
    event.target.closest('.workspace-row')?.classList.toggle('selected', event.target.checked);
  });

  els.storeList?.addEventListener('contextmenu', (event) => {
    const row = event.target.closest('[data-store-id]');
    if (!row) return;
    event.preventDefault();
    showStoreMenu(Number(row.dataset.storeId), event.clientX, event.clientY);
  });

  els.actionBar?.addEventListener('click', (event) => {
    if (event.target.closest('#action-bar-more-btn')) {
      const open = els.actionBarMoreMenu?.classList.toggle('hidden');
      els.actionBarMoreBtn?.setAttribute('aria-expanded', open ? 'false' : 'true');
      return;
    }
    const batchBtn = event.target.closest('[data-batch]');
    if (batchBtn) {
      hideActionBarMore();
      batch(batchBtn.dataset.batch);
      return;
    }
    const popBtn = event.target.closest('[data-popover]');
    if (popBtn) {
      hideActionBarMore();
      showPopover(popBtn.dataset.popover, popBtn);
    }
  });

  els.contextMenu?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-context]');
    if (!btn) return;
    const storeId = state.contextStoreId;
    hideContextMenu();
    runContextAction(btn.dataset.context, storeId);
  });

  els.actionBarClear?.addEventListener('click', () => {
    state.selected.clear();
    hideContextMenu();
    hideActionBarMore();
    renderStores();
  });

  els.popover?.addEventListener('click', async (event) => {
    const moveBtn = event.target.closest('[data-move-group]');
    if (moveBtn) {
      hidePopover();
      await batch('move_group', { group_id: moveBtn.dataset.moveGroup || null });
      return;
    }
    if (event.target.closest('[data-create-group-inline]')) {
      const name = window.prompt('New group name');
      if (name) { hidePopover(); await batch('create_group', { name }); }
      return;
    }
    if (event.target.closest('[data-create-label-inline]')) {
      const name = window.prompt('New label name');
      if (name) { hidePopover(); await batch('create_label', { name }); }
      return;
    }
    if (event.target.closest('[data-apply-labels]')) {
      const label_ids = [...els.popoverBody.querySelectorAll('input:checked')].map((el) => Number(el.value));
      hidePopover();
      await batch('add_labels', { label_ids });
      return;
    }
    if (event.target.closest('[data-remove-labels]')) {
      const label_ids = [...els.popoverBody.querySelectorAll('input:checked')].map((el) => Number(el.value));
      hidePopover();
      await batch('remove_labels', { label_ids });
    }
  });

  els.drawerClose?.addEventListener('click', closeDrawer);
  els.drawer?.addEventListener('click', (event) => {
    const preview = event.target.closest('[data-drawer-preview]');
    if (preview) {
      const store = state.stores.find((s) => s.id === Number(preview.dataset.drawerPreview));
      if (store) window.open(`/manage/${store.slug}/preview`, '_blank');
    }
  });

  document.getElementById('rename-group-btn')?.addEventListener('click', async (event) => {
    const groupId = event.currentTarget.dataset.groupId;
    const name = window.prompt('Rename group', document.getElementById('group-page-title')?.textContent || '');
    if (!name) return;
    try {
      const data = await api({ action: 'rename_group', group_id: Number(groupId), name, store_ids: [] });
      syncBoot(data);
      const title = document.getElementById('group-page-title');
      if (title) title.textContent = name;
      toast('Group renamed.');
    } catch (error) { toast(error.message); }
  });

  document.getElementById('delete-group-btn')?.addEventListener('click', async (event) => {
    const groupId = Number(event.currentTarget.dataset.groupId);
    if (!window.confirm('Delete this group? Stores will become ungrouped.')) return;
    try {
      await api({ action: 'delete_group', group_id: groupId, store_ids: [] });
      window.location.href = '/app/store/organize';
    } catch (error) { toast(error.message); }
  });

  document.addEventListener('click', (event) => {
    if (!els.popover.contains(event.target) && !event.target.closest('[data-popover]')) hidePopover();
    if (!els.contextMenu.contains(event.target)) hideContextMenu();
    if (
      els.actionBarMoreMenu
      && !els.actionBarMoreMenu.contains(event.target)
      && !event.target.closest('#action-bar-more-btn')
    ) {
      hideActionBarMore();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      hideContextMenu();
      hideActionBarMore();
      hidePopover();
      closeDrawer();
    }
  });

  const labelQuery = new URLSearchParams(window.location.search).get('label');
  if (labelQuery && /^\d+$/.test(labelQuery)) {
    state.labelIds = [Number(labelQuery)];
  }

  if (mode === 'group' && focusGroupId) {
    state.view = 'group';
    state.groupId = focusGroupId;
  }

  render();
})();
