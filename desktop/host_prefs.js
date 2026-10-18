/**
 * Local host preferences: layout, keymap, probe (no CPU/GPU/memory sampling).
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const DEFAULT_KEYMAP = {
  "workbench.palette": "CommandOrControl+K",
  "history.undo": "CommandOrControl+Z",
  "history.redo": "CommandOrControl+Shift+Z",
  "file.save": "CommandOrControl+S",
  "file.new": "CommandOrControl+N",
  "file.open": "CommandOrControl+O",
  "file.export": "CommandOrControl+Shift+E",
  "file.keymap.export": "CommandOrControl+Shift+K",
  "edit.cut": "CommandOrControl+X",
  "edit.copy": "CommandOrControl+C",
  "edit.paste": "CommandOrControl+V",
  "edit.selectAll": "CommandOrControl+A",
  "edit.find": "CommandOrControl+F",
  "view.home": "CommandOrControl+1",
  "view.describe": "CommandOrControl+2",
  "view.simulate": "CommandOrControl+3",
  "view.instantiate": "CommandOrControl+4",
  "view.community": "CommandOrControl+5",
  "view.space": "CommandOrControl+6",
  "view.sidebar": "CommandOrControl+B",
  "view.panel": "CommandOrControl+J",
  "view.zen": "CommandOrControl+K Z",
  "pane.code": "CommandOrControl+Shift+1",
  "pane.visual": "CommandOrControl+Shift+2",
  "pane.graph": "CommandOrControl+Shift+3",
  "pane.uir": "CommandOrControl+Shift+4",
  "pane.simulation": "CommandOrControl+Shift+5",
  "pane.page": "CommandOrControl+Shift+6",
  "pane.artifact": "CommandOrControl+Shift+7",
  "pane.diagram": "CommandOrControl+Shift+8",
  "pane.splitRight": "CommandOrControl+\\",
  "pane.pin": "CommandOrControl+Shift+P",
  "window.new": "CommandOrControl+Shift+N",
};

function keymapConflicts(keymap) {
  const seen = {};
  const conflicts = [];
  Object.keys(keymap || {}).forEach((id) => {
    const acc = String(keymap[id] || "").trim();
    if (!acc) return;
    if (seen[acc]) conflicts.push({ keys: acc, a: seen[acc], b: id });
    else seen[acc] = id;
  });
  return conflicts;
}

function platformAccelerator(acc) {
  const raw = String(acc || "");
  if (process.platform === "darwin") return raw.replace(/CommandOrControl/g, "Command").replace(/CmdOrCtrl/g, "Command");
  return raw.replace(/CommandOrControl/g, "Control").replace(/CmdOrCtrl/g, "Control");
}

function mergeKeymap(partial) {
  return Object.assign({}, DEFAULT_KEYMAP, partial && typeof partial === "object" ? partial : {});
}

function prefsPath(userData) {
  return path.join(userData, "host-prefs.json");
}

function loadPrefs(userData) {
  try {
    const data = JSON.parse(fs.readFileSync(prefsPath(userData), "utf8"));
    if (data && typeof data === "object") {
      data.keymap = mergeKeymap(data.keymap);
      return data;
    }
  } catch {
    /* first launch */
  }
  return { keymap: DEFAULT_KEYMAP, layout: null, editorGroups: [], windows: [], proxy: "", dirty: false };
}

function savePrefs(userData, patch) {
  const next = Object.assign(loadPrefs(userData), patch || {});
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(prefsPath(userData), JSON.stringify(next, null, 2));
  return next;
}

function probe() {
  const locale = Intl.DateTimeFormat().resolvedOptions();
  return {
    arch: os.arch(),
    dark: false,
    locale: locale.locale || "en",
    platform: process.platform,
    screens: [],
    timezone: locale.timeZone || "UTC",
    version: process.versions.electron || "",
  };
}

function gitInit(cwd) {
  const result = spawnSync("git", ["init"], { cwd, encoding: "utf8" });
  if (result.error) return { ok: false, error: result.error.message };
  if (result.status !== 0) return { ok: false, error: result.stderr || "git init failed" };
  return { ok: true };
}

function gitStatus(cwd) {
  const result = spawnSync("git", ["status", "--porcelain", "-b"], { cwd, encoding: "utf8" });
  if (result.error) return { ok: false, error: result.error.message };
  if (result.status !== 0) return { ok: false, error: result.stderr || "git status failed" };
  return { ok: true, text: result.stdout || "" };
}

function gitCommit(cwd, message) {
  const msg = String(message || "Save local work").slice(0, 72);
  spawnSync("git", ["add", "-A"], { cwd, encoding: "utf8" });
  const result = spawnSync("git", ["commit", "-m", msg], { cwd, encoding: "utf8" });
  if (result.error) return { ok: false, error: result.error.message };
  if (result.status !== 0) return { ok: false, error: result.stderr || "git commit failed" };
  return { ok: true };
}

function gitDiff(cwd) {
  const result = spawnSync("git", ["diff", "--stat"], { cwd, encoding: "utf8" });
  if (result.error) return { ok: false, error: result.error.message };
  if (result.status !== 0) return { ok: false, error: result.stderr || "git diff failed" };
  return { ok: true, text: result.stdout || "" };
}

function gitLog(cwd) {
  const result = spawnSync("git", ["log", "-8", "--oneline"], { cwd, encoding: "utf8" });
  if (result.error) return { ok: false, error: result.error.message };
  if (result.status !== 0) return { ok: false, error: result.stderr || "git log failed" };
  return { ok: true, text: result.stdout || "" };
}

function gitIgnore(cwd) {
  const file = path.join(cwd, ".gitignore");
  const body = ["*.log", ".DS_Store", "Thumbs.db", "search-index.json", ""].join(os.EOL);
  try {
    fs.writeFileSync(file, body);
  } catch (err) {
    return { ok: false, error: err.message };
  }
  return { ok: true, path: file };
}

module.exports = {
  DEFAULT_KEYMAP,
  gitCommit,
  gitDiff,
  gitIgnore,
  gitInit,
  gitLog,
  gitStatus,
  keymapConflicts,
  loadPrefs,
  mergeKeymap,
  platformAccelerator,
  prefsPath,
  probe,
  savePrefs,
};
