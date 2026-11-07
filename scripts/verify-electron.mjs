#!/usr/bin/env node
/**
 * Electron Playwright e2e gate for @zintriq/desktop.
 * Exit codes:
 *   0 — all tests passed
 *   2 — Electron / Playwright launch failure
 *   3 — UI assertion / timeout (e.g. monaco never visible)
 *   1 — other failure
 * Usage: corepack pnpm verify:electron
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const result = spawnSync(
  "corepack",
  ["pnpm", "--filter", "@zintriq/desktop", "exec", "playwright", "test", "--reporter=line"],
  {
    cwd: root,
    env: process.env,
    encoding: "utf8",
  },
);

const stdout = result.stdout ?? "";
const stderr = result.stderr ?? "";
const combined = `${stdout}\n${stderr}`;
process.stdout.write(stdout);
process.stderr.write(stderr);

if (result.status === 0) {
  console.log("\nverify:electron ok");
  process.exit(0);
}

const launchFail =
  /electron\.launch|Executable doesn't exist|browserType\.launch|Target closed|SIGABRT|app failed to start|Could not find Electron|spawn .* ENOENT|Error: spawn|Electron failed to start/i.test(
    combined,
  );

const uiAssert =
  /\.monaco-editor|toBeVisible|toHaveTitle|toHaveText|Test timeout of|Timed out \d+ms waiting for|expect\(locator\)/i.test(
    combined,
  );

// Launch failures take priority over generic assertion text that may also appear.
if (launchFail) {
  console.error("\nverify:electron: Electron launch failure (exit 2)");
  process.exit(2);
}
if (uiAssert) {
  console.error("\nverify:electron: UI assertion / timeout (exit 3)");
  process.exit(3);
}

console.error(`\nverify:electron failed with exit ${result.status ?? 1}`);
process.exit(result.status ?? 1);
