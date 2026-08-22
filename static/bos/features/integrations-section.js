/** Connected Apps — regional payment & review plugins with merchant setup guides. */

import { showToast, openDrawer, closeDrawer, apiPost } from "../services/api.js";
import { fetchJson, esc } from "../services/bos-api.js";

const STATUS_LABELS = {
  not_connected: "Not Connected",
  connected: "Connected",
  active: "Active",
  disconnected: "Disconnected",
  error: "Error",
  pending: "Pending setup",
  restricted: "Restricted",
};

let catalog = null;

function statusBadgeClass(status) {
  if (status === "active" || status === "connected") return "bos-badge--active";
  if (status === "error" || status === "restricted") return "bos-badge--danger";
  return "bos-badge--muted";
}

function pluginStatus(plugin) {
  if (!plugin.connection) return "not_connected";
  return plugin.connection.status || "connected";
}

function isConnectedStatus(status) {
  return status !== "not_connected" && status !== "disconnected";
}

function isPayment(slug) {
  return catalog?.payments?.some((p) => p.slug === slug);
}

function catalogEntry(slug) {
  return catalog?.payments?.find((p) => p.slug === slug)
    || catalog?.reputation?.find((p) => p.slug === slug);
}

function connectUrl(slug) {
  if (isPayment(slug)) return `/api/integrations/payments/${slug}/connect`;
  return `/api/integrations/reputation/${slug}/connect`;
}

function disconnectUrl(slug) {
  if (isPayment(slug)) return `/api/integrations/payments/${slug}/disconnect`;
  return `/api/integrations/reputation/${slug}/disconnect`;
}

function statusUrl(slug) {
  if (isPayment(slug)) return `/api/integrations/payments/${slug}/status`;
  if (catalog?.reputation?.some((p) => p.slug === slug)) return `/api/integrations/reputation/${slug}/status`;
  return `/api/integrations/connections/${slug}`;
}

function setupGuideHtml(entry) {
  const guide = entry?.setup_guide || {};
  if (!guide.summary && !guide.steps?.length) return "";
  const steps = (guide.steps || []).map((s, i) => `<li>${esc(s)}</li>`).join("");
  const links = (guide.links || []).map((l) =>
    `<a class="ws-merchant-link" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)}</a>`
  ).join("");
  return `
    <div class="ws-integration-guide bos-panel">
      <p class="ws-integration-guide__title"><strong>Owner set up</strong></p>
      <p class="cp-muted ws-integration-guide__summary">${esc(guide.summary || "")}</p>
      ${steps ? `<ol class="cp-muted ws-integration-guide__steps">${steps}</ol>` : ""}
      ${links ? `<div class="ws-merchant-links"><span class="ws-merchant-links__label">Merchant links</span>${links}</div>` : ""}
    </div>`;
}

function credentialFormHtml(entry) {
  const fields = entry?.credential_fields || [];
  return fields.map((f) => {
    if (f.type === "select") {
      const opts = (f.options || []).map((o) =>
        `<option value="${esc(o)}"${o === "live" || o === "production" ? " selected" : ""}>${esc(o)}</option>`
      ).join("");
      return `<div class="bos-field"><label class="bos-label">${esc(f.label)}</label>
        <select class="bos-input" name="${esc(f.key)}" ${f.required ? "required" : ""}>${opts}</select></div>`;
    }
    if (f.type === "textarea") {
      return `<div class="bos-field"><label class="bos-label">${esc(f.label)}</label>
        <textarea class="bos-input" name="${esc(f.key)}" rows="4" spellcheck="false"
          placeholder="${esc(f.placeholder || "")}" ${f.required ? "required" : ""}
          autocomplete="off" style="min-height:88px;font-family:ui-monospace,monospace;font-size:12px"></textarea></div>`;
    }
    return `<div class="bos-field"><label class="bos-label">${esc(f.label)}</label>
      <input class="bos-input" name="${esc(f.key)}" type="${f.type || "text"}"
        placeholder="${esc(f.placeholder || "")}" ${f.required ? "required" : ""} autocomplete="off"></div>`;
  }).join("");
}

