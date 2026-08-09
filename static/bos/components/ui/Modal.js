/** Modal — confirmations, invites, settings dialogs. */

import { esc } from "./_utils.js";
import { Button } from "./Button.js";

let _modalHost = null;

function ensureHost() {
  if (_modalHost) return _modalHost;
  _modalHost = document.createElement("div");
  _modalHost.id = "bos-ui-modal-host";
  _modalHost.className = "bos-ui-modal-host hidden";
  _modalHost.setAttribute("aria-hidden", "true");
  document.body.appendChild(_modalHost);
  return _modalHost;
}

/**
 * @param {object} opts
 * @param {string} opts.title
 * @param {string} opts.bodyHtml
 * @param {string} [opts.primaryLabel]
 * @param {string} [opts.secondaryLabel]
 * @param {"primary"|"danger"} [opts.primaryVariant]
 * @param {() => void|Promise<void>} [opts.onPrimary]
 * @param {() => void} [opts.onClose]
 */
export function openModal({
  title,
  bodyHtml,
  primaryLabel = "Confirm",
  secondaryLabel = "Cancel",
  primaryVariant = "primary",
  onPrimary,
  onClose,
}) {
  const host = ensureHost();
  host.innerHTML = `
    <div class="bos-ui-modal-backdrop" data-modal-close></div>
    <div class="bos-ui-modal material-panel" role="dialog" aria-modal="true" aria-labelledby="bos-ui-modal-title">
      <header class="bos-ui-modal__head">
        <h2 id="bos-ui-modal-title" class="bos-ui-modal__title">${esc(title)}</h2>
        <button type="button" class="bos-ui-modal__close" data-modal-close aria-label="Close">×</button>
      </header>
      <div class="bos-ui-modal__body">${bodyHtml}</div>
      <footer class="bos-ui-modal__foot">
        ${Button({ variant: "ghost", label: secondaryLabel, id: "bos-ui-modal-cancel" })}
        ${Button({ variant: primaryVariant, label: primaryLabel, id: "bos-ui-modal-primary" })}
      </footer>
    </div>`;
  host.classList.remove("hidden");
  host.setAttribute("aria-hidden", "false");

  const close = () => {
    host.classList.add("hidden");
    host.setAttribute("aria-hidden", "true");
    onClose?.();
  };

  host.querySelectorAll("[data-modal-close]").forEach((el) => el.addEventListener("click", close));
  host.querySelector("#bos-ui-modal-cancel")?.addEventListener("click", close);
  host.querySelector("#bos-ui-modal-primary")?.addEventListener("click", async () => {
    const btn = host.querySelector("#bos-ui-modal-primary");
    if (btn instanceof HTMLButtonElement) {
      btn.disabled = true;
      btn.textContent = `${primaryLabel}…`;
    }
    try {
      await onPrimary?.();
      close();
    } catch {
      if (btn instanceof HTMLButtonElement) {
        btn.disabled = false;
        btn.textContent = primaryLabel;
      }
    }
  });

  document.addEventListener("keydown", function onEsc(e) {
    if (e.key === "Escape") {
      close();
      document.removeEventListener("keydown", onEsc);
    }
  });

  host.querySelector(".bos-ui-modal__close")?.focus();
  return { close };
}

/** Delete confirmation modal. */
export function confirmModal({ title, message, confirmLabel = "Delete", onConfirm }) {
  return openModal({
    title,
    bodyHtml: `<p class="bos-ui-modal__message">${esc(message)}</p>`,
    primaryLabel: confirmLabel,
    primaryVariant: "danger",
    onPrimary: onConfirm,
  });
}

export function closeModal() {
  _modalHost?.classList.add("hidden");
  _modalHost?.setAttribute("aria-hidden", "true");
}
