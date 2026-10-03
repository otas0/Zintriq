/**
 * Zintriq Studio — Electron shell.
 * Spawns the local Flask process, then loads /studio from 127.0.0.1 only.
 */

const { app, BrowserWindow, shell, ipcMain, safeStorage, session } = require("electron");
const transferHost = require("./transfer_host");
const path = require("path");
const fs = require("fs");
const { createPkcePair, buildAuthorizeUrl, parseAuthCallback } = require("./auth");
const {
  devUserDataDir,
  smokeUserDataDir,
  resolvePythonExecutable,
  pythonExists,
  startFlask,
  stopFlask,
  stopFlaskSync,
  scrub,
} = require("./flask_host");

app.commandLine.appendSwitch("disable-features", "ServiceWorker");
app.setName("Zintriq Studio");
if (app.isPackaged) {
  process.env.ZINTRIQ_PACKAGED = "1";
}
if (process.env.ZINTRIQ_SMOKE === "1") {
  app.setPath("userData", process.env.ZINTRIQ_SMOKE_USER_DATA || smokeUserDataDir());
} else if (!app.isPackaged) {
  app.setPath("userData", devUserDataDir());
}

const PROTOCOL = "zintriq";
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
  "frame-src 'self'",
].join("; ");

let mainWindow = null;
let pendingAuth = null;
let localOrigin = "";
let flaskInfo = null;
let quitStarted = false;
let loopbackArmed = false;

function userDataPath(...parts) {
  return path.join(app.getPath("userData"), ...parts);
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function loadSession() {
  const raw = readJson(userDataPath("session.json"), {});
  if (!raw.tokenEnc) return { token: null, user: null };
  try {
    const buf = Buffer.from(raw.tokenEnc, "base64");
    const token = safeStorage.isEncryptionAvailable()
      ? safeStorage.decryptString(buf)
      : buf.toString("utf8");
    return { token, user: raw.user || null };
  } catch {
    return { token: null, user: null };
  }
}

function saveSession({ token, user }) {
  const enc = safeStorage.isEncryptionAvailable()
    ? safeStorage.encryptString(token).toString("base64")
    : Buffer.from(token, "utf8").toString("base64");
  writeJson(userDataPath("session.json"), { tokenEnc: enc, user });
}

function clearSession() {
  try {
    fs.unlinkSync(userDataPath("session.json"));
  } catch {
    /* ignore */
  }
}

function studioConfig() {
  const envFile = path.join(__dirname, ".env.desktop.json");
  const fileCfg = readJson(envFile, {});
  return {
    auth0Domain: process.env.AUTH0_DOMAIN || fileCfg.auth0Domain || "",
    auth0NativeClientId:
      process.env.AUTH0_NATIVE_CLIENT_ID ||
      fileCfg.auth0NativeClientId ||
      process.env.AUTH0_CLIENT_ID ||
      fileCfg.auth0ClientId ||
      "",
    auth0Audience: process.env.AUTH0_AUDIENCE || fileCfg.auth0Audience || "",
    redirectUri: `${PROTOCOL}://auth/callback`,
  };
}

function injectTokenScript(token) {
  if (!token) {
    return `(() => {
      try { localStorage.removeItem("zintriq_studio_token"); } catch (e) {}
      window.__ZINTRIQ_STUDIO_TOKEN__ = "";
    })();`;
  }
  return `(() => {
    const t = ${JSON.stringify(token)};
    window.__ZINTRIQ_STUDIO_TOKEN__ = t;
    try { localStorage.setItem("zintriq_studio_token", t); } catch (e) {}
  })();`;
}

async function injectSessionIntoPage() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const { token } = loadSession();
  try {
    await mainWindow.webContents.executeJavaScript(injectTokenScript(token), true);
  } catch {
    /* page may have navigated away */
  }
}

function isAuthPagePath(pathname) {
  return pathname === "/login" || pathname === "/register" || pathname.startsWith("/login/");
}

function navigationAllowed(url, port) {
  let dest;
  try {
    dest = new URL(url);
  } catch {
    return false;
  }
  if (dest.protocol !== "http:" || dest.hostname !== "127.0.0.1" || dest.port !== String(port)) {
    return false;
  }
  if (isAuthPagePath(dest.pathname)) return false;
  return true;
}

function hardenContents(contents, port) {
  contents.setWindowOpenHandler(({ url }) => {
    try {
      const dest = new URL(url);
      if (dest.protocol === "https:") shell.openExternal(dest.href);
    } catch {
      /* deny */
    }
    return { action: "deny" };
  });
  const guard = (event, url) => {
    if (!navigationAllowed(url, port)) event.preventDefault();
  };
  contents.on("will-navigate", guard);
  contents.on("will-redirect", guard);
  contents.on("will-attach-webview", (event) => event.preventDefault());
}

