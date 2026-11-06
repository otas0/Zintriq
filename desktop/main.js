/**
 * Zintriq Editor — Electron shell.
 * Spawns local Flask on 127.0.0.1, loads /editor only.
 */

const { app, BrowserWindow, ipcMain, session, dialog } = require("electron");
const { installAppMenu } = require("./app_menu");
const hostPrefs = require("./host_prefs");
const path = require("path");
const http = require("http");
const {
  devUserDataDir,
  smokeUserDataDir,
  resolvePythonExecutable,
  pythonExists,
  startFlask,
  stopFlask,
  stopFlaskSync,
  scrub,
  onFlaskReady,
  loadLaunchRecipe,
  lastFlaskLaunch,
} = require("./flask_host");
const { navigationAllowed } = require("./navigation");
let ptyHost = null;
try {
  ptyHost = require("./pty_host");
} catch {
  ptyHost = null;
}

onFlaskReady((info) => {
  flaskInfo = info;
});

app.commandLine.appendSwitch("disable-features", "ServiceWorker");
app.setName("Zintriq Editor");
if (app.isPackaged) {
  process.env.ZINTRIQ_PACKAGED = "1";
}
if (process.env.ZINTRIQ_SMOKE === "1") {
  app.setPath("userData", process.env.ZINTRIQ_SMOKE_USER_DATA || smokeUserDataDir());
} else if (!app.isPackaged) {
  app.setPath("userData", devUserDataDir());
}

const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
].join("; ");

let mainWindow = null;
let localOrigin = "";
let flaskInfo = null;
let quitStarted = false;
let launchRecipe = null;

function editorHome() {
  const home = launchRecipe && launchRecipe.studio;
  return home && String(home).startsWith("/editor") ? home : "/editor";
}

function loadEditor(pathname) {
  if (!mainWindow || mainWindow.isDestroyed() || !localOrigin) return;
  const target = pathname && String(pathname).startsWith("/editor") ? pathname : editorHome();
  mainWindow.loadURL(`${localOrigin}${target}`);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: process.env.ZINTRIQ_SMOKE !== "1",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!flaskInfo || !navigationAllowed(url, flaskInfo.port)) {
      event.preventDefault();
    }
  });
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.on("closed", () => {
    if (mainWindow === win) mainWindow = null;
  });
  return win;
}

async function studioHttp(payload) {
  if (!flaskInfo) throw new Error("Flask not ready");
  const method = String((payload && payload.method) || "GET").toUpperCase();
  const reqPath = String((payload && payload.path) || "/");
  if (!reqPath.startsWith("/")) throw new Error("bad path");
  const body =
    payload && payload.body != null
      ? Buffer.from(typeof payload.body === "string" ? payload.body : JSON.stringify(payload.body))
      : null;
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port: flaskInfo.port,
        path: reqPath,
        method,
        headers: {
          "X-Zintriq-Desktop-Token": flaskInfo.token,
          ...(body
            ? { "Content-Type": "application/json", "Content-Length": body.length }
            : {}),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const raw = Buffer.concat(chunks).toString("utf8");
          let data = raw;
          try {
            data = JSON.parse(raw);
          } catch {
            /* keep text */
          }
          if (res.statusCode >= 400) {
            const err = new Error((data && data.error) || `HTTP ${res.statusCode}`);
            err.status = res.statusCode;
            err.data = data;
            reject(err);
            return;
          }
          resolve(data);
        });
      }
    );
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