function excludedNote() {
  const list = catalog?.excluded_territories || [];
  if (!list.length) return "";
  return `<p class="cp-muted" style="font-size:12px;margin-top:8px">Not available in: ${esc(list.join(", "))}.</p>`;
}

function filterByRegion(items, region) {
  if (!region || region === "all") return items;
  return items.filter((p) => {
    const entry = catalogEntry(p.slug);
    const regions = entry?.regions || p.regions || [];
    return regions.includes(region) || regions.includes("global");
  });
}

function pluginSearchHaystack(plugin) {
  const entry = catalogEntry(plugin.slug);
  return [
    plugin.slug,
    plugin.name,
    plugin.description,
    plugin.provider,
    entry?.name,
    entry?.description,
    ...(entry?.region_labels || []),
    ...(entry?.regions || []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function filterPlugins(items, region, query, scope) {
  const q = (query || "").trim().toLowerCase();
  return filterByRegion(items, region)
    .filter((p) => {
      if (scope === "connected") return isConnectedStatus(pluginStatus(p));
      if (scope === "available") return !isConnectedStatus(pluginStatus(p));
      return true;
    })
    .filter((p) => !q || pluginSearchHaystack(p).includes(q))
    .sort((a, b) => {
      const ac = isConnectedStatus(pluginStatus(a)) ? 0 : 1;
      const bc = isConnectedStatus(pluginStatus(b)) ? 0 : 1;
      if (ac !== bc) return ac - bc;
      const an = (catalogEntry(a.slug)?.name || a.name || "").toLowerCase();
      const bn = (catalogEntry(b.slug)?.name || b.name || "").toLowerCase();
      return an.localeCompare(bn);
    });
}

function regionTabsHtml(active) {
  const regions = catalog?.regions || [];
  const primary = new Set(catalog?.primary_regions || []);
  const global = regions.find((r) => r.id === "global");
  const rest = regions.filter((r) => r.id !== "global").sort((a, b) => {
    const ap = primary.has(a.id) ? 0 : 1;
    const bp = primary.has(b.id) ? 0 : 1;
    return ap - bp || a.label.localeCompare(b.label);
  });
  const sorted = global ? [global, ...rest] : rest;
  return `<div class="ws-region-tabs" role="tablist" aria-label="Regions">
    <button type="button" class="ws-region-tab${active === "all" ? " is-active" : ""}" data-region="all">All regions</button>
    ${sorted.map((r) =>
      `<button type="button" class="ws-region-tab${active === r.id ? " is-active" : ""}" data-region="${esc(r.id)}">${esc(r.label)}</button>`
    ).join("")}
  </div>`;
}

function scopeTabsHtml(active) {
  const items = [
    ["all", "All apps"],
    ["connected", "Connected"],
    ["available", "Not connected"],
  ];
  return `<div class="ws-scope-tabs" role="tablist" aria-label="Connection filter">
    ${items.map(([id, label]) =>
      `<button type="button" class="ws-scope-tab${active === id ? " is-active" : ""}" data-scope="${id}">${label}</button>`
    ).join("")}
  </div>`;
}

function integrationCard(plugin, entry) {
  const status = pluginStatus(plugin);
  const title = entry?.name || plugin.name;
  const connected = isConnectedStatus(status);
  const showCheckout = isPayment(plugin.slug) || plugin.category === "payments" || entry?.checkout_ready || plugin.checkout_ready;
  const checkoutTag = showCheckout ? `<span class="ws-checkout-tag">Checkout</span>` : "";
  const guideReady = Boolean(entry?.setup_guide?.summary && entry?.setup_guide?.links?.length);
  return `<article class="bos-panel ws-integration-card${connected ? " is-connected" : ""}" data-slug="${esc(plugin.slug)}">
    <div class="ws-integration-card__head">
      <div class="ws-integration-card__copy">
        <div class="ws-integration-card__title-row">
          <h3 class="bos-panel-title" style="margin:0">${esc(title)}</h3>
          ${checkoutTag}
        </div>
        <p class="cp-muted ws-integration-card__desc">${esc(plugin.description)}</p>
        ${entry?.region_labels?.length ? `<p class="cp-muted ws-integration-card__regions">${esc(entry.region_labels.slice(0, 4).join(" · "))}</p>` : ""}
      </div>
    </div>
    <div class="ws-integration-card__meta">
      <span class="bos-badge ${statusBadgeClass(status)}">${esc(STATUS_LABELS[status] || status)}</span>
      ${guideReady ? `<span class="ws-setup-pill">Setup guide</span>` : ""}
    </div>
    <div class="ws-integration-card__actions">
      <button type="button" class="bos-btn ${connected ? "bos-btn-ghost" : "bos-btn-primary"} bos-btn-sm"
        data-${connected ? "manage" : "connect"}="${esc(plugin.slug)}">${connected ? "Manage" : "Set up"}</button>
    </div>
  </article>`;
}

function oauthStartUrl(slug) {
  if (isPayment(slug)) return `/api/integrations/payments/${slug}/oauth/start`;
  return `/api/integrations/reputation/${slug}/oauth/start`;
}

async function startOauth(slug, title) {
  const data = await fetchJson(oauthStartUrl(slug));
  if (data.auth_url) {
    window.location.href = data.auth_url;
    return;
  }
  throw new Error(data.error || `Could not start ${title} sign-in`);
}

async function openConnectDrawer(slug, onChange) {
  const entry = catalogEntry(slug);
  const title = entry?.name || slug;
  const oauthOnly = Boolean(entry?.oauth_required) && !entry?.credential_fields?.length;
  const oauthAndFields = Boolean(entry?.oauth_required) && entry?.credential_fields?.length;
  openDrawer(`Set up ${title}`, `
    ${setupGuideHtml(entry)}
    ${excludedNote()}
    ${entry?.oauth_required ? `
      <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="plugin-oauth" style="margin-bottom:12px">
        Connect with ${esc(title)}
      </button>
      <p class="cp-muted" style="margin:0 0 12px;font-size:12px">Sign in as the business owner. A public listing ID is not enough.</p>` : ""}
    ${oauthOnly ? "" : `<form id="plugin-cred-form" class="cp-profile">${credentialFormHtml(entry)}
      <button type="submit" class="bos-btn ${oauthAndFields ? "bos-btn-ghost" : "bos-btn-primary"} bos-btn-sm" style="margin-top:12px">Save &amp; verify</button>
    </form>
    <p class="cp-muted" style="margin-top:12px;font-size:12px">Credentials are encrypted and never shared with other merchants.</p>`}
  `);

  document.getElementById("plugin-oauth")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await startOauth(slug, title);
    } catch (err) {
      showToast(err.message || "Could not start sign-in", { type: "error" });
      btn.disabled = false;
    }
  });

  document.getElementById("plugin-cred-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const body = Object.fromEntries(new FormData(form).entries());
    const btn = form.querySelector('[type="submit"]');
    btn.disabled = true;
    try {
      await apiPost(connectUrl(slug), body);
      showToast(`${title} connected`);
      closeDrawer();
      onChange?.();
    } catch (err) {
      showToast(err.message || "Could not verify credentials", { type: "error" });
      btn.disabled = false;
    }
  });
}

