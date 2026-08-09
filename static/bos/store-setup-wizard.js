/** First-time setup — business name + customer QR type in one flow. */

import { CUSTOMER_QR_TYPES } from "./customer-qr-types.js";
import { apiPost } from "./services/api.js";

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

/**
 * @param {{ onDone?: (result: { store_id: number, experience_id?: number }) => void }} [opts]
 */
export function openStoreSetupWizard(opts = {}) {
  let selected = CUSTOMER_QR_TYPES[0];
  let name = "";

  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay";
  overlay.innerHTML = `
    <div class="bos-modal bos-modal--sm bos-create-wizard" role="dialog" aria-labelledby="setup-title">
      <header class="bos-create-wizard__head">
        <h2 class="bos-panel-title" id="setup-title">Set up your store &amp; customer QR</h2>
        <p class="cp-muted bos-create-wizard__hint">Two steps — we create your store and a draft QR customers can scan.</p>
      </header>
      <div class="bos-field">
        <label class="bos-label" for="setup-name">Business name</label>
        <input class="bos-input" id="setup-name" placeholder="e.g. Sunbeam Bakery" required>
      </div>
      <p class="bos-label" style="margin:16px 0 8px">Customer QR type</p>
      <div class="bos-type-picker" role="listbox" aria-label="Customer QR type">
        ${CUSTOMER_QR_TYPES.map((t) => `
          <button type="button" class="bos-type-picker__option${selected.id === t.id ? " is-selected" : ""}" data-tpl="${t.id}" role="option">
            <strong class="bos-type-picker__name">${esc(t.name)}</strong>
            <p class="bos-type-picker__desc">${esc(t.description)}</p>
          </button>`).join("")}
      </div>
      <footer class="bos-create-wizard__foot">
        <button type="button" class="bos-btn bos-btn-ghost" id="setup-cancel">Cancel</button>
        <button type="button" class="bos-btn bos-btn-primary" id="setup-continue">Continue</button>
      </footer>
    </div>`;

  const paintSel = () => {
    overlay.querySelectorAll("[data-tpl]").forEach((btn) => {
      btn.classList.toggle("is-selected", selected.id === btn.dataset.tpl);
    });
  };

  overlay.querySelectorAll("[data-tpl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      selected = CUSTOMER_QR_TYPES.find((t) => t.id === btn.dataset.tpl) || selected;
      paintSel();
    });
  });

  overlay.querySelector("#setup-cancel")?.addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  overlay.querySelector(".bos-modal")?.addEventListener("click", (e) => e.stopPropagation());

  overlay.querySelector("#setup-continue")?.addEventListener("click", async () => {
    name = overlay.querySelector("#setup-name")?.value.trim() || "";
    if (!name) {
      window.alert("Enter your business name.");
      return;
    }
    const btn = overlay.querySelector("#setup-continue");
    btn.disabled = true;
    btn.textContent = "Creating…";
    try {
      const store = await apiPost("/api/stores", { name });
      const exp = await apiPost("/api/qr-experiences", {
        name: selected.name === "Restaurant" || selected.name === "Clinic" ? `${name} — ${selected.name}` : name,
        type: selected.id,
        template_id: selected.template_id,
        store_id: store.id,
        description: selected.description,
        experience_config: { template_id: selected.template_id, description: selected.description },
      });
      overlay.remove();
      opts.onDone?.({ store_id: store.id, experience_id: exp.id, store_slug: store.slug });
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Continue";
      window.alert(err.message || "Setup failed. Try again.");
    }
  });

  document.body.appendChild(overlay);
  overlay.querySelector("#setup-name")?.focus();
}
