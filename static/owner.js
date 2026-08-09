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
});
