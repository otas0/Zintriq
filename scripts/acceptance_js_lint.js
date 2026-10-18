#!/usr/bin/env node
/**
 * Offline JS acceptance lint for Studio plugins + Electron host.
 * No npm install required — pattern gates only (no-eval, no-new-Function, sandbox unload hooks).
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const FILES = [
  "static/studio/engine.js",
  "static/studio/editor-views.js",
  "static/studio/editors/plugin-kit.js",
  "static/studio/editors/diagram.js",
  "static/studio/editors/pack.js",
  "static/studio/editors/runtimes.js",
  "static/studio/editors/solvers.js",
  "static/studio/workbench.js",
  "desktop/host_prefs.js",
  "static/studio/meta-editor.js",
  "static/studio/zintriq.js",
  "desktop/main.js",
  "desktop/preload.js",
  "desktop/flask_host.js",
  "desktop/scripts/smoke.js",
];

const FORBIDDEN = [
  { re: /\beval\s*\(/, msg: "eval() is forbidden" },
  { re: /\bnew\s+Function\s*\(/, msg: "new Function() is forbidden" },
  { re: /\bFunction\s*\(\s*['"`]/, msg: "Function constructor is forbidden" },
];

const REQUIRED = {
  "static/studio/editor-views.js": ["unregister:", "dispose:", "destroySandbox", "clearHost"],
  "static/studio/editors/plugin-kit.js": ["me-plugin-toolbar", "Insert row", "View marks", "unregisterOwner", "Play", "me-timeline"],
  "static/studio/engine.js": ["unregisterOwner:", "dispose:", "off:"],
  "desktop/scripts/smoke.js": ["ZINTRIQ_SMOKE_COLD_MS", "cold start"],
};

let failed = 0;
for (const rel of FILES) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    console.error(`missing ${rel}`);
    failed += 1;
    continue;
  }
  const text = fs.readFileSync(abs, "utf8");
  for (const rule of FORBIDDEN) {
    if (rule.re.test(text)) {
      console.error(`${rel}: ${rule.msg}`);
      failed += 1;
    }
  }
  const need = REQUIRED[rel];
  if (need) {
    for (const needle of need) {
      if (!text.includes(needle)) {
        console.error(`${rel}: missing required token ${needle}`);
        failed += 1;
      }
    }
  }
}

if (failed) {
  console.error(`acceptance js lint failed (${failed})`);
  process.exit(1);
}
console.log("acceptance js lint ok");