function armLoopback(port, token) {
  if (loopbackArmed) return;
  loopbackArmed = true;
  const urls = [`http://127.0.0.1:${port}/*`];
  const prefix = `http://127.0.0.1:${port}/`;
  session.defaultSession.webRequest.onBeforeSendHeaders({ urls }, (details, callback) => {
    const headers = { ...details.requestHeaders };
    if (String(details.url || "").startsWith(prefix)) {
      headers["X-Zintriq-Desktop-Token"] = token;
    }
    const { token: studioToken } = loadSession();
    if (studioToken) headers.Authorization = `Bearer ${studioToken}`;
    else {
      delete headers.Authorization;
      delete headers.authorization;
    }
    headers["X-Studio-Client"] = "desktop";
    callback({ requestHeaders: headers });
  });
  session.defaultSession.webRequest.onHeadersReceived({ urls }, (details, callback) => {
    const headers = { ...details.responseHeaders };
    headers["Content-Security-Policy"] = [CSP];
    callback({ responseHeaders: headers });
  });
}

function installSmokeGuard(port) {
  const allowed = `http://127.0.0.1:${port}/`;
  const file = userDataPath("logs", "smoke-blocked.txt");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  session.defaultSession.webRequest.onBeforeRequest({ urls: ["<all_urls>"] }, (details, callback) => {
    const url = String(details.url || "");
    if (url.startsWith(allowed)) {
      callback({ cancel: false });
      return;
    }
    fs.appendFileSync(file, `${url}\n`);
    callback({ cancel: true });
  });
}

function writeSmokeTokenFile() {
  const file = process.env.ZINTRIQ_SMOKE_TOKEN_FILE;
  if (process.env.ZINTRIQ_SMOKE !== "1" || !file || !flaskInfo || !flaskInfo.token) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, flaskInfo.token, { mode: 0o600 });
}

function publishSmoke(loaded) {
  if (process.env.ZINTRIQ_SMOKE !== "1" || !flaskInfo) return;
  const body = {
    port: flaskInfo.port,
    token: flaskInfo.token,
    flaskPid: flaskInfo.pid,
    logPath: flaskInfo.logPath,
    loaded: Boolean(loaded),
  };
  fs.writeFileSync(userDataPath("smoke-session.json"), JSON.stringify(body), { mode: 0o600 });
}

function installPermissions() {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);
}

function createWindow(port) {
  localOrigin = `http://127.0.0.1:${port}`;
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    title: "Zintriq Studio",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
    },
  });
  hardenContents(mainWindow.webContents, port);
  mainWindow.webContents.on("did-finish-load", () => {
    injectSessionIntoPage();
    publishSmoke(true);
  });
  mainWindow.loadURL(`${localOrigin}/studio`);
}

async function showError(message, logPath) {
  const token = flaskInfo && flaskInfo.token;
  const win = new BrowserWindow({
    width: 720,
    height: 480,
    title: "Zintriq",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
    },
  });
  mainWindow = win;
  await win.loadFile(path.join(__dirname, "error.html"));
  const script = `document.getElementById("msg").textContent = ${JSON.stringify(scrub(message, token))};
    document.getElementById("log").textContent = ${JSON.stringify(logPath || "")};`;
  await win.webContents.executeJavaScript(script, true);
}

async function exchangePkce({ code, codeVerifier, redirectUri }) {
  const res = await fetch(`${localOrigin}/api/studio/auth/pkce/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      code,
      code_verifier: codeVerifier,
      redirect_uri: redirectUri,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Auth exchange failed (${res.status})`);
  return data;
}

async function startLogin() {
  const cfg = studioConfig();
  if (!cfg.auth0Domain || !cfg.auth0NativeClientId) {
    throw new Error("Set AUTH0_DOMAIN and AUTH0_NATIVE_CLIENT_ID (see desktop/.env.desktop.example)");
  }
  const { verifier, challenge } = createPkcePair();
  const state = require("crypto").randomBytes(16).toString("hex");
  pendingAuth = { verifier, state, redirectUri: cfg.redirectUri };
  const url = buildAuthorizeUrl({
    domain: cfg.auth0Domain,
    clientId: cfg.auth0NativeClientId,
    redirectUri: cfg.redirectUri,
    state,
    codeChallenge: challenge,
    audience: cfg.auth0Audience,
  });
  await shell.openExternal(url);
  return { ok: true, opened: true };
}

async function completeLogout() {
  clearSession();
  if (mainWindow && !mainWindow.isDestroyed()) {
    try {
      await mainWindow.webContents.executeJavaScript(injectTokenScript(null), true);
    } catch {
      /* ignore */
    }
    if (localOrigin) await mainWindow.loadURL(`${localOrigin}/studio`);
  }
  return { ok: true };
}

