const { app, BrowserWindow } = require("electron");

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: true,
    webPreferences: {
      // Monaco editor workers need a normal Chromium worker context.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  const target = process.env.ZINTRIQ_UI_URL || "http://localhost:5175";
  win.loadURL(target);
});
