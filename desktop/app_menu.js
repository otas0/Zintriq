/**
 * Native application menu. No marketing-site links.
 */

const { Menu } = require("electron");

function installAppMenu({
  loadStudio,
  loadDescribe,
  loadSimulate,
  loadInstantiate,
  loadCommunity,
  loadSpace,
  newDescription,
  importSite,
  exportSite,
  login,
  signup,
  logout,
  syncCloud,
  publish,
  checkUpdates,
  activateEditorView,
  gitInit,
  gitStatus,
  gitCommit,
  gitDiff,
  gitLog,
  gitIgnore,
  exportKeymap,
  keymap,
}) {
  const isMac = process.platform === "darwin";
  const keys = keymap && typeof keymap === "object" ? keymap : {};
  const acc = (id, fallback) => keys[id] || fallback;
  const template = [
    ...(isMac
      ? [
          {
            role: "appMenu",
          },
        ]
      : []),
    {
      label: "File",
      submenu: [
        {
          label: "Home",
          accelerator: acc("view.home", "CmdOrCtrl+1"),
          click: () => {
            if (typeof loadStudio === "function") loadStudio();
          },
        },
        {
          label: "New",
          accelerator: acc("file.new", "CmdOrCtrl+N"),
          click: () => {
            if (typeof newDescription === "function") newDescription();
          },
        },
        {
          label: "Community",
          accelerator: acc("view.community", "CmdOrCtrl+5"),
          click: () => {
            if (typeof loadCommunity === "function") loadCommunity();
          },
        },
        { type: "separator" },
        {
          label: "Open…",
          accelerator: acc("file.open", "CmdOrCtrl+O"),
          click: () => {
            if (typeof importSite === "function") importSite();
          },
        },
        {
          label: "Export webpage…",
          accelerator: "CmdOrCtrl+Shift+E",
          click: () => {
            if (typeof exportSite === "function") exportSite();
          },
        },
        {
          label: "Publish…",
          click: () => {
            if (typeof publish === "function") publish();
          },
        },
        {
          label: "Sync now",
          click: () => {
            if (typeof syncCloud === "function") syncCloud();
          },
        },
        { type: "separator" },
        {
          label: "Log in…",
          click: () => {
            if (typeof login === "function") login();
          },
        },
        {
          label: "Sign up…",
          click: () => {
            if (typeof signup === "function") signup();
          },
        },
        {
          label: "Log out",
          click: () => {
            if (typeof logout === "function") logout();
          },
        },
        { type: "separator" },
        {
          label: "Check for updates…",
          click: () => {
            if (typeof checkUpdates === "function") checkUpdates();
          },
        },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    {
      label: "Pane",
      submenu: [
        {
          label: "Code",
          accelerator: acc("pane.code", "CmdOrCtrl+Shift+1"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("code");
          },
        },
        {
          label: "Visual",
          accelerator: acc("pane.visual", "CmdOrCtrl+Shift+2"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("visual");
          },
        },
        {
          label: "Graph",
          accelerator: acc("pane.graph", "CmdOrCtrl+Shift+3"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("graph");
          },
        },
        {
          label: "UIR",
          accelerator: acc("pane.uir", "CmdOrCtrl+Shift+4"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("uir");
          },
        },
        {
          label: "Simulation",
          accelerator: acc("pane.simulation", "CmdOrCtrl+Shift+5"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("simulation");
          },
        },
        {
          label: "Page",
          accelerator: acc("pane.page", "CmdOrCtrl+Shift+6"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("page");
          },
        },
        {
          label: "Artifact",
          accelerator: acc("pane.artifact", "CmdOrCtrl+Shift+7"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("artifact");
          },
        },
        {
          label: "Diagram",
          accelerator: acc("pane.diagram", "CmdOrCtrl+Shift+8"),
          click: () => {
            if (typeof activateEditorView === "function") activateEditorView("diagram");
          },
        },
        {
          label: "Add plugin…",
          click: () => {
            if (typeof loadCommunity === "function") loadCommunity();
          },
        },
      ],
    },
    { role: "editMenu" },
    { role: "viewMenu" },
    {
      label: "Git",
      submenu: [
        {
          label: "Init in data folder",
          click: () => {
            if (typeof gitInit === "function") gitInit();
          },
        },
        {
          label: "Status",
          click: () => {
            if (typeof gitStatus === "function") gitStatus();
          },
        },
        {
          label: "Commit local work",
          click: () => {
            if (typeof gitCommit === "function") gitCommit();
          },
        },
        {
          label: "Diff",
          click: () => {
            if (typeof gitDiff === "function") gitDiff();
          },
        },
        {
          label: "Log",
          click: () => {
            if (typeof gitLog === "function") gitLog();
          },
        },
        {
          label: "Write ignore rules",
          click: () => {
            if (typeof gitIgnore === "function") gitIgnore();
          },
        },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "Export keymap…",
          click: () => {
            if (typeof exportKeymap === "function") exportKeymap();
          },
        },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

module.exports = { installAppMenu };
