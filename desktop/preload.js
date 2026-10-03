const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("zintriqDesktop", {
  platform: process.platform,
  isDesktop: true,
  getConfig: () => ipcRenderer.invoke("studio:get-config"),
  getToken: () => ipcRenderer.invoke("studio:get-token"),
  getUser: () => ipcRenderer.invoke("studio:get-user"),
  login: () => ipcRenderer.invoke("studio:login"),
  logout: () => ipcRenderer.invoke("studio:logout"),
  openExternal: (url) => ipcRenderer.invoke("studio:open-external", url),
  exportProject: (payload) => ipcRenderer.invoke("studio:export-project", payload),
  previewImport: () => ipcRenderer.invoke("studio:preview-import"),
  commitImport: (payload) => ipcRenderer.invoke("studio:commit-import", payload),
  cancelImport: (payload) => ipcRenderer.invoke("studio:cancel-import", payload),
  onTransferProgress: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("studio:transfer-progress", listener);
    return () => ipcRenderer.removeListener("studio:transfer-progress", listener);
  },
  onDeepLink: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("studio:deep-link", listener);
    return () => ipcRenderer.removeListener("studio:deep-link", listener);
  },
});
