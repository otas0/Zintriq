import { peekUndo, consumeUndo, clearUndo } from "./undo.js";

/** @param {string} message @param {{ undo?: () => void, undoLabel?: string }} [opts] */
export function showToast(message, opts = {}) {
  const el = document.getElementById("bos-toast");
  const undoBtn = document.getElementById("bos-toast-undo");
  if (!el) return;

  if (opts.undo) {
    import("./undo.js").then(({ pushUndo }) => pushUndo(opts.undoLabel || "Undo", opts.undo));
  }

  const msgEl = el.querySelector(".bos-toast__msg");
  if (msgEl) msgEl.textContent = message;
  else el.insertAdjacentHTML("afterbegin", `<span class="bos-toast__msg">${message}</span>`);

  const undo = peekUndo();
  if (undoBtn) {
    if (undo) {
      undoBtn.textContent = undo.label;
      undoBtn.classList.remove("hidden");
    } else {
      undoBtn.classList.add("hidden");
    }
  }

  el.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    el.classList.add("hidden");
    clearUndo();
    if (undoBtn) undoBtn.classList.add("hidden");
  }, opts.undo ? 5000 : 2600);
}

export function initToastUndo() {
  document.getElementById("bos-toast-undo")?.addEventListener("click", () => {
    const action = consumeUndo();
    action?.run();
    document.getElementById("bos-toast")?.classList.add("hidden");
    showToast("Undone");
  });
}

export function getCsrf() {
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
}

export async function apiPost(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": getCsrf(),
    },
    credentials: "same-origin",
    body: JSON.stringify({ ...body, csrf_token: getCsrf() }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

export function openDrawer(title, html) {
  const drawer = document.getElementById("bos-drawer");
  const titleEl = document.getElementById("bos-drawer-title");
  const bodyEl = document.getElementById("bos-drawer-body");
  if (!drawer || !titleEl || !bodyEl) return;
  titleEl.textContent = title;
  bodyEl.innerHTML = html;
  drawer.classList.remove("hidden");
  drawer.setAttribute("aria-hidden", "false");
  document.body.classList.add("bos-drawer-open");
}

export function closeDrawer() {
  const drawer = document.getElementById("bos-drawer");
  if (!drawer) return;
  drawer.classList.add("hidden");
  drawer.setAttribute("aria-hidden", "true");
  document.body.classList.remove("bos-drawer-open");
}

export function renderActionBar(count, actions, onAction) {
  const bar = document.getElementById("bos-action-bar");
  const countEl = document.getElementById("bos-action-bar-count");
  const actionsEl = document.getElementById("bos-action-bar-actions");
  if (!bar || !countEl || !actionsEl) return;
  if (count <= 0) {
    bar.classList.add("hidden");
    bar.setAttribute("aria-hidden", "true");
    return;
  }
  bar.classList.remove("hidden");
  bar.setAttribute("aria-hidden", "false");
  countEl.textContent = `${count} selected`;
  actionsEl.innerHTML = actions
    .map(
      (a) =>
        `<button type="button" class="os-btn os-btn-sm ${a.variant === "danger" ? "os-btn-danger" : a.variant === "primary" ? "os-btn-primary" : "os-btn-ghost"}" data-action="${a.action}">${a.label}</button>`
    )
    .join("");
  actionsEl.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => onAction(btn.getAttribute("data-action") || ""));
  });
}

export function renderSkeletonRows(count = 5) {
  return Array.from({ length: count }, () => '<div class="bos-skeleton bos-skeleton--row"></div>').join("");
}
