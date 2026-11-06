/**
 * Local host preferences: keymap + workbench layout (no telemetry).
 */
const fs = require("fs");
const path = require("path");

const DEFAULT_KEYMAP = {
  "file.save": "CommandOrControl+S",
  "edit.find": "CommandOrControl+F",
  "view.home": "CommandOrControl+1",
  "view.changes": "CommandOrControl+Shift+G",
  "view.split": "CommandOrControl+\\",
};

function keymapPath(userData) {
  return path.join(userData, "keymap.json");
}

function layoutPath(userData) {
  return path.join(userData, "layout.json");
}

function loadKeymap(userData) {
  try {
    const raw = JSON.parse(fs.readFileSync(keymapPath(userData), "utf8"));
    if (!raw || typeof raw !== "object") return { ...DEFAULT_KEYMAP };
    return { ...DEFAULT_KEYMAP, ...raw };
  } catch {
    return { ...DEFAULT_KEYMAP };
  }
}

function saveKeymap(userData, keymap) {
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(keymapPath(userData), JSON.stringify(keymap || DEFAULT_KEYMAP, null, 2));
}

function loadLayout(userData) {
  try {
    return JSON.parse(fs.readFileSync(layoutPath(userData), "utf8"));
  } catch {
    return null;
  }
}

function saveLayout(userData, layout) {
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(layoutPath(userData), JSON.stringify(layout || {}, null, 2));
}

module.exports = {
  DEFAULT_KEYMAP,
  loadKeymap,
  saveKeymap,
  loadLayout,
  saveLayout,
};
