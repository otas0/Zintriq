#!/usr/bin/env node
/**
 * Verify Zintriq UX audit checklist (static analysis).
 * Run: node scripts/verify_ux_audit.js
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
let pass = 0;
let fail = 0;

function ok(label) {
  pass += 1;
  console.log(`  PASS  ${label}`);
}

function bad(label, detail = "") {
  fail += 1;
  console.log(`  FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
}

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

function includes(rel, needle, label) {
  const text = read(rel);
  if (text.includes(needle)) ok(label);
  else bad(label, `missing in ${rel}`);
}

function excludes(rel, needle, label) {
  const text = read(rel);
  if (!text.includes(needle)) ok(label);
  else bad(label, `found in ${rel}`);
}

console.log("\nZintriq UX Audit Verification\n");

// Navigation
excludes("static/bos/product-focus.js", 'label: "Home"', "Nav: no Home");
includes("static/bos/product-focus.js", 'label: "Stores"', "Nav: Stores");
excludes("static/bos/product-focus.js", 'label: "Responses", icon: "✎", path: "/app/responses"', "Nav: no top-level Responses");
includes("static/bos/product-focus.js", 'label: "Team"', "Nav: Team");
includes("static/bos/product-focus.js", 'label: "Settings"', "Nav: Settings");
includes("static/bos/product-focus.js", "advancedAnalytics: false", "MVP: advanced analytics hidden");
includes("static/bos/product-focus.js", "workflowEngine: false", "MVP: workflow engine hidden");
includes("static/bos/product-focus.js", "plugins: false", "MVP: plugins hidden");

// Shell — no top toolbar; ⌘K command palette lives in shell.html
excludes("templates/bos/shell.html", "partials/toolbar.html", "Shell: toolbar partial removed");
excludes("templates/bos/shell.html", "bos-topbar-workspace-switcher", "Shell: no workspace selector");
excludes("templates/bos/shell.html", "bos-search-trigger", "Shell: no search bar");
excludes("templates/bos/shell.html", "bos-notifications-btn", "Shell: no notifications");
excludes("templates/bos/shell.html", "bos-user-menu", "Shell: no account icon in top bar");
includes("templates/bos/shell.html", "bos-command-palette", "Shell: command palette for ⌘K");
excludes("templates/bos/shell.html", "bos-toolbar--merchant", "Shell: no top toolbar");
excludes("templates/bos/shell.html", "bos-breadcrumbs", "Shell: no breadcrumbs");
excludes("static/bos/core/nav.js", "setBreadcrumbTrail", "Nav: breadcrumbs removed");
excludes("templates/os_base.html", "os-topbar", "OS shell: no sticky top bar");
includes("templates/bos/partials/sidebar.html", 'url_for(\'account\')', "Sidebar: account link kept");
excludes("templates/os_base.html", "QR Experiences", "OS shell: no QR Experiences nav");
excludes("templates/os_base.html", "my_stores", "OS shell: no footer Stores link");
excludes("templates/bos/partials/sidebar.html", "my_stores", "Sidebar: no Stores link");

excludes("templates/bos/partials/sidebar.html", "Home", "Sidebar: no Home link");
excludes("templates/os_base.html", "> Home", "OS shell: no Home nav");
includes("bos/routes.py", 'redirect(url_for("bos.store"))', "Routes: /app redirects to store");

// Store hub
includes("static/bos/features/qr-experiences-page.js", "qrExperienceCard", "QR list: card component");
includes("static/bos/features/qr-experiences-page.js", "bos-builder-grid", "QR editor: 3-column layout");
includes("static/bos/store-hub.js", "experiences", "Store hub: experiences tab");
includes("static/bos/store-hub.js", "responses", "Store hub: responses tab");
includes("static/bos/store-setup-wizard.js", "Set up your store", "Store hub: setup wizard");
includes("templates/bos/store_module.html", "Customer QR", "Store hub: customer QR tab");
includes("templates/bos/store_module.html", "owner/_workspace.html", "Store hub: stores workspace");
includes("static/bos/store-setup-wizard.js", "Set up your store", "Store hub: setup wizard");
includes("static/bos/components/qr/index.js", 'data-act="archive"', "QR card: archive action");

// Responses
includes("static/bos/features/responses-page.js", "/api/responses", "Responses: real API");
includes("static/bos/components/response/index.js", "Source:", "Response card: source label");

// Team
includes("static/bos/features/team-page.js", "/api/team/members", "Team: real members API");
includes("static/bos/features/team-page.js", "MVP_TEAM_ROLES", "Team: MVP roles");
includes("static/bos/features/team-page.js", "Invitations", "Team: invitations section");

// Settings
includes("static/bos/features/workspaces-page.js", "integrationsPlaceholder", "Settings: integrations flag");
includes("static/bos/features/integrations-section.js", "renderIntegrationsPlaceholder", "Settings: integrations placeholder");

// Audit doc
includes("docs/bos/UX_AUDIT.md", "Page-by-Page Audit", "Docs: UX audit written");
includes("docs/bos/MVP_UX_IMPLEMENTATION_PLAN.md", "Phase 1", "Docs: implementation plan");

console.log(`\n${pass} PASS, ${fail} FAIL\n`);
process.exit(fail ? 1 : 0);
