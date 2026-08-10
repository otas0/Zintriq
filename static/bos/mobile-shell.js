/** Mobile app shell — PWA + Capacitor native (Android / iOS) */

import { visibleNav } from "./product-focus.js";

export function isMobileApp() {
  if (typeof window.Capacitor?.isNativePlatform === "function" && window.Capacitor.isNativePlatform()) {
    return true;
  }
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  if (window.navigator.standalone === true) return true;
  return false;
}

function mountTabBar() {
  const tabs = visibleNav().filter((n) => !n.external);
  if (!tabs.length || document.getElementById("bos-mobile-tabbar")) return;

  const nav = document.createElement("nav");
  nav.id = "bos-mobile-tabbar";
  nav.className = "bos-mobile-tabbar";
  nav.setAttribute("aria-label", "Main navigation");

  const path = window.location.pathname.replace(/\/$/, "") || "/app/store";
  nav.innerHTML = tabs.map((t) => {
    const active = path === t.path || path.startsWith(t.path + "/") || (t.path.includes("#") && path === t.path.split("#")[0]);
    return `<a class="bos-mobile-tabbar__link${active ? " is-active" : ""}" href="${t.path}">
      <span class="bos-mobile-tabbar__icon" aria-hidden="true">${t.icon}</span>
      <span>${t.label}</span>
    </a>`;
  }).join("");

  document.body.appendChild(nav);
}

function initNativePlugins() {
  const cap = window.Capacitor;
  if (!cap?.isNativePlatform?.()) return;

  const App = cap.Plugins?.App;
  if (App?.addListener) {
    App.addListener("backButton", ({ canGoBack }) => {
      const drawer = document.getElementById("bos-drawer");
      if (drawer && !drawer.classList.contains("hidden")) {
        drawer.classList.add("hidden");
        return;
      }
      const sidebar = document.getElementById("bos-sidebar");
      if (sidebar?.classList.contains("is-open")) {
        sidebar.classList.remove("is-open");
        document.getElementById("bos-sidebar-backdrop")?.classList.add("hidden");
        return;
      }
      if (canGoBack) window.history.back();
      else App.exitApp?.();
    });
  }

  const StatusBar = cap.Plugins?.StatusBar;
  StatusBar?.setStyle?.({ style: "DARK" });
  StatusBar?.setBackgroundColor?.({ color: "#111111" });
}

function registerServiceWorker() {
  // Only installed PWA / standalone — not regular browser tabs (avoids hijacking /places, /store, etc.)
  if (!("serviceWorker" in navigator)) return;
  if (!window.matchMedia("(display-mode: standalone)").matches && window.navigator.standalone !== true) {
    return;
  }
  navigator.serviceWorker.register("/sw.js", { scope: "/app/" }).catch(() => {});
}

function unregisterDevServiceWorkers() {
  if (!("serviceWorker" in navigator)) return;
  const host = window.location.hostname;
  if (host !== "localhost" && host !== "127.0.0.1") return;
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((reg) => reg.unregister());
  }).catch(() => {});
}

export function initMobileShell() {
  unregisterDevServiceWorkers();

  if (!isMobileApp()) {
    registerServiceWorker();
    return;
  }

  document.documentElement.classList.add("bos-native");
  document.querySelector(".bos-app")?.classList.add("bos-app--mobile");
  mountTabBar();
  initNativePlugins();
}
