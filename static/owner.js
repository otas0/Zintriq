document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.confirm-form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const message = form.dataset.confirm || 'Are you sure?';
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  const batchForm = document.getElementById('batch-form');
  if (batchForm) {
    batchForm.addEventListener('submit', (event) => {
      const action = batchForm.querySelector('[name="action"]')?.value;
      const selected = batchForm.querySelectorAll('.store-checkbox:checked').length;
      if (!selected) {
        event.preventDefault();
        window.alert('Select at least one store.');
        return;
      }
      if (action === 'delete' && !window.confirm(`Permanently delete ${selected} store(s) and all associated data?`)) {
        event.preventDefault();
      }
    });
  }

  const selectAll = document.getElementById('select-all');
  if (selectAll) {
    selectAll.addEventListener('change', () => {
      document.querySelectorAll('.store-checkbox').forEach((box) => {
        box.checked = selectAll.checked;
      });
    });
  }

  document.querySelectorAll('[data-preview]').forEach((input) => {
    input.addEventListener('change', () => {
      const targetId = input.dataset.preview;
      const target = document.getElementById(targetId);
      const file = input.files?.[0];
      if (!target || !file) return;
      const reader = new FileReader();
      reader.onload = () => {
        target.innerHTML = `<img src="${reader.result}" alt="Preview">`;
      };
      reader.readAsDataURL(file);
    });
  });

  document.querySelectorAll('[id$="-url"], #add-item-image-url').forEach((input) => {
    input.addEventListener('input', () => {
      const previewId = input.id === 'add-item-image-url'
        ? 'add-item-image-preview'
        : input.id.replace('-url', '-preview').replace('background', 'background-preview').replace('item-image', 'item-image-preview');
      const target = document.getElementById(previewId);
      if (!target) return;
      if (input.value) {
        target.innerHTML = `<img src="${input.value}" alt="Preview">`;
      }
    });
  });

  document.querySelectorAll('.sortable-list').forEach((list) => {
    const inputId = list.dataset.reorderInput;
    const formId = list.dataset.reorderForm;
    const input = inputId ? document.getElementById(inputId) : null;
    const form = formId ? document.getElementById(formId) : null;
    let dragged = null;

    list.querySelectorAll('.sortable-row').forEach((row) => {
      row.addEventListener('dragstart', () => {
        dragged = row;
        row.classList.add('dragging');
      });
      row.addEventListener('dragend', () => {
        row.classList.remove('dragging');
        dragged = null;
        if (!input || !form) return;
        const order = [...list.querySelectorAll('.sortable-row')].map((el) => el.dataset.id).join(',');
        input.value = order;
        form.submit();
      });
      row.addEventListener('dragover', (event) => {
        event.preventDefault();
        if (!dragged || dragged === row) return;
        const rect = row.getBoundingClientRect();
        const after = event.clientY > rect.top + rect.height / 2;
        row.parentNode.insertBefore(dragged, after ? row.nextSibling : row);
      });
    });
  });

  const addModal = document.getElementById('sf-add-product-modal');
  const openModal = () => {
    if (!addModal) return;
    addModal.hidden = false;
    document.body.classList.add('os-modal-open');
    addModal.querySelector('input[name="name"]')?.focus();
  };
  const closeModal = () => {
    if (!addModal) return;
    addModal.hidden = true;
    document.body.classList.remove('os-modal-open');
  };
  document.getElementById('sf-add-product-open')?.addEventListener('click', openModal);
  document.getElementById('sf-add-product-open-empty')?.addEventListener('click', openModal);
  addModal?.querySelectorAll('[data-modal-close]').forEach((el) => {
    el.addEventListener('click', closeModal);
  });
  addModal?.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeModal();
  });

  const previewDock = document.getElementById('sf-preview-dock');
  const previewBackdrop = document.getElementById('sf-preview-backdrop');
  const previewFrame = document.getElementById('sf-preview-frame');
  const previewToggle = document.getElementById('sf-preview-toggle');
  const previewClose = document.getElementById('sf-preview-close');
  const ownerLayout = document.getElementById('sf-owner-layout');

  const reloadPreview = () => {
    if (!previewFrame?.dataset.src) return;
    previewFrame.src = `${previewFrame.dataset.src}${previewFrame.dataset.src.includes('?') ? '&' : '?'}_=${Date.now()}`;
  };

  const usePinnedPreview = () => window.matchMedia('(min-width: 1024px)').matches;

  const openPreview = () => {
    if (!previewDock || !previewBackdrop) return;
    if (previewFrame && !previewFrame.src && previewFrame.dataset.src) {
      previewFrame.src = previewFrame.dataset.src;
    }
    previewDock.hidden = false;
    if (usePinnedPreview()) {
      ownerLayout?.classList.add('sf-owner-layout--preview');
      previewBackdrop.hidden = true;
    } else {
      previewBackdrop.hidden = false;
    }
    previewToggle?.setAttribute('aria-expanded', 'true');
    document.body.classList.add('sf-preview-open');
  };
  const closePreview = () => {
    if (!previewDock || !previewBackdrop) return;
    previewDock.hidden = true;
    previewBackdrop.hidden = true;
    ownerLayout?.classList.remove('sf-owner-layout--preview');
    previewToggle?.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('sf-preview-open');
  };
  previewToggle?.addEventListener('click', () => {
    if (previewDock?.hidden) openPreview();
    else closePreview();
  });
  previewClose?.addEventListener('click', closePreview);
  previewBackdrop?.addEventListener('click', closePreview);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && previewDock && !previewDock.hidden) closePreview();
  });

  const csrfToken = () => document.querySelector('input[name="csrf_token"]')?.value || '';

  document.querySelectorAll('.sf-deal-toggle').forEach((input) => {
    input.addEventListener('change', async () => {
      const url = input.dataset.dealUrl;
      const itemId = input.dataset.itemId;
      const meta = document.querySelector(`[data-deal-meta="${itemId}"]`);
      if (!url) return;
      input.disabled = true;
      try {
        const body = new FormData();
        body.append('csrf_token', csrfToken());
        body.append('enabled', input.checked ? '1' : '0');
        const res = await fetch(url, {
          method: 'POST',
          body,
          headers: { 'X-Requested-With': 'fetch' },
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed');
        if (meta) {
          if (data.enabled && data.sale_price != null) {
            meta.innerHTML = `<span class="sf-product-deal__badge">${data.label || 'On sale'}</span><span class="sf-product-deal__price">$${Number(data.sale_price).toFixed(2)}</span>`;
          } else {
            meta.innerHTML = '';
          }
        }
        if (previewFrame?.src) reloadPreview();
      } catch (err) {
        input.checked = !input.checked;
        window.alert(err.message || 'Could not update deal.');
      } finally {
        input.disabled = false;
      }
    });
  });

  if (new URLSearchParams(window.location.search).get('add') === '1') {
    openModal();
  }
});
