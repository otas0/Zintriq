/**
 * Zintriq workspace shell — topbar theme toggle + user menu.
 * Themes: light | dark only.
 */
(function () {
  'use strict';

  const THEMES = ['light', 'dark'];

  function currentTheme() {
    const t = document.documentElement.getAttribute('data-theme') || 'light';
    return THEMES.includes(t) ? t : 'light';
  }

  function applyTheme(theme) {
    if (!THEMES.includes(theme)) theme = 'light';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('zintriq-theme', theme);
    updateThemeButton(theme);
  }

  function updateThemeButton(theme) {
    const btn = document.getElementById('zw-theme-toggle');
    if (!btn) return;
    const label = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
    btn.setAttribute('aria-label', label);
    btn.title = label;
  }

  function cycleTheme() {
    const idx = THEMES.indexOf(currentTheme());
    applyTheme(THEMES[(idx + 1) % THEMES.length]);
  }

  const MOBILE_NAV_MQ = window.matchMedia('(max-width: 768px)');

  function closeUserMenu() {
    const menu = document.getElementById('zw-user-dropdown');
    const btn = document.getElementById('zw-user-menu');
    if (menu) menu.classList.add('hidden');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function closeSidebar() {
    const sidebar = document.getElementById('zw-sidebar');
    const toggle = document.getElementById('zw-sidebar-toggle');
    const backdrop = document.getElementById('zw-sidebar-backdrop');
    if (sidebar) sidebar.classList.remove('zw-sidebar--open');
    if (toggle) {
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open navigation');
    }
    if (backdrop) {
      backdrop.hidden = true;
      backdrop.setAttribute('aria-hidden', 'true');
    }
    document.body.classList.remove('zw-sidebar-open');
  }

  function openSidebar() {
    const sidebar = document.getElementById('zw-sidebar');
    const toggle = document.getElementById('zw-sidebar-toggle');
    const backdrop = document.getElementById('zw-sidebar-backdrop');
    if (!sidebar || !toggle) return;
    closeUserMenu();
    sidebar.classList.add('zw-sidebar--open');
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Close navigation');
    if (backdrop) {
      backdrop.hidden = false;
      backdrop.setAttribute('aria-hidden', 'false');
    }
    document.body.classList.add('zw-sidebar-open');
  }

  function toggleSidebar(e) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    const sidebar = document.getElementById('zw-sidebar');
    if (!sidebar) return;
    if (sidebar.classList.contains('zw-sidebar--open')) closeSidebar();
    else openSidebar();
  }

  function toggleUserMenu(e) {
    e.preventDefault();
    e.stopPropagation();
    const menu = document.getElementById('zw-user-dropdown');
    const btn = document.getElementById('zw-user-menu');
    if (!menu || !btn) return;
    const open = menu.classList.toggle('hidden') === false;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function init() {
    // Migrate removed yellow theme → light
    if (localStorage.getItem('zintriq-theme') === 'yellow') {
      localStorage.setItem('zintriq-theme', 'light');
    }
    applyTheme(currentTheme());

    const themeBtn = document.getElementById('zw-theme-toggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        cycleTheme();
      });
    }

    const userBtn = document.getElementById('zw-user-menu');
    if (userBtn) {
      userBtn.addEventListener('click', toggleUserMenu);
    }

    document.addEventListener('click', (e) => {
      if (e.target.closest('#zw-user-menu') || e.target.closest('#zw-user-dropdown')) return;
      closeUserMenu();
    });

    const sidebarToggle = document.getElementById('zw-sidebar-toggle');
    if (sidebarToggle) {
      sidebarToggle.addEventListener('click', toggleSidebar);
    }

    const sidebarBackdrop = document.getElementById('zw-sidebar-backdrop');
    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener('click', closeSidebar);
    }

    const sidebar = document.getElementById('zw-sidebar');
    if (sidebar) {
      sidebar.addEventListener('click', (e) => {
        const link = e.target.closest('a.zw-nav-item, a.zw-sidebar__link');
        if (link && MOBILE_NAV_MQ.matches) closeSidebar();
      });
    }

    if (typeof MOBILE_NAV_MQ.addEventListener === 'function') {
      MOBILE_NAV_MQ.addEventListener('change', (ev) => {
        if (!ev.matches) closeSidebar();
      });
    } else if (typeof MOBILE_NAV_MQ.addListener === 'function') {
      MOBILE_NAV_MQ.addListener((ev) => {
        if (!ev.matches) closeSidebar();
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      closeSidebar();
      closeUserMenu();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
