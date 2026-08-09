/** Business domain — home & settings helpers. */

import { esc } from "../ui/_utils.js";

export function WelcomeBanner({ greeting, businessName, hint = "" }) {
  return `<section class="merchant-welcome bos-ui-welcome">
    <h2 class="merchant-welcome__title">${esc(greeting)}, ${esc(businessName)}</h2>
    <p class="merchant-welcome__hint">${esc(hint || "Your business activity today")}</p>
  </section>`;
}

export const welcomeBanner = WelcomeBanner;

export function QuickActionBar(actions) {
  return `<div class="merchant-quick-actions bos-ui-quick-actions">
    ${actions.map((a) => `
      <a class="merchant-quick-action merchant-quick-action--${a.variant || "primary"}" href="${esc(a.href)}">
        ${a.icon ? `<span class="merchant-quick-action__icon">${a.icon}</span>` : ""}
        <span>${esc(a.label)}</span>
      </a>`).join("")}
  </div>`;
}

export const quickActionBar = QuickActionBar;

export function SettingsNav(sections, active) {
  return `<nav class="merchant-settings-nav bos-ui-settings-nav" aria-label="Settings">
    ${sections.map((s) => `
      <button type="button" class="merchant-settings-nav__item${s.id === active ? " is-active" : ""}" data-section="${esc(s.id)}">
        <span class="merchant-settings-nav__label">${esc(s.label)}</span>
        ${s.hint ? `<span class="merchant-settings-nav__hint">${esc(s.hint)}</span>` : ""}
      </button>`).join("")}
  </nav>`;
}

export const settingsNav = SettingsNav;

export { mountCardGrid as renderMerchantGrid, CardGrid } from "../ui/Card.js";
