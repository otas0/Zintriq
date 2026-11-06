/**
 * Rebuild node-pty against the local Electron ABI.
 * Failures are non-fatal: Flask PTY (unix / ConPTY) remains the fallback.
 */
const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const root = path.join(__dirname, "..");
const ptyDir = path.join(root, "node_modules", "node-pty");
if (!fs.existsSync(ptyDir)) {
  console.warn("[rebuild-pty] node-pty not installed — skip (Flask PTY fallback)");
  process.exit(0);
}

const pythonCandidates = [
  process.env.npm_config_python,
  process.env.PYTHON,
  path.join(root, "..", ".venv", "bin", "python"),
  "python3",
  "python",
].filter(Boolean);

let python = null;
for (const cand of pythonCandidates) {
  const probe = spawnSync(cand, ["-c", "import setuptools"], { encoding: "utf8" });
  if (probe.status === 0) {
    python = cand;
    break;
  }
}

const env = { ...process.env };
if (python) {
  env.PYTHON = python;
  env.npm_config_python = python;
}

const bin = path.join(root, "node_modules", ".bin", "electron-rebuild");
const cmd = fs.existsSync(bin) ? bin : "npx";
const args = fs.existsSync(bin)
  ? ["-f", "-w", "node-pty"]
  : ["electron-rebuild", "-f", "-w", "node-pty"];

console.log(`[rebuild-pty] rebuilding node-pty for Electron${python ? ` (python=${python})` : ""}…`);
const result = spawnSync(cmd, args, { cwd: root, env, stdio: "inherit", shell: process.platform === "win32" });
if (result.status !== 0) {
  console.warn("[rebuild-pty] rebuild failed — editor will use Flask PTY (unix-pty / ConPTY)");
  process.exit(0);
}
console.log("[rebuild-pty] ok");
