import { api, toast } from "./universal-api.js";

const list = document.getElementById("ub-marketplace-list");
const search = document.getElementById("ub-marketplace-search");
const dialog = document.getElementById("ub-marketplace-dialog");
const dialogContent = document.getElementById("ub-marketplace-dialog-content");
let activeType = "";

const esc = (value = "") => { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; };
const typeLabel = (value = "") => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function card(item) {
  return `<article class="ub-card ub-market-card ub-market-card--network" data-package-card="${esc(item.id)}">
    <div class="ub-market-card__cover ub-market-card__cover--${esc(item.package_type)}"><span>${esc(typeLabel(item.package_type))}</span></div>
    <div class="ub-market-card__body"><div class="ub-market-card__badges"><span class="ub-badge ${item.trust_level === "official" ? "ub-badge--official" : ""}">${item.trust_level === "official" ? "Official" : "Community"}</span><span class="ub-badge">v${esc(item.version)}</span></div>
    <h2>${esc(item.name)}</h2><p>${esc(item.description || "Reusable Builder creation")}</p>
    <div class="ub-market-creator"><span>${esc(item.creator?.display_name || item.publisher)}</span><small>${item.install_count} installs · ${item.remix_count} remixes</small></div></div>
    <button class="ub-btn ub-btn--primary" data-view-package="${esc(item.id)}">View creation</button>
  </article>`;
}

async function load() {
  list.innerHTML = '<div class="ub-loading">Finding useful creations…</div>';
  const params = new URLSearchParams(); if (search.value.trim()) params.set("q", search.value.trim()); if (activeType) params.set("type", activeType);
  try {
    const { packages } = await api.marketplacePackages(params.toString());
    list.innerHTML = packages.map(card).join("") || '<div class="ub-card ub-empty-panel"><strong>No matching creations</strong><p>Try a broader search or another category.</p></div>';
    list.querySelectorAll("[data-view-package]").forEach((button) => button.addEventListener("click", () => showDetail(button.dataset.viewPackage)));
  } catch (error) { list.innerHTML = `<div class="ub-card ub-empty-panel"><strong>Community unavailable</strong><p>${esc(error.message)}</p></div>`; }
}

async function showDetail(packageId) {
  dialogContent.innerHTML = '<div class="ub-loading">Loading package details…</div>'; dialog.showModal();
  try {
    const item = await api.marketplacePackage(packageId);
    const canRemix = item.usage_rights.includes("remix") && item.package_type === "template";
    dialogContent.innerHTML = `<div class="ub-dialog__head"><div><p class="ub-eyebrow">${esc(typeLabel(item.package_type))} · v${esc(item.version)}</p><h2>${esc(item.name)}</h2></div><button class="ub-icon-btn" data-close>×</button></div>
      <div class="ub-package-detail"><section><p class="ub-package-lead">${esc(item.description)}</p><div class="ub-package-preview"><strong>Safe package preview</strong><p>${item.package_type === "template" ? "A complete editable Universal Project with its connected surfaces and capabilities." : "A declarative reusable resource that becomes part of your Project after installation."}</p></div>
      <h3>Requirements</h3><div class="ub-template-capabilities">${(item.required_capabilities || []).map((value) => `<span>${esc(value)}</span>`).join("") || "<span>No extra capabilities</span>"}</div>
      <h3>Permissions</h3><p>${(item.permissions || []).length ? item.permissions.map(esc).join(" · ") : "No privileged permissions requested."}</p>
      <h3>Release notes</h3><p>${esc(item.release_notes || "No release notes supplied.")}</p></section>
      <aside class="ub-card"><span class="ub-badge ${item.creator?.official ? "ub-badge--official" : ""}">${item.creator?.official ? "Official publisher" : "Creator"}</span><h3>${esc(item.creator?.display_name || item.publisher)}</h3><p>@${esc(item.creator?.handle || "creator")}</p><button class="ub-btn" data-follow>${item.creator?.following ? "Following" : "Follow creator"}</button><hr><p><strong>Usage rights</strong><br>${item.usage_rights.map(typeLabel).join(" · ")}</p><button class="ub-btn" data-save>${item.saved ? "Saved" : "Save"}</button>${canRemix ? '<button class="ub-btn ub-btn--primary" data-remix>Remix template</button>' : '<a class="ub-btn ub-btn--primary" href="/app/builder">Open Builder to install</a>'}<button class="ub-danger-link" data-report>Report</button></aside></div>`;
    dialogContent.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialogContent.querySelector("[data-save]").addEventListener("click", async (event) => { const result = await api.savePackage(item.id); event.target.textContent = result.saved ? "Saved" : "Save"; });
    dialogContent.querySelector("[data-follow]").addEventListener("click", async (event) => { const result = await api.followCreator(item.creator.id); event.target.textContent = result.following ? "Following" : "Follow creator"; });
    dialogContent.querySelector("[data-report]").addEventListener("click", () => reportDialog(item.id, item.name));
    dialogContent.querySelector("[data-remix]")?.addEventListener("click", async (event) => { event.target.disabled = true; event.target.textContent = "Creating remix…"; try { const result = await api.remixPackage(item.id, { name: `My ${item.name}` }); location.href = `/app/builder/${result.project_id}`; } catch (error) { event.target.disabled = false; event.target.textContent = "Remix template"; toast(error.message, "error"); } });
  } catch (error) { dialogContent.innerHTML = `<div class="ub-empty-panel"><strong>Could not open this creation</strong><p>${esc(error.message)}</p><button class="ub-btn" onclick="this.closest('dialog').close()">Close</button></div>`; }
}

function reportDialog(packageId, name) {
  const reasons = [["spam", "Spam"], ["malicious", "Malicious package"], ["copyright", "Copyright issue"], ["misleading", "Misleading content"], ["unsafe", "Unsafe content"], ["privacy", "Privacy / data exposure"], ["broken", "Broken package"]];
  dialogContent.innerHTML = `<div class="ub-dialog__head"><div><p class="ub-eyebrow">Report</p><h2>${esc(name)}</h2></div><button class="ub-icon-btn" data-back>×</button></div><p>Reports go to moderation with the package's evidence and status. A single report never removes content automatically.</p><label class="ub-field">Reason<select id="ub-report-reason">${reasons.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label><label class="ub-field">Details (optional)<textarea id="ub-report-details" placeholder="Add anything that helps moderators"></textarea></label><div class="ub-dialog__actions"><button class="ub-btn" data-back>Cancel</button><button class="ub-btn ub-btn--primary" data-confirm-report>Submit report</button></div>`;
  dialogContent.querySelectorAll("[data-back]").forEach((button) => button.addEventListener("click", () => showDetail(packageId)));
  dialogContent.querySelector("[data-confirm-report]").addEventListener("click", async (event) => { event.target.disabled = true; event.target.textContent = "Submitting…"; try { await api.reportPackage(packageId, { reason: document.getElementById("ub-report-reason").value, details: document.getElementById("ub-report-details").value.trim() }); dialog.close(); toast("Report submitted for review"); } catch (error) { event.target.disabled = false; event.target.textContent = "Submit report"; toast(error.message, "error"); } });
}

document.querySelectorAll("[data-market-type]").forEach((button) => button.addEventListener("click", () => { activeType = button.dataset.marketType; document.querySelectorAll("[data-market-type]").forEach((item) => item.classList.toggle("is-active", item === button)); load(); }));
document.getElementById("ub-marketplace-search-button").addEventListener("click", load);
search.addEventListener("keydown", (event) => { if (event.key === "Enter") load(); });
load();
