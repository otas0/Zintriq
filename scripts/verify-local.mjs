#!/usr/bin/env node
/**
 * Local gate without Electron e2e: workspace build/test + Tauri cargo check
 * + core-service /health + sha256sums + real clangd stdio smoke.
 * Electron Playwright lives in `pnpm verify:electron` (exit 2 = launch, 3 = UI).
 * Usage: corepack pnpm verify:local
 */
import { spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function run(label, command, args, opts = {}) {
  console.log(`\n==> ${label}`);
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    env: process.env,
    ...opts,
  });
  if (result.status !== 0) {
    console.error(`${label} failed with exit ${result.status ?? 1}`);
    process.exit(result.status ?? 1);
  }
}

function freePort(port) {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function withCoreService(fn) {
  const busy = !(await freePort(4317));
  if (!busy) {
    console.log("\n==> start core-service :4317");
    const { spawn } = await import("node:child_process");
    const proc = spawn("corepack", ["pnpm", "--filter", "@zintriq/core-service", "start"], {
      cwd: root,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    // Wait for health
    const started = Date.now();
    let ok = false;
    while (Date.now() - started < 20_000) {
      try {
        const res = await fetch("http://127.0.0.1:4317/health");
        if (res.ok) {
          ok = true;
          break;
        }
      } catch {
        /* retry */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    if (!ok) {
      proc.kill("SIGTERM");
      console.error("core-service failed to become healthy");
      process.exit(1);
    }
    try {
      await fn();
    } finally {
      proc.kill("SIGTERM");
    }
    return;
  }
  console.log("\n==> reuse existing core-service on :4317");
  await fn();
}

run("workspace build", "corepack", ["pnpm", "run", "build"]);
run("desktop unit tests", "corepack", ["pnpm", "--filter", "@zintriq/desktop", "test"]);
run("tauri cargo check", "cargo", ["check"], {
  cwd: path.join(root, "apps/desktop/src-tauri"),
});

await withCoreService(async () => {
  const health = await fetch("http://127.0.0.1:4317/health").then((r) => r.json());
  if (health.status !== "ok") {
    console.error("health not ok", health);
    process.exit(1);
  }
  console.log("core-service /health", health.status, health.version ?? "");
  const boards = await fetch("http://127.0.0.1:4317/boards").then((r) => r.json());
  const list = Array.isArray(boards) ? boards : boards.boards;
  if (!Array.isArray(list) || list.length < 1) {
    console.error("boards empty", boards);
    process.exit(1);
  }
  console.log(`core-service /boards count=${list.length}`);
});

run("sha256sums unit tests", "python3", ["-m", "unittest", "desktop.packaging.test_sha256sums"]);
run("clangd stdio smoke", "node", ["scripts/clangd-stdio-smoke.mjs"]);
console.log("\nverify:local ok (Electron e2e: pnpm verify:electron)");
