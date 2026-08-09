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
});
