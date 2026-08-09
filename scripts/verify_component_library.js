#!/usr/bin/env node
/** Verify MVP component library exports. */
import { pathToFileURL } from "url";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const componentsUrl = pathToFileURL(path.join(root, "static/bos/components/index.js")).href;

const REQUIRED = [
  "Button", "Card", "StatusBadge", "EmptyState", "Skeleton",
  "openModal", "openDropdown", "Input", "FormActions",
  "PageHeader", "SearchBar", "mountFilterBar", "initWorkspaceSelector",
  "WelcomeBanner", "QuickActionBar", "SettingsNav",
  "QRExperienceCard", "QRPreview", "QRStatus",
  "ResponseCard", "ResponseList", "ResponseDetail",
  "MemberCard", "InviteMemberModal",
  "button", "statusBadge", "emptyState", "loadingState", "pageHeader",
];

const mod = await import(componentsUrl);
let fail = 0;
for (const name of REQUIRED) {
  if (typeof mod[name] !== "function" && typeof mod[name] !== "undefined" && mod[name] == null) {
    console.log(`FAIL  missing export: ${name}`);
    fail++;
  } else if (mod[name] == null) {
    console.log(`FAIL  missing export: ${name}`);
    fail++;
  } else {
    console.log(`PASS  ${name}`);
  }
}

// Smoke render (no mock business data)
const html = mod.QRExperienceCard({
  id: 1,
  name: "Test",
  status: "active",
  type: "feedback",
  total_views: 10,
  response_count: 2,
});
if (!html.includes("Test") || !html.includes("data-id=\"1\"")) {
  console.log("FAIL  QRExperienceCard render");
  fail++;
} else {
  console.log("PASS  QRExperienceCard render");
}

console.log(fail ? `\n${REQUIRED.length - fail} PASS, ${fail} FAIL` : `\n${REQUIRED.length + 1} PASS, 0 FAIL`);
process.exit(fail ? 1 : 0);
