/** Store hub — stores list + customer QR + responses under one nav item. */

import { mountCustomerQrOverview } from "./store-customer-qr-overview.js";
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

function hideAddStoreMenu() {
  document.getElementById("store-hub-add-menu")?.classList.add("hidden");
}

function openAddStoreMenu(anchor) {
  let menu = document.getElementById("store-hub-add-menu");
  if (!menu) {
    menu = document.createElement("div");
    menu.id = "store-hub-add-menu";
    menu.className = "store-hub-add-menu material-panel hidden";
    menu.innerHTML = `
      <a class="store-hub-add-menu__item" href="/create">Blank store</a>
      <button type="button" class="store-hub-add-menu__item" id="store-hub-add-wizard">Store + customer QR</button>
    `;
    document.body.appendChild(menu);
    menu.querySelector("#store-hub-add-wizard")?.addEventListener("click", () => {
      hideAddStoreMenu();
      openStoreSetupWizard({ onDone: reloadAfterSetup });
    });
  }
  const rect = anchor.getBoundingClientRect();
  menu.classList.remove("hidden");
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8)}px`;
}

function wireAddStoreButton() {
  document.getElementById("store-hub-add")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const menu = document.getElementById("store-hub-add-menu");
    if (menu && !menu.classList.contains("hidden")) {
      hideAddStoreMenu();
      return;
    }
    openAddStoreMenu(event.currentTarget);
  });
}

function renderStoresHeaderActions() {
  const actions = document.getElementById("store-hub-actions");
  if (!actions) return;
  actions.innerHTML = `
    <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="store-hub-add">Add store</button>
  `;
  actions.style.display = "";
  wireAddStoreButton();
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
      subtitleEl.textContent = "Overview — manage shop QR and landing pages in the store.";
    } else if (store && tab === "responses") {
      subtitleEl.textContent = "Customer feedback for this store.";
    } else if (store) {
      subtitleEl.textContent = "Manage this store's QR and customer touchpoints.";
    } else {
      subtitleEl.textContent = "Manage storefronts and customer QR entry points.";
    }
  }

  if (!actions) return;

  if (tab === "stores") {
    renderStoresHeaderActions();
  } else if (tab === "experiences") {
    const store = storeFromBoot(storeId);
    if (store) {
      actions.innerHTML = `<a class="bos-btn bos-btn-primary bos-btn-sm" href="/manage/${encodeURIComponent(store.slug)}/qr">Manage in store</a>
         <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="store-hub-clear-store">All stores</button>`;
      actions.style.display = "";
      document.getElementById("store-hub-clear-store")?.addEventListener("click", () => {
        window.location.hash = "experiences";
        mountTab(parseHash());
      });
    } else {
      actions.innerHTML = "";
      actions.style.display = "none";
    }
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

  const fab = document.getElementById("bos-quick-fab");
  if (fab) fab.classList.toggle("hidden", tab === "stores");

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
      await mountCustomerQrOverview(panel, { storeId });
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
  const store = storeFromBoot(store_id);
  if (store?.slug) {
    window.location.href = experience_id
      ? `/manage/${encodeURIComponent(store.slug)}/landing-qr`
      : `/manage/${encodeURIComponent(store.slug)}/qr`;
    return;
  }
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
    <h2 class="bos-panel-title">Get started</h2>
    <p class="cp-muted">Add a blank store or set one up with a customer QR in one flow.</p>
    <button type="button" class="bos-btn bos-btn-primary" id="store-empty-setup">Add store</button>`;
  panel.prepend(banner);
  banner.querySelector("#store-empty-setup")?.addEventListener("click", (event) => {
    openAddStoreMenu(event.currentTarget);
  });
}

async function resolveLegacyExperienceHash(raw) {
  const match = raw.match(/^(?:experience|builder)\/(\d+)/);
  if (!match) return false;
  const id = Number(match[1]);
  const builder = raw.startsWith("builder");
  const store = storeFromBoot(parseHash().storeId);
  if (store?.slug) {
    window.location.replace(
      `/manage/${encodeURIComponent(store.slug)}/landing-qr#${builder ? "builder" : "experience"}/${id}`,
    );
    return true;
  }
  try {
    const res = await fetch(`/api/qr-experiences/${id}`, { credentials: "same-origin" });
    if (!res.ok) return false;
    const exp = await res.json();
    const bootStore = window.WORKSPACE_BOOT?.stores?.find((s) => s.id === exp.store_id);
    if (bootStore?.slug) {
      window.location.replace(
        `/manage/${encodeURIComponent(bootStore.slug)}/landing-qr#${builder ? "builder" : "experience"}/${id}`,
      );
      return true;
    }
  } catch {
    /* keep store hub overview */
  }
  return false;
}

export function initStoreHub() {
  const root = document.getElementById("bos-store-hub");
  if (!root) return;

  maybeShowEmptyBanner();

  document.addEventListener("click", (event) => {
    if (
      !event.target.closest("#store-hub-add-menu")
      && !event.target.closest("#store-hub-add")
      && !event.target.closest("#store-empty-setup")
    ) {
      hideAddStoreMenu();
    }
  });

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
  const initial = parseHash();
  const rawHash = (window.location.hash || "").replace(/^#/, "");
  if (rawHash.match(/^(?:experience|builder)\/\d+/)) {
    resolveLegacyExperienceHash(rawHash).then((handled) => {
      if (!handled) mountTab(initial);
    });
  } else {
    mountTab(initial);
  }
}

initStoreHub();
