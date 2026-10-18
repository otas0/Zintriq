(function () {
  const desktop = window.zintriqDesktop;
  const label = document.getElementById("da-account-label");
  const loginBtn = document.getElementById("da-account-login");
  const logoutBtn = document.getElementById("da-account-logout");
  const syncBtn = document.getElementById("da-account-sync");
  if (!label) return;

  async function refresh() {
    if (!desktop || !desktop.isDesktop) {
      label.textContent = "Open this page in Zintriq Studio.";
      if (loginBtn) loginBtn.hidden = true;
      if (logoutBtn) logoutBtn.hidden = true;
      if (syncBtn) syncBtn.hidden = true;
      return;
    }
    const [user, cfg] = await Promise.all([desktop.getUser(), desktop.getConfig()]);
    if (user && user.email) {
      label.textContent = "Signed in · " + user.email;
      if (loginBtn) loginBtn.hidden = true;
      if (logoutBtn) logoutBtn.hidden = false;
      if (syncBtn) syncBtn.hidden = false;
      return;
    }
    label.textContent = cfg && cfg.hasAccountOrigin
      ? "Local · not signed in. Sign in to publish and sync."
      : "Local · set the public website origin to sign in.";
    if (loginBtn) loginBtn.hidden = false;
    if (logoutBtn) logoutBtn.hidden = true;
    if (syncBtn) syncBtn.hidden = true;
  }

  if (loginBtn) {
    loginBtn.addEventListener("click", async function () {
      if (!desktop) return;
      await desktop.login();
    });
  }
  if (syncBtn) {
    syncBtn.addEventListener("click", async function () {
      if (!desktop || !desktop.syncNow) return;
      syncBtn.disabled = true;
      try {
        await desktop.syncNow();
        window.location.reload();
      } finally {
        syncBtn.disabled = false;
      }
    });
  }
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async function () {
      if (!desktop) return;
      await desktop.logout();
      await refresh();
    });
  }
  refresh();
})();
