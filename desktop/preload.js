const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("zintriqInvokeHttp", (payload) =>
  ipcRenderer.invoke("studio:http", payload)
);

contextBridge.exposeInMainWorld("zintriqDesktop", {
  platform: process.platform,
  isDesktop: true,
  getConfig: () => ipcRenderer.invoke("studio:get-config"),
  getToken: () => ipcRenderer.invoke("studio:get-token"),
  getUser: () => ipcRenderer.invoke("studio:get-user"),
  login: () => ipcRenderer.invoke("studio:login"),
  signup: () => ipcRenderer.invoke("studio:signup"),
  logout: () => ipcRenderer.invoke("studio:logout"),
  openExternal: (url) => ipcRenderer.invoke("studio:open-external", url),
  probe: () => ipcRenderer.invoke("studio:probe"),
  openPack: (filePath) => ipcRenderer.invoke("studio:open-pack", filePath),
  pathForFile: (file) => {
    try {
      return (webUtils && webUtils.getPathForFile(file)) || "";
    } catch {
      return "";
    }
  },
  loadLayout: () => ipcRenderer.invoke("studio:layout-load"),
  saveLayout: (layout) => ipcRenderer.invoke("studio:layout-save", layout),
  onLayout: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("studio:layout-changed", listener);
    return () => ipcRenderer.removeListener("studio:layout-changed", listener);
  },
  keymap: () => ipcRenderer.invoke("studio:keymap"),
  saveKeymap: (keymap) => ipcRenderer.invoke("studio:keymap-save", keymap),
  exportKeymap: () => ipcRenderer.invoke("studio:keymap-export"),
  importKeymap: (keymap) => ipcRenderer.invoke("studio:keymap-import", keymap),
  relaunch: () => ipcRenderer.invoke("studio:relaunch"),
  setDirty: (dirty) => ipcRenderer.invoke("studio:dirty", dirty),
  notify: (title, body) => ipcRenderer.invoke("studio:notify", { title, body }),
  gitInit: () => ipcRenderer.invoke("studio:git-init"),
  gitStatus: () => ipcRenderer.invoke("studio:git-status"),
  gitCommit: (message) => ipcRenderer.invoke("studio:git-commit", { message }),
  gitDiff: () => ipcRenderer.invoke("studio:git-diff"),
  gitLog: () => ipcRenderer.invoke("studio:git-log"),
  gitIgnore: () => ipcRenderer.invoke("studio:git-ignore"),
  newWindow: (studioPath) => ipcRenderer.invoke("studio:new-window", studioPath),
  listCatalog: (query) => ipcRenderer.invoke("studio:community-catalog", query || {}),
  listMine: () => ipcRenderer.invoke("studio:community-mine"),
  listPlugins: () => ipcRenderer.invoke("studio:plugin-catalog"),
  installPlugin: (id, csrf) => ipcRenderer.invoke("studio:plugin-install", { id, csrf }),
  disablePlugin: (id, csrf) => ipcRenderer.invoke("studio:plugin-disable", { id, csrf }),
  removePlugin: (id, csrf, deleteDraft) => ipcRenderer.invoke("studio:plugin-remove", { id, csrf, delete_draft: Boolean(deleteDraft) }),
  installSharePlugin: (id, csrf) => ipcRenderer.invoke("studio:plugin-from-share", { id, csrf }),
  publishPlugin: (pack) => ipcRenderer.invoke("studio:plugin-publish", { pack }),
  buildFromPlugins: (ids, csrf) => ipcRenderer.invoke("studio:plugin-project", { ids, csrf }),
  openShare: (id, surface) => ipcRenderer.invoke("studio:open-share", id, surface),
  publish: () => ipcRenderer.invoke("studio:publish"),
  unpublish: (id) => ipcRenderer.invoke("studio:unpublish", id),
  cloudEntitlement: () => ipcRenderer.invoke("studio:cloud-entitlement"),
  syncNow: () => ipcRenderer.invoke("studio:sync"),
  collabSync: (slug) => ipcRenderer.invoke("studio:collab-sync", slug),
  onDeepLink: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("studio:deep-link", listener);
    return () => ipcRenderer.removeListener("studio:deep-link", listener);
  },
});
