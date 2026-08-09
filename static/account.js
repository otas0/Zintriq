document.addEventListener('DOMContentLoaded', () => {
  const changeForm = document.getElementById('change-password-form');
  if (changeForm) {
    changeForm.addEventListener('submit', (event) => {
      const password = changeForm.querySelector('[name="password"]')?.value || '';
      const confirm = changeForm.querySelector('[name="confirm_password"]')?.value || '';
      if (password !== confirm) {
        event.preventDefault();
        window.alert('Your new passwords do not match.');
      }
    });
  }

  const connectedRoot = document.getElementById('account-connected-apps');
  if (connectedRoot) {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    fetch('/api/integrations/plugins', { headers: { 'X-CSRF-Token': csrf } })
      .then((r) => (r.ok ? r.json() : []))
      .then((plugins) => {
        const connected = (plugins || []).filter((p) => p.connection?.status === 'active' || p.connection?.status === 'connected');
        if (!connected.length) {
          connectedRoot.innerHTML = '<p class="cp-muted" style="font-size:13px">No apps connected yet. Connect Google Calendar in Settings → Integrations.</p>';
          return;
        }
        connectedRoot.innerHTML = connected.map((p) => {
          const email = p.connection?.external_account_email || '';
          const status = p.connection?.status || 'connected';
          return `<div class="os-card os-card-padded" style="padding:12px 16px">
            <strong>${p.name}</strong>
            <p class="cp-muted" style="margin:4px 0 0;font-size:13px">${email ? `${email} · ` : ''}${status}</p>
          </div>`;
        }).join('');
      })
      .catch(() => {
        connectedRoot.innerHTML = '<p class="cp-muted" style="font-size:13px">Could not load connected apps.</p>';
      });
  }

  const modal = document.getElementById('delete-account-modal');
  if (!modal) return;

  const openModal = () => {
    modal.hidden = false;
    modal.classList.add('is-open');
    document.body.classList.add('bos-confirm-modal-open');
    modal.querySelector('.bos-btn-danger')?.focus();
  };

  const closeModal = () => {
    modal.hidden = true;
    modal.classList.remove('is-open');
    document.body.classList.remove('bos-confirm-modal-open');
  };

  if (modal.classList.contains('is-open')) {
    document.body.classList.add('bos-confirm-modal-open');
  }

  modal.querySelectorAll('[data-modal-dismiss="delete-account"]').forEach((el) => {
    el.addEventListener('click', () => {
      const cancelForm = modal.querySelector('.bos-confirm-modal__cancel-form');
      if (cancelForm) {
        cancelForm.requestSubmit();
      } else {
        closeModal();
      }
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && modal.classList.contains('is-open')) {
      const cancelForm = modal.querySelector('.bos-confirm-modal__cancel-form');
      if (cancelForm) {
        cancelForm.requestSubmit();
      }
    }
  });
});
