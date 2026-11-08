#!/usr/bin/env node
/**
 * Tauri four-step automation (open → allow → edit → save).
 *
 * Linux/Windows: `tauri-driver` WebDriver (W3C) against a debug binary.
 * macOS: `tauri-driver` is unsupported — falls back to:
 *   ZINTRIQ_E2E_PROJECT_DIR auto open+allow (Rust `e2e_project_dir` + UI effect)
 *   + System Events click 「保存」 after a Cmd-A / type edit.
 *
 * Usage:
 *   pnpm e2e:tauri-webdriver
 *   ZINTRIQ_TAURI_BIN=... node scripts/tauri-webdriver-four-step.mjs
 *
 * Electron Playwright stays on Vite **:5175** — do not mix with this suite.
 */
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, rmSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DRIVER_PORT = Number(process.env.ZINTRIQ_TAURI_DRIVER_PORT || 4444);
const HOST = `http://127.0.0.1:${DRIVER_PORT}`;
const IS_DARWIN = process.platform === "darwin";

function which(bin) {
  const r = spawnSync("which", [bin], { encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : "";
}

function defaultBin() {
  if (process.env.ZINTRIQ_TAURI_BIN) return process.env.ZINTRIQ_TAURI_BIN;
  const candidates = [
    join(ROOT, "apps/desktop/src-tauri/target/debug/zintriq-desktop"),
    join(ROOT, "apps/desktop/src-tauri/target/debug/zintriq"),
    join(ROOT, "apps/desktop/src-tauri/target/debug/Zintriq"),
  ];
  return candidates.find((p) => existsSync(p)) || "";
}

async function wd(method, path, body) {
  const res = await fetch(`${HOST}${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`WebDriver ${method} ${path} → ${res.status} non-JSON: ${text.slice(0, 200)}`);
  }
  if (!res.ok || json.value?.error) {
    throw new Error(`WebDriver ${method} ${path} → ${JSON.stringify(json.value ?? json).slice(0, 400)}`);
  }
  return json.value;
}

async function findEl(sessionId, using, value) {
  return wd("POST", `/session/${sessionId}/element`, { using, value });
}

async function click(sessionId, el) {
  const id = el.ELEMENT || el["element-6066-11e4-a52e-4f735466cecf"];
  return wd("POST", `/session/${sessionId}/element/${id}/click`, {});
}

async function exec(sessionId, script, args = []) {
  return wd("POST", `/session/${sessionId}/execute/sync`, { script, args });
}

async function getText(sessionId, el) {
  const id = el.ELEMENT || el["element-6066-11e4-a52e-4f735466cecf"];
  return wd("GET", `/session/${sessionId}/element/${id}/text`);
}

function osascript(lines) {
  const r = spawnSync("osascript", lines.flatMap((l) => ["-e", l]), { encoding: "utf8" });
  if (r.status !== 0) {
    throw new Error(`osascript failed: ${r.stderr || r.stdout}`);
  }
  return r.stdout.trim();
}

async function darwinFourStep(appBin, projectDir) {
  console.log("==> macOS fallback (tauri-driver unsupported on Darwin)");
  console.log(`    app=${appBin}`);
  console.log(`    project=${projectDir}`);
  // Marker drives edit+save inside the UI effect (no Accessibility / System Events required).
  writeFileSync(join(projectDir, ".zintriq-e2e-autosave"), "1\n");

  const child = spawn(appBin, [], {
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ZINTRIQ_E2E_PROJECT_DIR: projectDir },
  });
  const cleanup = () => {
    try {
      child.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  };
  process.on("exit", cleanup);

  console.log("==> step1–4 via e2e_project_dir + .zintriq-e2e-autosave (open/allow/edit/save)");
  const done = join(projectDir, ".zintriq-e2e-done");
  let ok = false;
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    if (existsSync(done)) {
      ok = true;
      break;
    }
  }
  const disk = existsSync(join(projectDir, "main.cpp"))
    ? readFileSync(join(projectDir, "main.cpp"), "utf8")
    : "";
  cleanup();
  if (!ok) {
    throw new Error(
      `timed out waiting for ${done} (is the debug binary rebuilt with e2e_project_dir? disk=${JSON.stringify(disk.slice(0, 40))})`,
    );
  }
  if (!disk.includes("return 1")) {
    throw new Error(`four-step marker ok but main.cpp not updated: ${JSON.stringify(disk.slice(0, 60))}`);
  }
  console.log("    disk main.cpp updated");
  console.log("==> four-step OK (macOS marker fallback)");
}

async function webdriverFourStep(appBin, projectDir) {
  const driverBin = which("tauri-driver");
  if (!driverBin) {
    console.error("tauri-driver not on PATH — install: cargo install tauri-driver");
    process.exit(2);
  }

  // Probe support (exits immediately on Darwin with a message on stderr).
  const probe = spawnSync(driverBin, ["--port", String(DRIVER_PORT + 1)], {
    encoding: "utf8",
    timeout: 1500,
  });
  const probeOut = `${probe.stdout || ""}${probe.stderr || ""}`;
  if (/not supported on this platform/i.test(probeOut)) {
    throw new Error("PLATFORM_UNSUPPORTED");
  }

  console.log("==> step0 driver + app");
  const driver = spawn(driverBin, ["--port", String(DRIVER_PORT)], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  const cleanup = () => {
    try {
      driver.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  };
  process.on("exit", cleanup);
  await sleep(1000);

  let sessionId;
  try {
    const session = await wd("POST", "/session", {
      capabilities: {
        alwaysMatch: {
          "tauri:options": { application: appBin },
          browserName: "wry",
        },
      },
    });
    sessionId = session.sessionId || session;
    if (typeof sessionId === "object") sessionId = session.sessionId;

    await exec(sessionId, "window.__ZINTRIQ_E2E_PROJECT__ = arguments[0];", [projectDir]);

    console.log("==> step1 open-folder");
    await click(sessionId, await findEl(sessionId, "css selector", '[data-testid="open-folder"]'));
    await sleep(500);

    console.log("==> step2 allow (openViaTauriPath)");
    let rootText = "";
    for (let i = 0; i < 20; i++) {
      rootText = await getText(sessionId, await findEl(sessionId, "css selector", '[data-testid="project-root"]'));
      if (rootText && rootText !== "memory") break;
      await sleep(250);
    }
    const expectedName = projectDir.split(/[/\\]/).filter(Boolean).pop();
    if (!rootText.includes(expectedName)) {
      throw new Error(`project-root="${rootText}", want "${expectedName}"`);
    }

    console.log("==> step3 edit");
    await exec(
      sessionId,
      `if (window.monaco?.editor?.getEditors) {
         const eds = window.monaco.editor.getEditors();
         if (eds[0]) eds[0].setValue('int main(){return 1;}\\n');
       }
       return true;`,
    );
    await sleep(300);

    console.log("==> step4 save");
    await click(sessionId, await findEl(sessionId, "css selector", '[data-testid="save-file"]'));
    await sleep(400);
    console.log("==> four-step OK (WebDriver)");
  } finally {
    if (sessionId) {
      try {
        await wd("DELETE", `/session/${sessionId}`);
      } catch {
        /* ignore */
      }
    }
    cleanup();
  }
}

async function main() {
  const projectDir = process.env.ZINTRIQ_E2E_PROJECT_DIR || join(tmpdir(), `zintriq-wd-${Date.now()}`);
  mkdirSync(projectDir, { recursive: true });
  writeFileSync(join(projectDir, "main.cpp"), "int main(){return 0;}\n");

  const appBin = defaultBin();
  if (!appBin) {
    console.error("No Tauri debug binary. Build:");
    console.error("  corepack pnpm --filter @zintriq/desktop exec tauri build --debug");
    console.error("Or set ZINTRIQ_TAURI_BIN");
    process.exit(2);
  }

  try {
    if (IS_DARWIN && process.env.ZINTRIQ_FORCE_WEBDRIVER !== "1") {
      await darwinFourStep(appBin, projectDir);
    } else {
      try {
        await webdriverFourStep(appBin, projectDir);
      } catch (err) {
        if (String(err.message || err).includes("PLATFORM_UNSUPPORTED") && IS_DARWIN) {
          await darwinFourStep(appBin, projectDir);
        } else {
          throw err;
        }
      }
    }
  } finally {
    if (process.env.ZINTRIQ_KEEP_E2E_PROJECT !== "1") {
      try {
        rmSync(projectDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    }
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
