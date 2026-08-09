import * as store from "../core/store.js";
import { markAllRead, getUnreadCount, syncServerNotifications } from "../platform/notifications.js";
import { escapeHtml } from "../services/search.js";

export function renderNotificationBell() {
  const btn = document.getElementById("bos-notifications-btn");
  const badge = document.getElementById("bos-notifications-badge");
  const count = getUnreadCount();
  if (badge) {
    badge.textContent = count > 0 ? String(count) : "";
    badge.classList.toggle("hidden", count === 0);
  }
  if (btn) btn.setAttribute("aria-label", `${count} unread notifications`);
}

export function renderNotificationPanel() {
  const panel = document.getElementById("bos-notifications-panel");
  if (!panel) return;
  const items = store.getCollection("notifications");
  panel.innerHTML = `
    <div class="bos-notifications__head">
      <h3>Notifications</h3>
      <button type="button" class="os-btn os-btn-ghost os-btn-sm" id="bos-notifications-read-all">Mark all read</button>
    </div>
    ${items.length ? `<ul class="bos-notifications__list">${items.map((n) => `
      <li class="bos-notification${n.read ? "" : " is-unread"}" data-ntf-id="${n.id}">
        <a href="${escapeHtml(String(n.href || "/app/store"))}" class="bos-notification__link">
          <strong>${escapeHtml(String(n.title))}</strong>
          <span>${escapeHtml(String(n.body))}</span>
          <span class="bos-notification__meta">${escapeHtml(String(n.priority || "info"))} · ${escapeHtml(String(n.createdAt || "").slice(0, 10))}</span>
        </a>
        <button type="button" class="os-btn os-btn-ghost os-btn-sm" data-dismiss-ntf="${n.id}">Dismiss</button>
      </li>`).join("")}</ul>` : `<p class="bos-empty__text">No notifications</p>`}`;

  panel.querySelector("#bos-notifications-read-all")?.addEventListener("click", async () => {
    markAllRead();
    await fetch("/api/notifications/read-all", { method: "POST", credentials: "same-origin" }).catch(() => {});
    renderNotificationPanel();
    renderNotificationBell();
  });

  panel.querySelectorAll("[data-dismiss-ntf]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      store.remove("notifications", btn.getAttribute("data-dismiss-ntf"), { skipNotify: true });
      renderNotificationPanel();
      renderNotificationBell();
    });
  });

  panel.querySelectorAll(".bos-notification").forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.getAttribute("data-ntf-id");
      if (id) store.update("notifications", id, { read: true });
      renderNotificationPanel();
      renderNotificationBell();
    });
  });
}

export function initNotifications() {
  const btn = document.getElementById("bos-notifications-btn");
  const panel = document.getElementById("bos-notifications-panel");

  btn?.addEventListener("click", (e) => {
    e.stopPropagation();
    syncServerNotifications().then(() => {
      const open = panel?.classList.toggle("hidden") === false;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      renderNotificationPanel();
      renderNotificationBell();
    });
  });

  document.addEventListener("click", (e) => {
    if (!(e.target instanceof Element)) return;
    if (e.target.closest("#bos-notifications-btn") || e.target.closest("#bos-notifications-panel")) return;
    panel?.classList.add("hidden");
    btn?.setAttribute("aria-expanded", "false");
  });

  store.subscribe((col) => {
    if (!col || col === "notifications") {
      renderNotificationBell();
      if (panel && !panel.classList.contains("hidden")) renderNotificationPanel();
    }
  });

  window.addEventListener("bos:domain-event", () => {
    renderNotificationBell();
    if (panel && !panel.classList.contains("hidden")) renderNotificationPanel();
  });

  window.addEventListener("bos:mark-notifications-read", () => {
    markAllRead();
    renderNotificationPanel();
    renderNotificationBell();
  });

  const deferSync = () => {
    syncServerNotifications().then(() => {
      renderNotificationBell();
    });
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(deferSync, { timeout: 3000 });
  } else {
    setTimeout(deferSync, 500);
  }
}
