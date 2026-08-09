/** Store hub — stores list + customer QR + responses under one nav item. */

import { mountQrExperiencesPage } from "./features/qr-experiences-page.js";
import { mountResponsesPage } from "./features/responses-page.js";
import { openStoreSetupWizard } from "./store-setup-wizard.js";

const TABS = ["stores", "experiences", "responses"];

/** @returns {{ tab: string, storeId: number | null }} */
function parseHash() {
  const raw = (window.location.hash || "").replace(/^#/, "");
  const storeMatch = raw.match(/^store\/(\d+)/);
  if (storeMatch) {
    const sub = raw.includes("/") ? raw.split("/").slice(1).join("/") : "";
    if (sub.startsWith("experiences") || sub.startsWith("customer-qr")) {
      return { tab: "experiences", storeId: Number(storeMatch[1]) };
    }
    if (sub.startsWith("responses")) {
      return { tab: "responses", storeId: Number(storeMatch[1]) };
    }
    return { tab: "experiences", storeId: Number(storeMatch[1]) };
  }
  if (raw.startsWith("experience") || raw.startsWith("builder") || raw === "experiences" || raw === "customer-qr") {
    return { tab: "experiences", storeId: null };
  }
  if (raw === "responses") return { tab: "responses", storeId: null };
  if (TABS.includes(raw)) return { tab: raw, storeId: null };
  return { tab: "stores", storeId: null };
}

function storeFromBoot(storeId) {
  const boot = window.WORKSPACE_BOOT;
  if (!boot?.stores || !storeId) return null;
  return boot.stores.find((s) => s.id === storeId) || null;
}

function updateHeader(tab, storeId) {
  const actions = document.getElementById("store-hub-actions");
  const titleEl = document.querySelector(".merchant-page-head__title");
  const subtitleEl = document.querySelector(".merchant-page-head__subtitle");
  const store = storeFromBoot(storeId);

  if (titleEl && store) {
    titleEl.textContent = store.name;
  } else if (titleEl) {
    titleEl.textContent = "Stores";
  }

  if (subtitleEl) {
    if (store && tab === "experiences") {
      subtitleEl.textContent = "Customer QR codes for this store.";
    } else if (store && tab === "responses") {
      subtitleEl.textContent = "Customer feedback for this store.";
    } else if (store) {
      subtitleEl.textContent = "Manage this store's QR and customer touchpoints.";
    } else {
      subtitleEl.textContent = "Manage storefronts, customer QR, and responses.";
    }
  }

  if (!actions) return;

  if (tab === "stores") {
    const boot = window.WORKSPACE_BOOT;
    const empty = !boot?.stores?.length;
    actions.innerHTML = empty
      ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="store-hub-setup">Set up store &amp; QR</button>`
      : `<a class="bos-btn bos-btn-primary bos-btn-sm" href="/create">Add store</a>
         <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="store-hub-setup">Quick setup</button>`;
    actions.style.display = "";
    document.getElementById("store-hub-setup")?.addEventListener("click", () => {
      openStoreSetupWizard({ onDone: reloadAfterSetup });
    });
  } else if (tab === "experiences") {
    actions.innerHTML = `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="store-hub-add-qr">Add customer QR</button>`;
    if (storeId) {
      actions.innerHTML += `<button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="store-hub-clear-store">All stores</button>`;
    }
    actions.style.display = "";
    document.getElementById("store-hub-add-qr")?.addEventListener("click", () => {
      window.dispatchEvent(new CustomEvent("bos:add-customer-qr", { detail: { storeId } }));
    });
    document.getElementById("store-hub-clear-store")?.addEventListener("click", () => {
      window.location.hash = "experiences";
      mountTab(parseHash());
    });
  } else {
    actions.style.display = "none";
  }
}

function setTab(tab, storeId) {
  document.querySelectorAll("[data-store-hub-tab]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.storeHubTab === tab);
  });
  document.getElementById("store-panel-stores")?.classList.toggle("hidden", tab !== "stores");
  document.getElementById("store-panel-experiences")?.classList.toggle("hidden", tab !== "experiences");
  document.getElementById("store-panel-responses")?.classList.toggle("hidden", tab !== "responses");

  const chip = document.getElementById("store-hub-store-chip");
  const store = storeFromBoot(storeId);
  if (chip) {
    if (store && tab !== "stores") {
      chip.textContent = store.name;
      chip.classList.remove("hidden");
    } else {
      chip.classList.add("hidden");
    }
  }

  updateHeader(tab, storeId);
}

let responsesMounted = false;
let activeStoreId = null;

async function mountTab({ tab, storeId }) {
  activeStoreId = storeId;
  setTab(tab, storeId);

  if (tab === "experiences") {
    const panel = document.getElementById("store-panel-experiences");
    if (panel) {
      await mountQrExperiencesPage(panel, { embedded: true, storeId });
    }
  }
  if (tab === "responses" && !responsesMounted) {
    const panel = document.getElementById("store-panel-responses");
    if (panel) {
      await mountResponsesPage(panel, { embedded: true, storeId });
      responsesMounted = true;
    }
  }
}

function reloadAfterSetup({ store_id, experience_id }) {
  window.location.href = experience_id
    ? `/app/store#store/${store_id}/experiences`
    : `/app/store#store/${store_id}`;
  window.location.reload();
}

function maybeShowEmptyBanner() {
  const boot = window.WORKSPACE_BOOT;
  if (boot?.stores?.length) return;
  const panel = document.getElementById("store-panel-stores");
  if (!panel || document.getElementById("store-empty-banner")) return;
  const banner = document.createElement("div");
  banner.id = "store-empty-banner";
  banner.className = "material-panel bos-store-empty-banner";
  banner.innerHTML = `
    <h2 class="bos-panel-title">Get started in 2 steps</h2>
    <p class="cp-muted">Add your business name and pick a customer QR type — restaurant, clinic, feedback, and more.</p>
    <button type="button" class="bos-btn bos-btn-primary" id="store-empty-setup">Set up store &amp; customer QR</button>`;
  panel.prepend(banner);
  banner.querySelector("#store-empty-setup")?.addEventListener("click", () => {
    openStoreSetupWizard({ onDone: reloadAfterSetup });
  });
}

export function initStoreHub() {
  const root = document.getElementById("bos-store-hub");
  if (!root) return;

  maybeShowEmptyBanner();

  document.querySelectorAll("[data-store-hub-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.storeHubTab;
      const storeId = activeStoreId;
      if (storeId && tab !== "stores") {
        window.location.hash = `store/${storeId}/${tab === "experiences" ? "experiences" : "responses"}`;
      } else {
        window.location.hash = tab === "experiences" ? "experiences" : tab === "responses" ? "responses" : "stores";
      }
      mountTab(parseHash());
    });
  });

  window.addEventListener("hashchange", () => mountTab(parseHash()));
  mountTab(parseHash());
}

initStoreHub();
