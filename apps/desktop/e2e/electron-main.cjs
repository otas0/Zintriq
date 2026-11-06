const { app, BrowserWindow } = require("electron");

app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 1280, height: 800, show: true });
  const target = process.env.ZINTRIQ_UI_URL || "http://localhost:5173";
  win.loadURL(target);
});