async function handleAuthUrl(urlString) {
  if (!urlString || !urlString.startsWith(`${PROTOCOL}://`)) return;
  if (urlString.startsWith(`${PROTOCOL}://auth/callback`)) {
    const { code, state, error, errorDescription } = parseAuthCallback(urlString);
    if (error) throw new Error(errorDescription || error);
    if (!pendingAuth || state !== pendingAuth.state) throw new Error("Auth state mismatch — try signing in again");
    const result = await exchangePkce({
      code,
      codeVerifier: pendingAuth.verifier,
      redirectUri: pendingAuth.redirectUri,
    });
    pendingAuth = null;
    saveSession({ token: result.token, user: result.user });
    if (mainWindow && !mainWindow.isDestroyed() && localOrigin) {
      await mainWindow.loadURL(`${localOrigin}/studio`);
      await injectSessionIntoPage();
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
    return result;
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("studio:deep-link", { url: urlString });
    const target = new URL(urlString);
    const pkg = target.searchParams.get("package");
    if (pkg && localOrigin) {
      await mainWindow.loadURL(`${localOrigin}/studio?install=${encodeURIComponent(pkg)}`);
    } else {
      mainWindow.focus();
    }
  }
}

function registerIpc() {
  ipcMain.handle("studio:get-config", () => {
    const cfg = studioConfig();
    return {
      serverUrl: localOrigin,
      hasAuth0: Boolean(cfg.auth0Domain && cfg.auth0NativeClientId),
      protocol: PROTOCOL,
    };
  });
  ipcMain.handle("studio:get-token", () => loadSession().token);
  ipcMain.handle("studio:get-user", () => loadSession().user);
  ipcMain.handle("studio:login", () => startLogin());
  ipcMain.handle("studio:logout", () => completeLogout());
  ipcMain.handle("studio:export-project", (event, payload) => {
    return transferHost.exportProject({
      event,
      window: mainWindow,
      flaskInfo,
      projectId: payload && payload.projectId,
      suggestedName: payload && payload.name,
    });
  });
  ipcMain.handle("studio:preview-import", (event) => {
    return transferHost.previewImport({
      event,
      window: mainWindow,
      flaskInfo,
      userData: app.getPath("userData"),
    });
  });
  ipcMain.handle("studio:commit-import", (event, payload) => {
    return transferHost.commitImport({
      event,
      window: mainWindow,
      flaskInfo,
      userData: app.getPath("userData"),
      stagingId: payload && payload.stagingId,
      enableKeys: payload && payload.enableKeys,
    });
  });
  ipcMain.handle("studio:cancel-import", (event, payload) => {
    return transferHost.cancelImport({
      event,
      flaskInfo,
      userData: app.getPath("userData"),
      stagingId: payload && payload.stagingId,
    });
  });
  ipcMain.handle("studio:open-external", (_event, url) => {
    let dest;
    try {
      dest = new URL(String(url || ""));
    } catch {
      return { ok: false };
    }
    if (dest.protocol !== "https:") return { ok: false };
    shell.openExternal(dest.href);
    return { ok: true };
  });
}

function registerProtocol() {
  if (process.defaultApp) {
    if (process.argv.length >= 2) {
      app.setAsDefaultProtocolClient(PROTOCOL, process.execPath, [path.resolve(process.argv[1])]);
    }
  } else {
    app.setAsDefaultProtocolClient(PROTOCOL);
  }
}

app.on("web-contents-created", (_event, contents) => {
  contents.on("will-attach-webview", (event) => event.preventDefault());
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", (_event, argv) => {
    const url = argv.find((arg) => String(arg).startsWith(`${PROTOCOL}://`));
    if (url) handleAuthUrl(url).catch(() => {});
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    installPermissions();
    registerProtocol();
    registerIpc();
    const python = resolvePythonExecutable();
    if (!pythonExists(python)) {
      await showError("请先创建虚拟环境并安装依赖", "");
      return;
    }
    try {
      flaskInfo = await startFlask({
        userData: app.getPath("userData"),
        pythonPath: python,
        appVersion: app.getVersion(),
      });
      writeSmokeTokenFile();
      armLoopback(flaskInfo.port, flaskInfo.token);
      if (process.env.ZINTRIQ_SMOKE === "1") installSmokeGuard(flaskInfo.port);
      createWindow(flaskInfo.port);
      const bootUrl = process.argv.find((arg) => String(arg).startsWith(`${PROTOCOL}://`));
      if (bootUrl) handleAuthUrl(bootUrl).catch(() => {});
    } catch (err) {
      const message = err && err.message ? err.message : "Flask 启动失败";
      await showError(message, err && err.logPath ? err.logPath : "");
    }
  });

  app.on("open-url", (event, url) => {
    event.preventDefault();
    handleAuthUrl(url).catch(() => {});
  });

  app.on("before-quit", (event) => {
    if (quitStarted) return;
    event.preventDefault();
    quitStarted = true;
    try {
      fs.rmSync(userDataPath("smoke-session.json"), { force: true });
    } catch {
      /* ignore */
    }
    try {
      transferHost.cleanAllStaging(app.getPath("userData"));
    } catch {
      /* ignore */
    }
    stopFlask().finally(() => app.exit(0));
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0 && flaskInfo) createWindow(flaskInfo.port);
  });

  process.on("exit", () => {
    stopFlaskSync();
  });
}
