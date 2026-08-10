document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('os-sidebar');
  const backdrop = document.getElementById('os-sidebar-backdrop');
  const openBtn = document.getElementById('os-menu-btn');
  const closeBtn = document.getElementById('os-sidebar-close');

  const openSidebar = () => {
    sidebar?.classList.add('is-open');
    if (backdrop) backdrop.hidden = false;
  };

  const closeSidebar = () => {
    sidebar?.classList.remove('is-open');
    if (backdrop) backdrop.hidden = true;
  };

  openBtn?.addEventListener('click', openSidebar);
  closeBtn?.addEventListener('click', closeSidebar);
  backdrop?.addEventListener('click', closeSidebar);

  document.querySelectorAll('#os-flashes .os-toast').forEach((toast) => {
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  });

  const switcher = document.getElementById('os-store-switcher');
  const switcherBtn = document.getElementById('os-store-switcher-btn');
  const switcherMenu = document.getElementById('os-store-switcher-menu');
  const closeSwitcher = () => {
    switcherMenu?.setAttribute('hidden', '');
    switcherBtn?.setAttribute('aria-expanded', 'false');
  };
  switcherBtn?.addEventListener('click', (event) => {
    event.stopPropagation();
    const open = switcherMenu?.hasAttribute('hidden');
    if (open) {
      switcherMenu?.removeAttribute('hidden');
      switcherBtn?.setAttribute('aria-expanded', 'true');
    } else {
      closeSwitcher();
    }
  });
  document.addEventListener('click', (event) => {
    if (switcher && !switcher.contains(event.target)) closeSwitcher();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeSwitcher();
  });
});
