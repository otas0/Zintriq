/**
 * Zintriq Studio project dashboard (composition home).
 */
(function () {
  'use strict';

  const API_BASE = '/api/builder-core/projects';
  const boot = window.STUDIO_BOOT || {};
  const studioBase = (boot.basePath || document.querySelector('[data-studio-base]')?.dataset.studioBase || '/studio').replace(/\/$/, '') || '/studio';
  const editorPath = (id) => `${studioBase}/p/${id}`;
  const homePath = () => studioBase;

  // DOM Elements
  const grid = document.getElementById('zw-project-grid');
  const emptyState = document.getElementById('zw-empty');
  const viewTitle = document.getElementById('zw-view-title');
  const sortBtn = document.getElementById('zw-sort-btn');
  const sortMenu = document.getElementById('zw-sort-menu');
  const sortLabel = document.getElementById('zw-sort-label');
  const newProjectBtn = document.getElementById('zw-new-project');
  const modal = document.getElementById('zw-modal');
  const modalBackdrop = document.getElementById('zw-modal-backdrop');
  const modalClose = document.getElementById('zw-modal-close');
  const modalCancel = document.getElementById('zw-modal-cancel');
  const createForm = document.getElementById('zw-create-form');
  const emptyCreateBtn = document.getElementById('zw-empty-create');
  const navItems = document.querySelectorAll('.zw-nav-item--view');
  const actionItems = document.querySelectorAll('.zw-nav-item--action');
  const searchInput = document.getElementById('zw-search');

  let currentView = 'all';
  let currentSort = 'viewed';
  let projects = [];

  // Initialize
  async function init() {
    const params = new URLSearchParams(window.location.search);
    const viewParam = params.get('view');
    if (viewParam && ['all', 'recent', 'favorites', 'archived'].includes(viewParam)) {
      currentView = viewParam;
      navItems.forEach(i => i.classList.remove('zw-nav-item--active'));
      const activeItem = document.querySelector(`.zw-nav-item--view[data-view="${viewParam}"]`);
      if (activeItem) activeItem.classList.add('zw-nav-item--active');
      if (viewTitle) viewTitle.textContent = getViewTitle(currentView);
    }

    await loadProjects();
    renderProjects();
    if (boot.desktopMode) {
      await loadLocalMeta();
    }
    bindEvents();
    bindSiteImport();

    const actionParam = params.get('action');
    if (actionParam === 'new-composition' || actionParam === 'new-website' || actionParam === 'new-app' || actionParam === 'new-store') {
      openModal('composition');
    }

    const installPackage = (params.get('install') || '').trim();
    if (installPackage) {
      handlePendingInstall(installPackage);
    }
  }

  function clearInstallQuery() {
    window.history.replaceState({}, '', homePath());
  }

  function showInstallDialog(packageId, candidates) {
    return new Promise((resolve) => {
      const existing = document.getElementById('zw-install-modal');
      if (existing) existing.remove();

      const wrap = document.createElement('div');
      wrap.id = 'zw-install-modal';
      wrap.className = 'zw-modal';
      wrap.innerHTML = `
        <div class="zw-modal__backdrop" data-install-cancel></div>
        <div class="zw-modal__content" role="dialog" aria-modal="true" aria-labelledby="zw-install-title">
          <div class="zw-modal__header">
            <div>
              <span class="zw-modal__eyebrow">Community → Studio</span>
              <h2 class="zw-modal__title" id="zw-install-title">Install package</h2>
            </div>
            <button type="button" class="zw-modal__close" data-install-cancel aria-label="Close">×</button>
          </div>
          <p class="zw-form-hint" style="margin:0 0 16px">Choose which composition receives <code>${escapeHtml(packageId)}</code>. Install runs in Studio.</p>
          <div class="zw-form-group">
            <label class="zw-label" for="zw-install-project">Composition</label>
            <select id="zw-install-project" class="zw-input">
              ${candidates.map((p, i) => `<option value="${p.id}" ${i === 0 ? 'selected' : ''}>${escapeHtml(p.name || ('Composition ' + p.id))}</option>`).join('')}
            </select>
          </div>
          <p class="zw-install-error" id="zw-install-error" hidden style="color:#b42318;margin:0 0 12px"></p>
          <div class="zw-modal__actions">
            <button type="button" class="zw-btn zw-btn--secondary" data-install-cancel>Cancel</button>
            <button type="button" class="zw-btn zw-btn--primary" id="zw-install-confirm">Install into composition</button>
          </div>
        </div>`;
      document.body.appendChild(wrap);

      const close = (value) => {
        wrap.remove();
        resolve(value);
      };
      wrap.querySelectorAll('[data-install-cancel]').forEach((el) => {
        el.addEventListener('click', () => close(null));
      });
      wrap.querySelector('#zw-install-confirm')?.addEventListener('click', async () => {
        const select = wrap.querySelector('#zw-install-project');
        const err = wrap.querySelector('#zw-install-error');
        const btn = wrap.querySelector('#zw-install-confirm');
        const projectId = Number(select?.value);
        if (!projectId) return;
        btn.disabled = true;
        btn.textContent = 'Installing…';
        if (err) err.hidden = true;
        try {
          const res = await fetch(
            `/api/marketplace/projects/${projectId}/packages/${encodeURIComponent(packageId)}/install`,
            {
              method: 'POST',
              headers: studioHeaders({ 'Content-Type': 'application/json' }),
              body: JSON.stringify({ csrf_token: getCsrfToken() }),
              credentials: 'same-origin',
            }
          );
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || data.message || 'Install failed');
          close(projectId);
        } catch (e) {
          btn.disabled = false;
          btn.textContent = 'Install into composition';
          if (err) {
            err.hidden = false;
            err.textContent = e.message || 'Install failed';
          }
        }
      });
    });
  }

  async function handlePendingInstall(packageId) {
    const candidates = projects.filter((p) => p.status !== 'archived');
    if (!candidates.length) {
      showInstallEmptyHint();
      clearInstallQuery();
      return;
    }
    const projectId = await showInstallDialog(packageId, candidates);
    if (!projectId) {
      clearInstallQuery();
      return;
    }
    window.location.href = editorPath(projectId);
  }

  function showInstallEmptyHint() {
    const wrap = document.createElement('div');
    wrap.className = 'zw-modal';
    wrap.innerHTML = `
      <div class="zw-modal__backdrop" data-close></div>
      <div class="zw-modal__content" role="dialog" aria-modal="true">
        <div class="zw-modal__header">
          <div>
            <span class="zw-modal__eyebrow">Community → Studio</span>
            <h2 class="zw-modal__title">Create a composition first</h2>
          </div>
          <button type="button" class="zw-modal__close" data-close aria-label="Close">×</button>
        </div>
        <p class="zw-form-hint">This package needs a composition to land in. Create one, then import again from Community.</p>
        <div class="zw-modal__actions">
          <button type="button" class="zw-btn zw-btn--secondary" data-close>Close</button>
          <button type="button" class="zw-btn zw-btn--primary" id="zw-install-create">New composition</button>
        </div>
      </div>`;
    document.body.appendChild(wrap);
    const dismiss = () => wrap.remove();
    wrap.querySelectorAll('[data-close]').forEach((el) => el.addEventListener('click', dismiss));
    wrap.querySelector('#zw-install-create')?.addEventListener('click', () => {
      dismiss();
      openModal('composition');
    });
  }

  // Load projects from API
  async function loadProjects() {
    try {
      const res = await fetch(API_BASE, { headers: studioHeaders(), credentials: 'same-origin' });
      if (!res.ok) throw new Error('Failed to load projects');
      const data = await res.json();
      projects = data.projects || [];
    } catch (err) {
      console.error('Error loading projects:', err);
      projects = [];
    }
  }

  // Filter and sort projects
  function getFilteredProjects() {
    let filtered = [...projects];
    const query = (searchInput?.value || '').trim().toLowerCase();

    if (currentView === 'recent') {
      const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
      filtered = filtered.filter(p => {
        const ts = new Date(p.updated_at || p.created_at || 0).getTime();
        return Number.isFinite(ts) && ts > sevenDaysAgo;
      });
    } else if (currentView === 'favorites') {
      filtered = filtered.filter(p => p.is_favorite || p.settings?.is_favorite);
    } else if (currentView === 'archived') {
      filtered = filtered.filter(p => p.status === 'archived');
    } else {
      filtered = filtered.filter(p => p.status !== 'archived');
    }

    if (query) {
      filtered = filtered.filter(p => (p.name || '').toLowerCase().includes(query));
    }

    if (currentSort === 'modified') {
      filtered.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
    } else if (currentSort === 'created') {
      filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    } else if (currentSort === 'name') {
      filtered.sort((a, b) => a.name.localeCompare(b.name));
    } else {
      filtered.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
    }

    return filtered;
  }

  function updateEmptyState(view, hasResults, searching) {
    if (!emptyState) return;
    const title = emptyState.querySelector('.zw-empty__title');
    const text = emptyState.querySelector('.zw-empty__text');
    const createBtn = emptyState.querySelector('#zw-empty-create');
    if (hasResults) {
      emptyState.classList.add('hidden');
      emptyState.setAttribute('aria-hidden', 'true');
      emptyState.setAttribute('hidden', '');
      return;
    }
    emptyState.classList.remove('hidden');
    emptyState.removeAttribute('aria-hidden');
    emptyState.removeAttribute('hidden');
    if (searching) {
      if (title) title.textContent = 'No compositions found';
      if (text) text.textContent = 'Try a different search term.';
      if (createBtn) createBtn.classList.add('hidden');
      return;
    }
    const copy = {
      favorites: {
        title: 'No starred compositions',
        text: 'Star a composition card to pin it here.',
        showCreate: false,
      },
      archived: {
        title: 'Archive is empty',
        text: 'Archive a composition from its card. Active work stays under Compositions.',
        showCreate: false,
      },
      recent: {
        title: 'No recent compositions',
        text: 'Compositions updated in the last 7 days appear here.',
        showCreate: true,
      },
      all: {
        title: 'No compositions yet',
        text: 'Start a blank composition — build with Data, Interface, Logic, Connection, and Publish. Community packages import later.',
        showCreate: true,
      },
    }[view] || {
      title: 'No compositions yet',
      text: 'Start a blank composition — build with Data, Interface, Logic, Connection, and Publish. Community packages import later.',
      showCreate: true,
    };
    if (title) title.textContent = copy.title;
    if (text) text.textContent = copy.text;
    if (createBtn) createBtn.classList.toggle('hidden', !copy.showCreate);
  }

  // Render projects
  function renderProjects() {
    const filtered = getFilteredProjects();
    const searching = !!(searchInput?.value || '').trim();

    if (filtered.length === 0) {
      grid.innerHTML = '';
      grid.classList.add('hidden');
      updateEmptyState(currentView, false, searching);
      return;
    }

    grid.classList.remove('hidden');
    updateEmptyState(currentView, true, searching);

    grid.innerHTML = filtered.map(project => {
      const status = project.status || 'draft';
      const updated = formatRelativeTime(project.updated_at);
      const favorited = !!(project.is_favorite || project.settings?.is_favorite);
      const badge = compositionBadge(project);

      return `
        <article class="zw-project-card zw-composition-card" data-project-id="${project.id}">
          <div class="zw-project-card__preview">
            <div class="zw-composition-card__primitives" aria-hidden="true">
              <span>D</span><span>I</span><span>L</span><span>C</span><span>P</span>
            </div>
            <span class="zw-project-card__type-badge">${escapeHtml(badge)}</span>
          </div>
          <div class="zw-project-card__body">
            <div class="zw-project-card__header">
              <h3 class="zw-project-card__name">${escapeHtml(project.name)}</h3>
              <div class="zw-project-card__actions">
                <button type="button" class="zw-project-card__icon-btn" data-action="favorite" aria-label="${favorited ? 'Unstar' : 'Star'}" title="${favorited ? 'Unstar' : 'Star'}">
                  ${favorited ? '★' : '☆'}
                </button>
                <button type="button" class="zw-project-card__icon-btn" data-action="archive" aria-label="${status === 'archived' ? 'Restore' : 'Archive'}" title="${status === 'archived' ? 'Restore' : 'Archive'}">
                  ${status === 'archived' ? '⤴' : '▤'}
                </button>
                ${window.STUDIO_BOOT && window.STUDIO_BOOT.desktopMode ? `<button type="button" class="zw-project-card__icon-btn" data-action="export" aria-label="导出" title="导出">↗</button>` : ''}
              </div>
            </div>
            <div class="zw-project-card__meta">
              <span class="zw-project-card__status zw-project-card__status--${escapeHtml(status)}">${escapeHtml(status)}</span>
              <span>${updated}</span>
            </div>
          </div>
        </article>
      `;
    }).join('');

    grid.querySelectorAll('.zw-project-card').forEach(card => {
      card.addEventListener('click', (e) => {
        const actionBtn = e.target.closest('[data-action]');
        if (actionBtn) {
          e.preventDefault();
          e.stopPropagation();
          handleCardAction(card.dataset.projectId, actionBtn.dataset.action);
          return;
        }
        window.location.href = editorPath(card.dataset.projectId);
      });
    });
  }

  async function handleCardAction(projectId, action) {
    const project = projects.find(p => String(p.id) === String(projectId));
    if (!project) return;
    const body = {};
    if (action === 'favorite') {
      body.is_favorite = !(project.is_favorite || project.settings?.is_favorite);
    } else if (action === 'archive') {
      body.status = project.status === 'archived' ? 'active' : 'archived';
    } else if (action === 'export') {
      if (window.zintriqProjectTransfer) window.zintriqProjectTransfer.exportProject(project);
      return;
    } else {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/${projectId}`, {
        method: 'PATCH',
        headers: studioHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ ...body, csrf_token: getCsrfToken() }),
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error('Update failed');
      const updated = await res.json();
      projects = projects.map(p => (String(p.id) === String(projectId) ? { ...p, ...updated } : p));
      renderProjects();
    } catch (err) {
      console.error(err);
      alert('Could not update composition. Please try again.');
    }
  }

  // Theme — handled by zintriq-shell.js on all workspace pages
  function bindEvents() {
    navItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        navItems.forEach(i => i.classList.remove('zw-nav-item--active'));
        item.classList.add('zw-nav-item--active');
        currentView = item.dataset.view;
        viewTitle.textContent = getViewTitle(currentView);
        renderProjects();
        history.replaceState(null, '', item.getAttribute('href'));
      });
    });

    actionItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const action = item.dataset.action;
        if (action === 'new-composition' || action === 'new-website' || action === 'new-app' || action === 'new-store') {
          openModal('composition');
        } else if (action) {
          openModal('composition');
        }
      });
    });

    if (sortBtn) {
      sortBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sortMenu.classList.toggle('hidden');
      });
    }

    document.addEventListener('click', () => {
      if (sortMenu) sortMenu.classList.add('hidden');
    });

    if (sortMenu) {
      sortMenu.addEventListener('click', (e) => e.stopPropagation());
    }

    sortMenu?.querySelectorAll('.zw-dropdown__item').forEach(item => {
      item.addEventListener('click', () => {
        sortMenu.querySelectorAll('.zw-dropdown__item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        currentSort = item.dataset.sort;
        sortLabel.textContent = item.textContent;
        sortMenu.classList.add('hidden');
        renderProjects();
      });
    });

    if (newProjectBtn) {
      newProjectBtn.addEventListener('click', () => openModal());
    }

    if (emptyCreateBtn) {
      emptyCreateBtn.addEventListener('click', () => openModal());
    }

    if (modalClose) modalClose.addEventListener('click', closeModal);
    if (modalCancel) modalCancel.addEventListener('click', closeModal);
    if (modalBackdrop) modalBackdrop.addEventListener('click', closeModal);

    if (createForm) {
      createForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await createProject();
      });
    }

    if (searchInput) {
      searchInput.addEventListener('input', () => {
        renderProjects();
      });
    }
  }

  function openModal(defaultType) {
    modal.classList.remove('hidden');
    createForm.reset();
    const type = defaultType === 'from-community' ? 'from-community' : 'composition';
    const radio = createForm.querySelector(`input[name="type"][value="${type}"]`);
    if (radio) radio.checked = true;
    const nameInput = document.getElementById('zw-create-name');
    if (nameInput) nameInput.focus();
  }

  function closeModal() {
    modal.classList.add('hidden');
  }

  async function createProject() {
    const formData = new FormData(createForm);
    const name = formData.get('name');
    const type = formData.get('type') || 'composition';

    if (!name) return;

    try {
      const res = await fetch(API_BASE, {
        method: 'POST',
        headers: studioHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          name: name,
          kind: 'composition',
          starter: 'Composition',
          csrf_token: getCsrfToken(),
        }),
        credentials: 'same-origin',
      });

      if (!res.ok) throw new Error('Failed to create composition');

      const data = await res.json();
      if (type === 'from-community') {
        closeModal();
        window.location.assign(boot.communityUrl || '/app/community');
        return;
      }
      closeModal();
      await loadProjects();
      renderProjects();

      if (data.id) {
        window.location.href = editorPath(data.id);
      }
    } catch (err) {
      console.error('Error creating composition:', err);
      alert('Failed to create composition. Please try again.');
    }
  }

  function getViewTitle(view) {
    const titles = {
      all: 'Compositions',
      recent: 'Recent',
      favorites: 'Starred',
      archived: 'Archive',
    };
    return titles[view] || 'Compositions';
  }

  function compositionBadge(project) {
    const kind = String(project.kind || 'composition').toLowerCase();
    if (kind === 'website' || kind === 'app' || kind === 'store' || kind === 'application') {
      return 'Composition';
    }
    return kind === 'composition' ? 'Composition' : capitalize(kind);
  }

  function formatRelativeTime(dateStr) {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);

    if (months > 0) return `${months}mo ago`;
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return 'Just now';
  }

  async function loadLocalMeta() {
    const draftList = document.getElementById('zw-draft-list');
    const artifactList = document.getElementById('zw-artifact-list');
    if (!draftList || !artifactList) return;
    try {
      const res = await fetch('/api/builder-core/meta/index', {
        headers: studioHeaders(),
        credentials: 'same-origin',
      });
      if (!res.ok) return;
      const data = await res.json();
      renderLocalList(draftList, data.drafts || [], function (item) {
        return `<a href="${studioBase}/meta/${encodeURIComponent(item.slug)}">${escapeHtml(item.slug)}</a>` +
          (item.updated_at ? `<span>${escapeHtml(item.updated_at)}</span>` : '');
      }, 'No drafts yet');
      renderLocalList(artifactList, data.artifacts || [], function (item) {
        const url = item.public_url || `/build/${item.slug}`;
        return `<a href="${escapeHtml(url)}/home">${escapeHtml(item.slug)}</a>` +
          ` <a href="${studioBase}/meta/${encodeURIComponent(item.slug)}">Edit</a>` +
          ` <a href="/api/builder-core/meta/sites/${encodeURIComponent(item.slug)}/zip">Zip</a>`;
      }, 'No /build pages yet');
    } catch (err) {
      console.error('Local meta index failed', err);
    }
  }

  function renderLocalList(listEl, rows, rowHtml, emptyText) {
    if (!rows.length) {
      listEl.innerHTML = `<li class="zw-local-meta__empty">${emptyText}</li>`;
      return;
    }
    listEl.innerHTML = rows.map(function (item) {
      return `<li>${rowHtml(item)}</li>`;
    }).join('');
  }

  function bindSiteImport() {
    const input = document.getElementById('zw-import-site');
    if (!input) return;
    input.addEventListener('change', async function () {
      const file = input.files && input.files[0];
      input.value = '';
      if (!file) return;
      const body = new FormData();
      body.append('site', file);
      body.append('csrf_token', getCsrfToken());
      try {
        const res = await fetch('/api/builder-core/meta/sites/import', {
          method: 'POST',
          headers: studioHeaders(),
          credentials: 'same-origin',
          body: body,
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok) {
          alert(data.error || 'Import failed');
          return;
        }
        await loadLocalMeta();
        if (data.slug) window.location.href = `${studioBase}/meta/${encodeURIComponent(data.slug)}`;
      } catch (err) {
        console.error('Site import failed', err);
      }
    });
  }

  function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  function studioBearer() {
    return window.__ZINTRIQ_STUDIO_TOKEN__ || localStorage.getItem('zintriq_studio_token') || '';
  }

  function studioHeaders(extra = {}) {
    const headers = { Accept: 'application/json', ...extra };
    const bearer = studioBearer();
    if (bearer) headers.Authorization = `Bearer ${bearer}`;
    else {
      const csrf = getCsrfToken();
      if (csrf) headers['X-CSRF-Token'] = csrf;
    }
    return headers;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