function accountStatusLines(status, slug) {
  const lines = [];
  const pay = status.payment || {};
  const mode = pay.metadata?.connect_mode;
  if (mode === "api_credentials") lines.push("Connected with verified API credentials");
  if (status.external_account_id) lines.push(`ID: ${esc(status.external_account_id)}`);
  if (status.external_account_email) lines.push(`Account: ${esc(status.external_account_email)}`);
  if (pay.charges_enabled) lines.push("Ready to accept payments");
  if (pay.livemode === true) lines.push("Live — customers pay for real");
  if (isPayment(slug) && mode === "api_credentials") lines.push("Live checkout — customers pay on this provider");
  if (!lines.length) lines.push("Account linked");
  return lines.map((l) => `<p class="cp-muted">${l}</p>`).join("");
}

async function openManageDrawer(slug, onChange) {
  const entry = catalogEntry(slug);
  const title = entry?.name || slug;
  const status = await fetchJson(statusUrl(slug));
  const connected = status.connected;

  openDrawer(title, `
    <div class="cp-profile">
      <p><span class="bos-badge ${statusBadgeClass(status.status || "not_connected")}">${esc(STATUS_LABELS[status.status] || status.status || "Not Connected")}</span></p>
      ${connected ? accountStatusLines(status, slug) : setupGuideHtml(entry)}
      ${connected ? setupGuideHtml(entry) : ""}
      ${status.recent_logs?.length ? `
        <h4 class="bos-drawer-section">Activity</h4>
        <ul class="bos-timeline">${status.recent_logs.slice(0, 6).map((l) =>
          `<li>${esc(l.event_type)} — ${esc(l.status)}</li>`
        ).join("")}</ul>` : ""}
      ${connected ? `
        <button type="button" class="bos-btn bos-btn-ghost bos-btn-sm" id="acct-update" style="margin-top:12px">Update credentials</button>
        ${!isPayment(slug) ? `<button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="acct-sync" style="margin-top:8px">Sync reviews</button>` : ""}
        <button type="button" class="bos-btn bos-btn-danger bos-btn-sm" id="acct-disconnect" style="margin-top:16px">Disconnect</button>` : `
        <button type="button" class="bos-btn bos-btn-primary bos-btn-sm" id="acct-connect" style="margin-top:12px">Set up ${esc(title)}</button>`}
    </div>
  `);

  document.getElementById("acct-connect")?.addEventListener("click", () => {
    closeDrawer();
    openConnectDrawer(slug, onChange);
  });
  document.getElementById("acct-update")?.addEventListener("click", () => {
    closeDrawer();
    openConnectDrawer(slug, onChange);
  });
  document.getElementById("acct-sync")?.addEventListener("click", async () => {
    try {
      const result = await apiPost(`/api/feedback/plugins/${slug}/sync`, {});
      showToast(result.note || `Synced ${result.synced ?? 0} review(s)`);
      closeDrawer();
      onChange?.();
    } catch (err) {
      showToast(err.message || "Sync failed", { type: "error" });
    }
  });
  document.getElementById("acct-disconnect")?.addEventListener("click", async () => {
    if (!window.confirm(`Disconnect ${title}?`)) return;
    await apiPost(disconnectUrl(slug), {});
    showToast("Disconnected");
    closeDrawer();
    onChange?.();
  });
}

