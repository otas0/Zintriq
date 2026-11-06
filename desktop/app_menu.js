/**
 * Native application menu — editor shell.
 */

const { Menu } = require("electron");

function installAppMenu({
  loadHome,
  save,
  find,
  changes,
  ai,
  split,
  goDef,
  rename,
  findRefs,
  codeAction,
  keymap,
}) {
  const isMac = process.platform === "darwin";
  const keys = keymap && typeof keymap === "object" ? keymap : {};
  const acc = (id, fallback) => keys[id] || fallback;
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "File",
      submenu: [
        {
          label: "Home",
          accelerator: acc("view.home", "CmdOrCtrl+1"),
          click: () => loadHome && loadHome(),
        },
        {
          label: "Save",
          accelerator: acc("file.save", "CmdOrCtrl+S"),
          click: () => save && save(),
        },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
        { type: "separator" },
        {
          label: "Find",
          accelerator: acc("edit.find", "CmdOrCtrl+F"),
          click: () => find && find(),
        },
      ],
    },
    {
      label: "View",
      submenu: [
        {
          label: "Changes",
          accelerator: acc("view.changes", "CmdOrCtrl+Shift+G"),
          click: () => changes && changes(),
        },
        {
          label: "Toggle Split",
          accelerator: acc("view.split", "CmdOrCtrl+\\"),
          click: () => split && split(),
        },
        {
          label: "AI Panel",
          click: () => ai && ai(),
        },
        { type: "separator" },
        {
          label: "Go to Definition",
          accelerator: "F12",
          click: () => goDef && goDef(),
        },
        {
          label: "Find References",
          accelerator: "Shift+F12",
          click: () => findRefs && findRefs(),
        },
        {
          label: "Rename Symbol",
          accelerator: "F2",
          click: () => rename && rename(),
        },
        {
          label: "Code Action…",
          accelerator: "CmdOrCtrl+.",
          click: () => codeAction && codeAction(),
        },
        { type: "separator" },
        { role: "reload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

module.exports = { installAppMenu };
