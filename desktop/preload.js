const { contextBridge, ipcRenderer } = require("electron");

const ptyDataHandlers = new Set();
const ptyExitHandlers = new Set();
ipcRenderer.on("editor:pty-data", (_e, payload) => {
  for (const h of ptyDataHandlers) h(payload.id, payload.data);
});
ipcRenderer.on("editor:pty-exit", (_e, payload) => {
  for (const h of ptyExitHandlers) h(payload.id, payload.code);
});

contextBridge.exposeInMainWorld("zintriqDesktop", {
  platform: process.platform,
  isDesktop: true,
  getConfig: () => ipcRenderer.invoke("editor:get-config"),
  getToken: () => ipcRenderer.invoke("editor:get-token"),
  http: (payload) => ipcRenderer.invoke("editor:http", payload),
  probe: () => ipcRenderer.invoke("editor:probe"),
  keymap: () => ipcRenderer.invoke("editor:keymap"),
  loadLayout: () => ipcRenderer.invoke("editor:layout-load"),
  saveLayout: (layout) => ipcRenderer.invoke("editor:layout-save", layout),
  onMenu: (handler) => {
    const listener = (_event, action) => handler(action);
    ipcRenderer.on("editor:menu", listener);
    return () => ipcRenderer.removeListener("editor:menu", listener);
  },
  pty: {
    available: () => ipcRenderer.invoke("editor:pty-available"),
    start: (opts) => ipcRenderer.invoke("editor:pty-start", opts || {}),
    write: (id, data) => ipcRenderer.invoke("editor:pty-write", id, data),
    resize: (id, cols, rows) => ipcRenderer.invoke("editor:pty-resize", id, cols, rows),
    kill: (id) => ipcRenderer.invoke("editor:pty-kill", id),
    onData: (handler) => {
      ptyDataHandlers.add(handler);
      return () => ptyDataHandlers.delete(handler);
    },
    onExit: (handler) => {
      ptyExitHandlers.add(handler);
      return () => ptyExitHandlers.delete(handler);
    },
  },
});
