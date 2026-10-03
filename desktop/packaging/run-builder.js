#!/usr/bin/env node
/**
 * Run electron-builder with a resolved Python interpreter available as `python`.
 * Callers do not need a `python` binary on PATH.
 */
const { execSync, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const desktopDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopDir, "..");

function which(cmd) {
  try {
    const output = execSync(process.platform === "win32" ? `where ${cmd}` : `command -v ${cmd}`, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    return output.trim().split(/\r?\n/)[0];
  } catch {
    return "";
  }
}

function resolvePython() {
  const win = process.platform === "win32";
  const rel = win ? ["Scripts", "python.exe"] : ["bin", "python"];
  const candidates = [];
  if (process.env.ZINTRIQ_PYTHON) candidates.push(process.env.ZINTRIQ_PYTHON);
  if (process.env.VIRTUAL_ENV) candidates.push(path.join(process.env.VIRTUAL_ENV, ...rel));
  candidates.push(path.join(repoRoot, ".venv", ...rel));
  for (const item of candidates) {
    if (item && fs.existsSync(item)) return path.resolve(item);
  }
  return which(win ? "python" : "python3") || which("python3") || which("python") || "";
}

function writeShim(python, shimDir) {
  if (process.platform === "win32") {
    const cmd = path.join(shimDir, "python.cmd");
    fs.writeFileSync(cmd, `@echo off\r\n"${python}" %*\r\n`);
    const bat = path.join(shimDir, "python.bat");
    fs.writeFileSync(bat, `@echo off\r\n"${python}" %*\r\n`);
    try {
      fs.copyFileSync(python, path.join(shimDir, "python.exe"));
    } catch {
      /* cmd shim is enough when copy of a launcher fails */
    }
    return;
  }
  const dest = path.join(shimDir, "python");
  const quoted = python.replace(/'/g, `'\\''`);
  fs.writeFileSync(dest, `#!/bin/sh\nexec '${quoted}' "$@"\n`, { mode: 0o755 });
}

function main() {
  const python = resolvePython();
  if (!python) {
    console.error("No Python interpreter found. Create a venv (see docs/desktop-packaging.md).");
    process.exit(1);
  }
  const shim = fs.mkdtempSync(path.join(os.tmpdir(), "zintriq-python-shim-"));
  writeShim(python, shim);
  const env = { ...process.env, PATH: `${shim}${path.delimiter}${process.env.PATH || ""}` };
  const args = process.argv.slice(2);
  const builder = path.join(desktopDir, "node_modules", "electron-builder", "cli.js");
  const result = spawnSync(process.execPath, [builder, ...args], {
    cwd: desktopDir,
    env,
    stdio: "inherit",
  });
  if (result.status) process.exit(result.status == null ? 1 : result.status);
  const after = spawnSync(python, [path.join(__dirname, "after_dist.py"), path.join(desktopDir, "release")], {
    cwd: repoRoot,
    env,
    stdio: "inherit",
  });
  process.exit(after.status == null ? 1 : after.status);
}

main();