function emptyPluginMessage(region, query, scope) {
  const q = (query || "").trim();
  if (q && region && region !== "all") {
    return `No plugins match “${esc(q)}” in this region.`;
  }
  if (q) return `No plugins match “${esc(q)}”.`;
  if (scope === "connected") return "No connected apps yet. Set up a payment or review plugin below.";
  return "No plugins in this region. Try All regions or another tab.";
}

function renderPluginGrid(list, region, query, scope) {
  if (!list.length) {
    return `<p class="cp-muted">${emptyPluginMessage(region, query, scope)}</p>`;
  }
  return `<div class="ws-integration-grid">${list.map((plugin) =>
    integrationCard(plugin, catalogEntry(plugin.slug))
  ).join("")}</div>`;
}

/** @param {HTMLElement} container */
export async function renderIntegrationsSection(container) {
  container.innerHTML = `<div class="bos-loading">Loading integrations…</div>`;
  try {
    const [pluginsData, cat] = await Promise.all([
      fetchJson("/api/integrations/plugins"),
      fetchJson("/api/integrations/catalog"),
    ]);
    catalog = cat;
    let region = "all";
    let scope = "all";
    let query = "";
    let plugins = pluginsData;

    let paymentPlugins = plugins.filter((p) => cat.payments?.some((x) => x.slug === p.slug));
    let reputationPlugins = plugins.filter((p) => cat.reputation?.some((x) => x.slug === p.slug));

    const applyPluginLists = (next) => {
      plugins = next;
      paymentPlugins = plugins.filter((p) => cat.payments?.some((x) => x.slug === p.slug));
      reputationPlugins = plugins.filter((p) => cat.reputation?.some((x) => x.slug === p.slug));
    };

    const refreshAfterChange = async () => {
      try {
        const next = await fetchJson("/api/integrations/plugins");
        applyPluginLists(next);
        paintGrids();
      } catch (err) {
        showToast(err.message || "Could not refresh integrations", { type: "error" });
        render();
      }
    };

    const paintGrids = () => {
      const payList = filterPlugins(paymentPlugins, region, query, scope);
      const repList = filterPlugins(reputationPlugins, region, query, scope);
      const payCount = container.querySelector("#pay-count");
      const repCount = container.querySelector("#rep-count");
      const connectedN = [...paymentPlugins, ...reputationPlugins].filter((p) => isConnectedStatus(pluginStatus(p))).length;
      const summary = container.querySelector("#integration-summary");
      if (summary) {
        summary.textContent = `${plugins.length} apps · ${connectedN} connected · search & filter by region`;
      }
      if (payCount) payCount.textContent = `(${payList.length})`;
      if (repCount) repCount.textContent = `(${repList.length})`;
      const payGrid = container.querySelector("#pay-grid");
      const repGrid = container.querySelector("#rep-grid");
      const paySection = container.querySelector("#pay-section");
      const repSection = container.querySelector("#rep-section");
      if (payGrid) payGrid.innerHTML = renderPluginGrid(payList, region, query, scope);
      if (repGrid) repGrid.innerHTML = renderPluginGrid(repList, region, query, scope);
      if (paySection) paySection.hidden = scope === "connected" && !payList.length && !!repList.length;
      if (repSection) repSection.hidden = scope === "connected" && !repList.length && !!payList.length;
      bindActions();
    };

    const render = () => {
      container.innerHTML = `
        <section class="bos-panel ws-integrations-hero">
          <div class="bos-panel-head ws-integrations-toolbar">
            <div>
              <h2 class="bos-panel-title">Connected Apps</h2>
              <p class="cp-muted" id="integration-summary" style="margin:4px 0 0;font-size:13px"></p>
            </div>
            <input type="search" class="bos-input bos-input-sm ws-plugin-search" id="plugin-search"
              placeholder="Search PayTabs, FPS, Stripe…" value="${esc(query)}" autocomplete="off"
              aria-label="Search plugins">
          </div>
          <p class="cp-muted ws-integrations-blurb">Add your own merchant credentials. Each connection is verified with the provider before it activates.</p>
          ${excludedNote()}
          ${scopeTabsHtml(scope)}
        </section>
        ${regionTabsHtml(region)}
        <section id="pay-section">
          <h3 class="bos-section-label" style="margin:16px 0 12px">Payments <span class="cp-muted" id="pay-count" style="font-weight:normal"></span></h3>
          <div id="pay-grid"></div>
        </section>
        <section id="rep-section">
          <h3 class="bos-section-label" style="margin:24px 0 12px">Reviews <span class="cp-muted" id="rep-count" style="font-weight:normal"></span></h3>
          <div id="rep-grid"></div>
        </section>`;

      container.querySelectorAll(".ws-region-tab").forEach((btn) => {
        btn.addEventListener("click", () => {
          region = btn.dataset.region;
          container.querySelectorAll(".ws-region-tab").forEach((tab) => {
            tab.classList.toggle("is-active", tab.dataset.region === region);
          });
          paintGrids();
        });
      });
      container.querySelectorAll(".ws-scope-tab").forEach((btn) => {
        btn.addEventListener("click", () => {
          scope = btn.dataset.scope;
          container.querySelectorAll(".ws-scope-tab").forEach((tab) => {
            tab.classList.toggle("is-active", tab.dataset.scope === scope);
          });
          paintGrids();
        });
      });
      container.querySelector("#plugin-search")?.addEventListener("input", (e) => {
        query = e.target.value;
        paintGrids();
      });
      paintGrids();
    };

    const bindActions = () => {
      container.querySelectorAll("[data-connect]").forEach((btn) => {
        btn.addEventListener("click", () => openConnectDrawer(btn.dataset.connect, refreshAfterChange));
      });
      container.querySelectorAll("[data-manage]").forEach((btn) => {
        btn.addEventListener("click", () => openManageDrawer(btn.dataset.manage, refreshAfterChange));
      });
    };

    render();
  } catch (err) {
    container.innerHTML = `<div class="bos-empty"><p class="bos-empty__title">Could not load integrations</p><p>${esc(err.message)}</p></div>`;
  }
}

export async function renderIntegrationsPlaceholder(container) {
  container.innerHTML = `
    <section class="bos-panel">
      <h2 class="bos-panel-title">Integrations</h2>
      <p class="cp-muted">Regional payment and review plugins for merchants worldwide.</p>
    </section>`;
}