function wireIpc() {
  ipcMain.handle("editor:get-config", async () => ({
    origin: localOrigin,
    home: editorHome(),
    platform: process.platform,
  }));
  ipcMain.handle("editor:get-token", async () => (flaskInfo ? flaskInfo.token : ""));
  ipcMain.handle("editor:http", async (_e, payload) => studioHttp(payload));
  ipcMain.handle("editor:probe", async () => {
    const launch = lastFlaskLaunch();
    return {
      ok: Boolean(flaskInfo),
      port: flaskInfo && flaskInfo.port,
      reason: launch.reason || "",
      logTail: launch.logTail || "",
    };
  });
  ipcMain.handle("editor:keymap", async () => hostPrefs.loadKeymap(app.getPath("userData")));
  ipcMain.handle("editor:layout-load", async () => hostPrefs.loadLayout(app.getPath("userData")));
  ipcMain.handle("editor:layout-save", async (_e, layout) => {
    hostPrefs.saveLayout(app.getPath("userData"), layout || {});
    return { ok: true };
  });

  ipcMain.handle("editor:pty-available", async () => Boolean(ptyHost && ptyHost.available()));
  ipcMain.handle("editor:pty-start", async (event, opts) => {
    if (!ptyHost || !ptyHost.available()) throw new Error("node-pty unavailable");
    const cwd = ptyHost.resolveWorkspaceCwd(app.getPath("userData"), launchRecipe);
    const wc = event.sender;
    return ptyHost.start({
      cwd,
      cols: opts && opts.cols,
      rows: opts && opts.rows,
      onData: (id, data) => {
        if (!wc.isDestroyed()) wc.send("editor:pty-data", { id, data });
      },
      onExit: (id, code) => {
        if (!wc.isDestroyed()) wc.send("editor:pty-exit", { id, code });
      },
    });
  });
  ipcMain.handle("editor:pty-write", async (_e, id, data) => {
    if (!ptyHost) throw new Error("node-pty unavailable");
    return ptyHost.write(id, data);
  });
  ipcMain.handle("editor:pty-resize", async (_e, id, cols, rows) => {
    if (!ptyHost) throw new Error("node-pty unavailable");
    return ptyHost.resize(id, cols, rows);
  });
  ipcMain.handle("editor:pty-kill", async (_e, id) => {
    if (!ptyHost) return { ok: true };
    return ptyHost.kill(id);
  });
}

async function boot() {
  const userData = app.getPath("userData");
  launchRecipe = loadLaunchRecipe(userData);
  const pythonPath = resolvePythonExecutable();
  if (!pythonExists(pythonPath)) {
    dialog.showErrorBox(
      "Python missing",
      `Could not find ${pythonPath}. Create .venv or set ZINTRIQ_PYTHON.`
    );
    app.quit();
    return;
  }
  try {
    flaskInfo = await startFlask({
      userData,
      pythonPath,
      appVersion: app.getVersion(),
    });
  } catch (err) {
    const detail = scrub(err && err.message ? err.message : String(err), "");
    if (mainWindow && !mainWindow.isDestroyed()) {
      await mainWindow.loadFile(path.join(__dirname, "error.html"), {
        query: { message: detail },
      });
    } else {
      dialog.showErrorBox("Editor failed to start", detail);
    }
    return;
  }
  localOrigin = `http://127.0.0.1:${flaskInfo.port}`;
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [CSP],
      },
    });
  });
  wireIpc();
  const sendMenu = (action) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("editor:menu", action);
    }
  };
  installAppMenu({
    loadHome: () => loadEditor("/editor"),
    save: () => sendMenu("save"),
    find: () => sendMenu("find"),
    changes: () => sendMenu("changes"),
    ai: () => sendMenu("ai"),
    split: () => sendMenu("split"),
    goDef: () => sendMenu("goDef"),
    rename: () => sendMenu("rename"),
    findRefs: () => sendMenu("findRefs"),
    codeAction: () => sendMenu("codeAction"),
    keymap: hostPrefs.loadKeymap(userData),
  });
  if (!mainWindow) mainWindow = createWindow();
  loadEditor(editorHome());
  if (process.env.ZINTRIQ_SMOKE === "1") {
    const sessionFile = path.join(userData, "smoke-session.json");
    require("fs").writeFileSync(
      sessionFile,
      JSON.stringify({
        port: flaskInfo.port,
        pid: flaskInfo.pid,
        origin: localOrigin,
        readyAt: Date.now(),
      })
    );
  }
}

app.whenReady().then(boot);

app.on("before-quit", (e) => {
  if (quitStarted) return;
  quitStarted = true;
  e.preventDefault();
  try {
    if (ptyHost) ptyHost.killAll();
  } catch {
    /* ignore */
  }
  Promise.resolve(stopFlask())
    .catch(() => {})
    .finally(() => app.exit(0));
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (!mainWindow) {
    mainWindow = createWindow();
    if (localOrigin) loadEditor(editorHome());
  }
});

process.on("exit", () => {
  stopFlaskSync();
});
