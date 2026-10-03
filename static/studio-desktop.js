/**
 * Studio desktop bridge + web fallback for /studio/desktop gate.
 * In Electron: Auth0 Native PKCE via window.zintriqDesktop.
 * In browser: Sign in falls back to normal web /login → /studio.
 */
(function () {
  "use strict";

  const desktop = window.zintriqDesktop;
  const isDesktop = Boolean(desktop && desktop.isDesktop);
  const signInBtn = document.getElementById("sd-sign-in");
  const hint = document.getElementById("sd-hint");

  function showHint(msg) {
    if (!hint) return;
    hint.hidden = !msg;
    hint.textContent = msg || "";
  }

  // Browser: desktop gate Sign in → web Auth0 login, then /studio
  if (!isDesktop) {
    if (signInBtn) {
      signInBtn.addEventListener("click", () => {
        window.location.href = "/login?next=/studio";
      });
    }
    return;
  }

  document.documentElement.classList.add("zintriq-desktop");

  async function startDesktopLogin() {
    showHint("");
    if (signInBtn) signInBtn.disabled = true;
    try {
      const cfg = await desktop.getConfig();
      if (!cfg.hasAuth0) {
        showHint("Auth0 is not configured. Set AUTH0_DOMAIN and AUTH0_NATIVE_CLIENT_ID in desktop/.env.desktop.json");
        return;
      }
      await desktop.login();
      showHint("Complete sign-in in your browser. This window will open Studio when you return.");
    } catch (err) {
      showHint(err?.message || "Could not start sign-in");
    } finally {
      if (signInBtn) signInBtn.disabled = false;
    }
  }

  async function desktopLogout() {
    try {
      await desktop.logout();
    } catch (err) {
      console.error(err);
      window.location.href = "/studio/desktop";
    }
  }

  if (signInBtn) {
    signInBtn.addEventListener("click", startDesktopLogin);
    desktop.getToken().then((token) => {
      if (token) window.location.replace("/studio");
    }).catch(() => {});
  }

  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest("#ub-open-community");
      if (!a) return;
      const href = a.getAttribute("href") || "";
      if (href.startsWith("/app/community")) return;
      e.preventDefault();
      if (desktop && href) desktop.openExternal(href);
    },
    true,
  );

  const dropdown = document.getElementById("zw-user-dropdown");
  if (dropdown && !dropdown.querySelector("[data-desktop-logout]")) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "zw-user-dropdown__item zw-user-dropdown__item--danger";
    btn.setAttribute("role", "menuitem");
    btn.setAttribute("data-desktop-logout", "1");
    btn.textContent = "Sign out";
    btn.addEventListener("click", desktopLogout);
    dropdown.appendChild(btn);
  }

  const editorLogout = document.getElementById("ub-desktop-logout");
  if (editorLogout) {
    editorLogout.classList.remove("hidden");
    editorLogout.addEventListener("click", desktopLogout);
  }

  desktop.getUser?.().then((user) => {
    const meta = document.getElementById("ub-account-meta");
    if (meta && user?.email) meta.textContent = user.email;
  }).catch(() => {});

  desktop.onDeepLink?.((payload) => {
    if (!payload?.url) return;
    try {
      const u = new URL(payload.url);
      const pkg = u.searchParams.get("package");
      if (pkg) {
        window.location.href = `/studio?install=${encodeURIComponent(pkg)}`;
      }
    } catch {
      /* ignore */
    }
  });
})();
