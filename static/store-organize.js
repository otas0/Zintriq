/** Groups & labels — separate from the stores list (P2). */

(() => {
  const boot = window.WORKSPACE_BOOT;
  if (!boot) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const groupsEl = document.getElementById('organize-groups');
  const labelsEl = document.getElementById('organize-labels');

  const api = async (payload) => {
    const res = await fetch('/api/workspace/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ ...payload, csrf_token: csrf }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  };

  const esc = (s) => String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  let groups = boot.groups || [];
  let labels = boot.labels || [];

  const render = () => {
    document.getElementById('organize-groups-empty')?.classList.toggle('hidden', groups.length > 0);
    document.getElementById('organize-labels-empty')?.classList.toggle('hidden', labels.length > 0);

    groupsEl.innerHTML = groups.map((g) => `
      <li class="store-organize-item">
        <a class="store-organize-item__main" href="/my-stores/groups/${g.id}">
          <span class="store-organize-item__name">${esc(g.name)}</span>
          <span class="store-organize-item__meta">${g.total || 0} stores · ${g.active_count || 0} active</span>
        </a>
        <button type="button" class="store-organize-item__action" data-rename-group="${g.id}">Rename</button>
      </li>
    `).join('');

    labelsEl.innerHTML = labels.map((l) => `
      <li class="store-organize-item">
        <a class="store-organize-item__main" href="/app/store?label=${l.id}">
          <span class="store-organize-item__name">${esc(l.name)}</span>
          <span class="store-organize-item__meta">${l.store_count || 0} stores</span>
        </a>
        <button type="button" class="store-organize-item__action" data-rename-label="${l.id}">Rename</button>
      </li>
    `).join('');
  };

  document.getElementById('organize-create-group')?.addEventListener('click', async () => {
    const name = window.prompt('Group name');
    if (!name?.trim()) return;
    try {
      const data = await api({ action: 'create_group', name: name.trim(), store_ids: [] });
      groups = data.groups || groups;
      render();
    } catch (err) {
      window.alert(err.message);
    }
  });

  document.getElementById('organize-create-label')?.addEventListener('click', async () => {
    const name = window.prompt('Label name');
    if (!name?.trim()) return;
    try {
      const data = await api({ action: 'create_label', name: name.trim(), store_ids: [] });
      labels = data.labels || labels;
      render();
    } catch (err) {
      window.alert(err.message);
    }
  });

  groupsEl?.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-rename-group]');
    if (!btn) return;
    event.preventDefault();
    const id = Number(btn.dataset.renameGroup);
    const group = groups.find((g) => g.id === id);
    const name = window.prompt('Rename group', group?.name || '');
    if (!name?.trim()) return;
    try {
      const data = await api({ action: 'rename_group', group_id: id, name: name.trim(), store_ids: [] });
      groups = data.groups || groups;
      render();
    } catch (err) {
      window.alert(err.message);
    }
  });

  labelsEl?.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-rename-label]');
    if (!btn) return;
    event.preventDefault();
    const id = Number(btn.dataset.renameLabel);
    const label = labels.find((l) => l.id === id);
    const name = window.prompt('Rename label', label?.name || '');
    if (!name?.trim()) return;
    try {
      const data = await api({ action: 'rename_label', label_id: id, name: name.trim(), store_ids: [] });
      labels = data.labels || labels;
      render();
    } catch (err) {
      window.alert(err.message);
    }
  });

  render();
})();
