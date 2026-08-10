/** Unified Add customer QR wizard — one flow for shop, landing, and specialized types. */

import { allCustomerQrEntries } from "./customer-qr-types.js";

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  return { "Content-Type": "application/json", "X-CSRF-Token": token };
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: csrfHeaders(),
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

const SECTION_LABELS = {
  shop: "Shop",
  landing: "Landing page",
  specialized: "Specialized",
};

/**
 * @param {{
 *   storeId: number,
 *   storeSlug?: string,
 *   storeName?: string,
 *   landingOnly?: boolean,
 *   onDone?: (result: { redirect: string, kind: string, id?: number }) => void,
 * }} opts
 */
export function openCustomerQrWizard(opts) {
  const { storeId, storeSlug, storeName, landingOnly = false, onDone } = opts;
  const entries = allCustomerQrEntries({ landingOnly });
  let selected = entries[0];
  let name = selected.defaultName;

  const overlay = document.createElement("div");
  overlay.className = "bos-modal-overlay";

  const renderOptions = () => {
    let lastSection = "";
    return entries.map((entry) => {
      const sectionHtml = entry.section !== lastSection
        ? `<p class="bos-wizard-section-label">${SECTION_LABELS[entry.section] || entry.section}</p>`
        : "";
      lastSection = entry.section;
      return `${sectionHtml}
        <button type="button" class="bos-type-picker__option${selected.id === entry.id ? " is-selected" : ""}"
          data-entry="${entry.id}" role="option" aria-selected="${selected.id === entry.id}">
          <strong class="bos-type-picker__name">${esc(entry.name)}</strong>
          <p class="bos-type-picker__desc">${esc(entry.description)}</p>
        </button>`;
    }).join("");
  };

  const paint = () => {
    overlay.querySelector("#cqr-options").innerHTML = renderOptions();
    overlay.querySelectorAll("[data-entry]").forEach((btn) => {
      btn.addEventListener("click", () => {
        selected = entries.find((e) => e.id === btn.dataset.entry) || selected;
        name = selected.defaultName;
        overlay.querySelector("#cqr-name").value = name;
        paint();
      });
    });
    overlay.querySelector("#cqr-name").value = name;
  };

  overlay.innerHTML = `
    <div class="bos-modal bos-modal--sm bos-create-wizard" role="dialog" aria-labelledby="cqr-title">
      <header class="bos-create-wizard__head">
        <h2 class="bos-panel-title" id="cqr-title">${landingOnly ? "Add landing page" : "Add customer QR"}</h2>
        <p class="bos-create-wizard__hint cp-muted">
          ${landingOnly
            ? "Pick a landing style, name it, then customize the page customers see first."
            : storeName
              ? `What should customers do when they scan? We'll create it for ${esc(storeName)}.`
              : "What should customers do when they scan? Pick a type and we'll create it."}
        </p>
      </header>
      <div class="bos-type-picker" id="cqr-options" role="listbox" aria-label="Customer QR type"></div>
      <div class="bos-field bos-create-wizard__name">
        <label class="bos-label" for="cqr-name">Name</label>
        <input class="bos-input" id="cqr-name" value="${esc(name)}">
      </div>
      <footer class="bos-create-wizard__foot">
        <button type="button" class="bos-btn bos-btn-ghost" id="cqr-cancel">Cancel</button>
        <button type="button" class="bos-btn bos-btn-primary" id="cqr-create">Create</button>
      </footer>
    </div>`;

  paint();

  overlay.querySelector("#cqr-cancel")?.addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  overlay.querySelector(".bos-modal")?.addEventListener("click", (e) => e.stopPropagation());

  overlay.querySelector("#cqr-create")?.addEventListener("click", async () => {
    name = overlay.querySelector("#cqr-name")?.value.trim() || selected.defaultName;
    const btn = overlay.querySelector("#cqr-create");
    btn.disabled = true;
    btn.textContent = "Creating…";
    try {
      let result;
      if (selected.kind === "landing") {
        const created = await apiPost("/api/qr-experiences", {
          name,
          type: selected.landingType,
          template_id: selected.template_id,
          store_id: storeId,
          description: selected.description,
          experience_config: {
            template_id: selected.template_id,
            description: selected.description,
          },
        });
        const slug = storeSlug || created.store_slug;
        result = {
          kind: "landing",
          id: created.id,
          redirect: slug
            ? `/manage/${encodeURIComponent(slug)}/landing-qr#builder/${created.id}`
            : `/app/store#experience/${created.id}`,
        };
      } else {
        result = await apiPost(`/api/stores/${storeId}/customer-qr`, {
          kind: selected.kind,
          name,
        });
      }
      overlay.remove();
      if (onDone) {
        onDone(result);
      } else if (result.redirect) {
        window.location.href = result.redirect;
      }
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Create";
      window.alert(err.message || "Could not create. Try again.");
    }
  });

  document.body.appendChild(overlay);
  overlay.querySelector("#cqr-name")?.focus();
}

/** Open wizard when URL contains ?add=1 (used from BOS overview links). */
export function maybeOpenCustomerQrWizardFromQuery(boot) {
  if (!boot?.storeId) return;
  const params = new URLSearchParams(window.location.search);
  if (params.get("add") !== "1") return;
  openCustomerQrWizard({
    storeId: boot.storeId,
    storeSlug: boot.storeSlug,
    storeName: boot.storeName,
    onDone: ({ redirect }) => {
      if (redirect) window.location.replace(redirect);
    },
  });
  params.delete("add");
  const qs = params.toString();
  const next = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
  window.history.replaceState({}, "", next);
}
