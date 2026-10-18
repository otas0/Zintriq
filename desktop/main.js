/**
 * Zintriq Studio — Electron shell.
 * Spawns the local Flask process, then loads /studio from 127.0.0.1 only.
 */

const { app, BrowserWindow, shell, ipcMain, safeStorage, session, dialog, Notification, nativeTheme } = require("electron");
const { installAppMenu } = require("./app_menu");
const metaZipHost = require("./meta_zip_host");
const metaHttp = require("./meta_http");
const cloudHost = require("./cloud_host");
const updater = require("./updater");
const hostPrefs = require("./host_prefs");
const { resolveAccountOrigin } = require("./account_origin");
const path = require("path");
const fs = require("fs");
const { fileURLToPath } = require("url");
const { createPkcePair, buildDesktopAuthorizeUrl, buildDesktopRegisterUrl, parseAuthCallback } = require("./auth");
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

onFlaskReady((info) => {
  flaskInfo = info;
});

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
let launchRecipe = null;
const pendingPacks = [];
let openingPacks = false;

function queuePackPath(filePath) {
  if (!metaZipHost.isPackPath(filePath)) return;
  const resolved = path.resolve(String(filePath));
  if (!pendingPacks.includes(resolved)) pendingPacks.push(resolved);
}

async function flushPendingPacks() {
  if (openingPacks || !flaskInfo || !localOrigin || !mainWindow || mainWindow.isDestroyed()) return { ok: false };
  const next = pendingPacks.shift();
  if (!next) return { ok: true, empty: true };
  openingPacks = true;
  let result = { ok: false };
  try {
    result = await metaZipHost.importPackFromPath({
      window: mainWindow,
      flaskInfo,
      origin: localOrigin,
      loadStudio,
      filePath: next,
    });
    if (!result.ok && !result.canceled && mainWindow && !mainWindow.isDestroyed()) {
      await dialog.showMessageBox(mainWindow, {
        type: "error",
        message: "Could not open pack",
        detail: String(result.error || ""),
      });
    }
  } finally {
    openingPacks = false;
  }
  if (pendingPacks.length) await flushPendingPacks();
  return result;
}

function studioHome() {
  const studio = launchRecipe && launchRecipe.studio;
  return studio && String(studio).startsWith("/studio") ? studio : "/studio";
}

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
    accountOrigin: resolveAccountOrigin({ env: process.env, fileCfg }),
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
  try {
    await mainWindow.webContents.executeJavaScript(injectTokenScript(null), true);
  } catch {
    /* page may have navigated away */
  }
}

const { navigationAllowed } = require("./navigation");

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
    const raw = String(url || "");
    if (raw.startsWith("file:")) {
      event.preventDefault();
      try {
        queuePackPath(fileURLToPath(raw));
        flushPendingPacks();
      } catch {
        /* ignore */
      }
      return;
    }
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
    delete headers.Authorization;
    delete headers.authorization;
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

function publishSmokeFailure(message, logPath) {
  if (process.env.ZINTRIQ_SMOKE !== "1") return;
  const body = {
    port: (flaskInfo && flaskInfo.port) || 0,
    token: (flaskInfo && flaskInfo.token) || "",
    flaskPid: (flaskInfo && flaskInfo.pid) || 0,
    logPath: logPath || (flaskInfo && flaskInfo.logPath) || "",
    loaded: false,
    error: String(message || "Flask 启动失败"),
  };
  fs.writeFileSync(userDataPath("smoke-session.json"), JSON.stringify(body), { mode: 0o600 });
}

function installPermissions() {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);
}

function smokeBypass() {
  return process.env.ZINTRIQ_SMOKE === "1";
}

async function sessionValid() {
  if (smokeBypass()) return true;
  const { token, user } = loadSession();
  const origin = studioConfig().accountOrigin;
  if (!token || !origin) return false;
  const check = await cloudHost.verifySession(origin, token);
  if (check.status === 401) {
    clearSession();
    return false;
  }
  if (check.status === 0) return true;
  if (!check.ok) {
    clearSession();
    return false;
  }
  if (check.data && check.data.user) {
    saveSession({ token, user: check.data.user || user });
  }
  return true;
}

async function showLoginGate() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  await mainWindow.loadFile(path.join(__dirname, "login.html"));
}

async function enterApp() {
  if (await sessionValid()) {
    try {
      await pullCloudDrafts();
    } catch {
      /* local drafts still apply after sign-in */
    }
  }
  loadStudio();
  return true;
}

function loadStudio() {
  loadWorkbenchPath(studioHome());
}

function loadDescribe() {
  loadSurfaceWithCurrent("/studio/meta");
}

function loadSimulate() {
  loadSurfaceWithCurrent("/studio/simulate");
}

function loadInstantiate() {
  loadSurfaceWithCurrent("/studio/instantiate");
}

function loadWorkbenchPath(pathname) {
  if (!mainWindow || mainWindow.isDestroyed() || !localOrigin) return;
  mainWindow.loadURL(`${localOrigin}${pathname}`);
}

async function loadSurfaceWithCurrent(basePath) {
  if (!mainWindow || mainWindow.isDestroyed() || !localOrigin) return;
  let pathname = basePath;
  if (flaskInfo) {
    try {
      const listed = await metaHttp.studioHttp(
        flaskInfo,
        { method: "GET", path: "/api/builder-core/meta/index" },
        studioExtra(),
      );
      const slug = listed.status < 300 && listed.body && listed.body.current;
      if (slug) pathname = `${basePath}/${encodeURIComponent(slug)}`;
    } catch {
      /* empty editor */
    }
  }
  mainWindow.loadURL(`${localOrigin}${pathname}`);
}

function loadCommunity() {
  if (!mainWindow || mainWindow.isDestroyed() || !localOrigin) return;
  mainWindow.loadURL(`${localOrigin}/app/community`);
}

function loadSpace() {
  loadWorkbenchPath("/studio/space");
}

function newDescription() {
  if (!mainWindow || mainWindow.isDestroyed() || !localOrigin) return;
  mainWindow.loadURL(`${localOrigin}/studio/meta?new=1`);
}

function createWindow(port) {
  localOrigin = `http://127.0.0.1:${port}`;
  installAppMenu({
    loadStudio,
    loadDescribe,
    loadSimulate,
    loadInstantiate,
    loadCommunity,
    loadSpace,
    newDescription,
    importSite: () => {
      return metaZipHost.importSite({
        window: mainWindow,
        flaskInfo,
        origin: localOrigin,
        loadStudio,
      });
    },
    exportSite: () => {
      return metaZipHost.exportSite({
        window: mainWindow,
        flaskInfo,
      });
    },
    login: () => startLogin(),
    signup: () => startSignup(),
    logout: () => completeLogout(),
    syncCloud: () => pullCloudDrafts(),
    publish: () => publishCurrent(),
    checkUpdates: () => checkForUpdates({ silent: false }),
    activateEditorView: (id) => {
      if (!mainWindow || mainWindow.isDestroyed()) return;
      const safe = String(id || "").replace(/[^a-z0-9_-]/gi, "");
      if (!safe) return;
      return mainWindow.webContents.executeJavaScript(
        `window.ZintriqEditorViews && window.ZintriqEditorViews.activate(${JSON.stringify(safe)})`,
        true
      );
    },
    gitInit: () => hostPrefs.gitInit(app.getPath("userData")),
    gitStatus: async () => {
      const row = hostPrefs.gitStatus(app.getPath("userData"));
      await dialog.showMessageBox(mainWindow, {
        type: "info",
        title: "Git status",
        message: row.ok ? row.text || "clean" : row.error || "git status failed",
      });
    },
    gitCommit: async () => {
      const asked = await dialog.showMessageBox(mainWindow, {
        type: "question",
        buttons: ["Commit", "Cancel"],
        defaultId: 0,
        cancelId: 1,
        title: "Git commit",
        message: "Commit local work in the data folder?",
      });
      if (asked.response !== 0) return;
      return hostPrefs.gitCommit(app.getPath("userData"), "Save local work");
    },
    gitDiff: async () => {
      const row = hostPrefs.gitDiff(app.getPath("userData"));
      await dialog.showMessageBox(mainWindow, {
        type: "info",
        title: "Git diff",
        message: row.ok ? row.text || "clean" : row.error || "git diff failed",
      });
    },
    gitLog: async () => {
      const row = hostPrefs.gitLog(app.getPath("userData"));
      await dialog.showMessageBox(mainWindow, {
        type: "info",
        title: "Git log",
        message: row.ok ? row.text || "empty" : row.error || "git log failed",
      });
    },
    gitIgnore: () => hostPrefs.gitIgnore(app.getPath("userData")),
    exportKeymap: () => {
      const dest = path.join(app.getPath("userData"), "keymap.json");
      const keymap = hostPrefs.loadPrefs(app.getPath("userData")).keymap || hostPrefs.DEFAULT_KEYMAP;
      fs.writeFileSync(dest, JSON.stringify(keymap, null, 2));
      return dest;
    },
    keymap: hostPrefs.loadPrefs(app.getPath("userData")).keymap || hostPrefs.DEFAULT_KEYMAP,
  });
  const prefs = hostPrefs.loadPrefs(app.getPath("userData"));
  const bounds = (prefs.layout && prefs.layout.bounds) || {};
  mainWindow = new BrowserWindow({
    width: bounds.width || 1440,
    height: bounds.height || 900,
    x: bounds.x,
    y: bounds.y,
    minWidth: 1100,
    minHeight: 700,
    title: "Zintriq Studio",
    show: false,
    backgroundColor: "#111111",
    autoHideMenuBar: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webviewTag: false,
    },
  });
  hardenContents(mainWindow.webContents, port);
  mainWindow.once("ready-to-show", () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
  });
  mainWindow.webContents.on("did-finish-load", () => {
    injectSessionIntoPage();
    publishSmoke(true);
    flushPendingPacks();
  });
  enterApp();
  mainWindow.on("close", () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const b = mainWindow.getBounds();
    hostPrefs.savePrefs(app.getPath("userData"), {
      layout: Object.assign({}, hostPrefs.loadPrefs(app.getPath("userData")).layout || {}, { bounds: b }),
    });
  });
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
    document.getElementById("log").textContent = ${JSON.stringify(logPath || "")};
    var tail = document.getElementById("tail");
    if (tail) tail.textContent = ${JSON.stringify((lastFlaskLaunch().logTail || "").slice(-2000))};`;
  await win.webContents.executeJavaScript(script, true);
}

async function exchangePkce({ code, codeVerifier, redirectUri }) {
  const origin = studioConfig().accountOrigin.replace(/\/$/, "");
  const res = await fetch(`${origin}/api/desktop/token`, {
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

async function beginWebAuth() {
  const cfg = studioConfig();
  if (!cfg.accountOrigin) {
    throw new Error("Set ZINTRIQ_ACCOUNT_ORIGIN (see desktop/.env.desktop.example)");
  }
  const { verifier, challenge } = createPkcePair();
  const state = require("crypto").randomBytes(16).toString("hex");
  pendingAuth = { verifier, state, redirectUri: cfg.redirectUri };
  const authorizeUrl = buildDesktopAuthorizeUrl({
    origin: cfg.accountOrigin,
    clientId: "zintriq-desktop",
    redirectUri: cfg.redirectUri,
    state,
    codeChallenge: challenge,
    os: process.platform,
    version: app.getVersion(),
    deviceName: require("os").hostname(),
  });
  return { origin: cfg.accountOrigin, authorizeUrl };
}

async function startLogin() {
  const { authorizeUrl } = await beginWebAuth();
  await shell.openExternal(authorizeUrl);
  return { ok: true, opened: true };
}

async function startSignup() {
  const { origin, authorizeUrl } = await beginWebAuth();
  const url = buildDesktopRegisterUrl({ origin, authorizeUrl });
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
    await showLoginGate();
  }
  return { ok: true };
}

function studioExtra() {
  return { "X-Studio-Client": "desktop" };
}

async function requireCloudPublish(origin, token) {
  const ent = await cloudHost.entitlement(origin, token);
  if (!ent.ok) {
    if (ent.status === 401) throw new Error("Log in first (File → Log in…)");
    throw new Error((ent.data && ent.data.error) || "Could not check cloud subscription");
  }
  const data = ent.data || {};
  // When billing is off on the portal, entitlement.publish is true.
  if (data.billing_enabled && !data.publish) {
    throw new Error(
      "Cloud subscription required for Publish & sync. Local export stays free — open Pricing on the website."
    );
  }
  return data;
}

const cloudDraftRevisions = Object.create(null);

async function pullCloudDrafts() {
  const { token } = loadSession();
  const origin = studioConfig().accountOrigin;
  if (!token || !origin || !flaskInfo) return { ok: false };
  try {
    await requireCloudPublish(origin, token);
  } catch (err) {
    return { ok: false, error: err && err.message ? err.message : "Sync requires a cloud subscription" };
  }
  const listed = await cloudHost.listDrafts(origin, token);
  if (!listed.ok) return listed;
  const rows = (listed.data && listed.data.drafts) || [];
  let applied = 0;
  const conflicts = [];
  for (const item of rows) {
    const slug = item.slug;
    if (item.deleted_at) {
      await metaHttp.studioHttp(
        flaskInfo,
        {
          method: "POST",
          path: "/api/builder-core/meta/drafts/remove",
          json: { slug },
        },
        studioExtra(),
      );
      delete cloudDraftRevisions[slug];
      applied += 1;
      continue;
    }
    const remote = await cloudHost.getDraft(origin, token, slug);
    if (!remote.ok || !remote.data || !remote.data.code) continue;
    cloudDraftRevisions[slug] = Number(remote.data.revision || item.revision || 1) || 1;
    const local = await metaHttp.studioHttp(
      flaskInfo,
      { method: "GET", path: `/api/builder-core/meta/drafts/${encodeURIComponent(slug)}` },
      studioExtra(),
    );
    const localAt = local.status < 300 && local.body ? String(local.body.updated_at || "") : "";
    const remoteAt = String(remote.data.updated_at || "");
    const localCode = local.status < 300 && local.body ? String(local.body.code || "") : "";
    if (localCode && localCode !== String(remote.data.code || "") && localAt && remoteAt && localAt >= remoteAt) {
      conflicts.push(slug);
      continue;
    }
    if (localAt && remoteAt && localAt >= remoteAt && localCode) continue;
    await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/drafts",
        json: {
          slug: remote.data.slug,
          code: remote.data.code,
          events: remote.data.events || "",
          title: remote.data.title || remote.data.slug,
        },
      },
      studioExtra(),
    );
    applied += 1;
  }
  return { ok: true, count: applied, conflicts };
}

async function maybePushDraft(payload, result) {
  if (!result || result.status >= 300) return;
  const path = String((payload && payload.path) || "");
  const method = String((payload && payload.method) || "").toUpperCase();
  if (method !== "POST" || path !== "/api/builder-core/meta/drafts") return;
  const { token } = loadSession();
  const origin = studioConfig().accountOrigin;
  if (!token || !origin || !result.body) return;
  try {
    await requireCloudPublish(origin, token);
    const slug = String(result.body.slug || "");
    const pushed = await cloudHost.pushDraft(origin, token, {
      ...result.body,
      base_revision: cloudDraftRevisions[slug],
    });
    if (pushed.status === 409) {
      return;
    }
    if (pushed.ok && pushed.data && pushed.data.revision != null) {
      cloudDraftRevisions[slug] = Number(pushed.data.revision) || cloudDraftRevisions[slug];
    }
  } catch {
    /* stay local — never block save/export */
  }
}

async function publishCurrent() {
  const { token } = loadSession();
  const origin = studioConfig().accountOrigin;
  if (!token || !origin) throw new Error("Log in first (File → Log in…)");
  await requireCloudPublish(origin, token);
  const listed = await metaHttp.studioHttp(
    flaskInfo,
    { method: "GET", path: "/api/builder-core/meta/drafts" },
    studioExtra(),
  );
  const slug = listed.body && listed.body.current;
  if (!slug) throw new Error("Save a description first");
  const draft = await metaHttp.studioHttp(
    flaskInfo,
    { method: "GET", path: `/api/builder-core/meta/drafts/${encodeURIComponent(slug)}` },
    studioExtra(),
  );
  if (draft.status >= 300 || !draft.body) throw new Error("Could not read the current draft");
  const pushed = await cloudHost.pushDraft(origin, token, {
    ...draft.body,
    base_revision: cloudDraftRevisions[slug],
  });
  if (!pushed.ok) {
    throw new Error((pushed.data && pushed.data.error) || "Could not sync draft before publish");
  }
  if (pushed.data && pushed.data.revision != null) {
    cloudDraftRevisions[slug] = Number(pushed.data.revision) || 1;
  }
  const published = await cloudHost.publishDraft(origin, token, slug, slug);
  if (!published.ok) throw new Error((published.data && published.data.error) || "Publish failed");
  const publicId = published.data && published.data.id;
  if (publicId) {
    const assets = await metaHttp.studioHttp(
      flaskInfo,
      { method: "GET", path: `/api/builder-core/meta/sites/${encodeURIComponent(slug)}/assets` },
      studioExtra(),
    );
    const names = (assets.body && assets.body.assets) || [];
    for (const name of names) {
      const file = await metaHttp.studioHttp(
        flaskInfo,
        {
          method: "GET",
          path: `/api/builder-core/meta/sites/${encodeURIComponent(slug)}/assets/${encodeURIComponent(name)}`,
        },
        studioExtra(),
      );
      if (file.status >= 300 || !file.raw || !file.raw.length) continue;
      const bytes = Buffer.isBuffer(file.raw) ? file.raw : Buffer.from(file.raw);
      const ext = String(name).split(".").pop() || "png";
      const mime =
        ext === "jpg" || ext === "jpeg"
          ? "image/jpeg"
          : ext === "gif"
            ? "image/gif"
            : ext === "webp"
              ? "image/webp"
              : "image/png";
      await cloudHost.putShareAsset(origin, token, publicId, name, bytes, mime);
    }
  }
  const path = (published.data && published.data.url) || "";
  await shell.openExternal(`${String(origin).replace(/\/$/, "")}${path}`);
  return published.data;
}

async function openCommunityShare(shareId, surface) {
  const origin = studioConfig().accountOrigin;
  if (!origin || !flaskInfo) return;
  const share = await cloudHost.getShare(origin, shareId);
  if (!share.ok || !share.data || !share.data.code) return;
  await metaHttp.studioHttp(
    flaskInfo,
    {
      method: "POST",
      path: "/api/builder-core/meta/drafts",
      json: {
        slug: share.data.slug,
        code: share.data.code,
        events: share.data.events || "",
      },
    },
    studioExtra(),
  );
  if (mainWindow && !mainWindow.isDestroyed() && localOrigin) {
    const routes = { describe: "/studio/meta", simulate: "/studio/simulate", instantiate: "/studio/instantiate" };
    const base = routes[String(surface || "describe")] || "/studio/meta";
    await mainWindow.loadURL(`${localOrigin}${base}/${encodeURIComponent(share.data.slug)}`);
    mainWindow.focus();
  }
}

async function checkForUpdates({ silent } = {}) {
  if (process.env.ZINTRIQ_SMOKE === "1") return;
  const origin = studioConfig().accountOrigin;
  const current = app.getVersion();
  const homepage = (() => {
    try {
      return String(require("./package.json").homepage || "").replace(/\/$/, "");
    } catch {
      return "";
    }
  })();
  const updateOrigin =
    String(process.env.ZINTRIQ_UPDATE_ORIGIN || "").replace(/\/$/, "") ||
    (app.isPackaged ? homepage : origin);
  if (updater.canAutoInstall({ packaged: app.isPackaged, env: process.env }) && updateOrigin) {
    try {
      const { autoUpdater } = require("electron-updater");
      const result = await updater.installFromFeed({
        feedUrl: updater.updateFeedUrl(updateOrigin),
        dialog,
        autoUpdater,
      });
      if (result.status === "none" && !silent && mainWindow && !mainWindow.isDestroyed()) {
        await dialog.showMessageBox(mainWindow, {
          type: "info",
          message: "Zintriq is up to date.",
          detail: `This app is ${current}.`,
        });
      }
      return;
    } catch (err) {
      if (!silent && mainWindow && !mainWindow.isDestroyed()) {
        await dialog.showMessageBox(mainWindow, {
          type: "warning",
          message: "Could not install the update.",
          detail: String(err && err.message ? err.message : err),
        });
      }
      return;
    }
  }
  if (!updateOrigin) {
    if (!silent && mainWindow && !mainWindow.isDestroyed()) {
      await dialog.showMessageBox(mainWindow, {
        type: "info",
        message: "Could not check for updates.",
        detail: "No update server is configured.",
      });
    }
    return;
  }
  const feed = await cloudHost.getUpdates(updateOrigin);
  if (!feed.ok || !feed.data || !feed.data.version) {
    if (!silent && mainWindow && !mainWindow.isDestroyed()) {
      await dialog.showMessageBox(mainWindow, {
        type: "warning",
        message: "Could not check for updates.",
        detail: "The update server did not return a version. Try again when you are online.",
      });
    }
    return;
  }
  const remote = String(feed.data.version);
  if (!updater.isNewer(remote, current)) {
    if (!silent && mainWindow && !mainWindow.isDestroyed()) {
      await dialog.showMessageBox(mainWindow, {
        type: "info",
        message: "Zintriq is up to date.",
        detail: `This app is ${current}.`,
      });
    }
    return;
  }
  const choice = await dialog.showMessageBox(mainWindow || undefined, {
    type: "info",
    buttons: ["Download", "Later"],
    defaultId: 0,
    cancelId: 1,
    message: `Version ${remote} is available.`,
    detail: String(feed.data.notes || "Installers are on the website."),
  });
  if (choice.response === 0) {
    const path = String(feed.data.download || "/download");
    await shell.openExternal(`${String(updateOrigin).replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`);
  }
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
    await enterApp();
    await flushPendingPacks();
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
    return result;
  }
  try {
    const dest = new URL(urlString);
    if (dest.hostname === "c") {
      if (!(await sessionValid())) {
        await showLoginGate();
        return;
      }
      const shareId = String(dest.pathname || "").replace(/^\//, "");
      if (shareId) await openCommunityShare(shareId);
      return;
    }
  } catch {
    /* fall through */
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
      accountOrigin: cfg.accountOrigin || "",
      hasAccountOrigin: Boolean(cfg.accountOrigin),
      protocol: PROTOCOL,
    };
  });
  ipcMain.handle("studio:get-token", () => loadSession().token);
  ipcMain.handle("studio:get-user", () => loadSession().user);
  ipcMain.handle("studio:probe", () => {
    const info = hostPrefs.probe();
    info.dark = Boolean(nativeTheme.shouldUseDarkColors);
    info.flask = Boolean(flaskInfo && flaskInfo.port);
    info.host = flaskInfo ? `127.0.0.1:${flaskInfo.port}` : "";
    info.ok = Boolean(flaskInfo && flaskInfo.port);
    info.logPath = (flaskInfo && flaskInfo.logPath) || "";
    const launch = lastFlaskLaunch();
    info.exitCode = launch.exitCode;
    info.portInUse = Boolean(launch.portInUse);
    info.tokenOk = launch.tokenOk !== false;
    info.logTail = String(launch.logTail || "").slice(-2000);
    if (!info.ok) {
      info.reason = launch.reason || "flask_down";
      if (info.portInUse) {
        info.next = "Port is in use. Quit the other Zintriq copy, then reopen. Log: " + (info.logPath || "userData/logs/flask.log");
      } else if (!info.tokenOk) {
        info.next = "Desktop token mismatch. Quit Zintriq and open it again. Do not paste a website URL. Log: " + (info.logPath || "userData/logs/flask.log");
      } else {
        info.next =
          "Local host is down (exit " +
          String(info.exitCode == null ? "?" : info.exitCode) +
          "). Quit Zintriq and open it again. Log: " +
          (info.logPath || "userData/logs/flask.log");
      }
    } else {
      info.reason = "";
      info.next = "";
    }
    return info;
  });
  ipcMain.handle("studio:layout-load", () => hostPrefs.loadPrefs(app.getPath("userData")).layout || {});
  ipcMain.handle("studio:layout-save", (_event, layout) => {
    const payload = layout || {};
    const saved = hostPrefs.savePrefs(app.getPath("userData"), {
      layout: payload,
      editorGroups: payload.groups || payload.editorGroups || [],
    }).layout;
    BrowserWindow.getAllWindows().forEach((win) => {
      if (!win.isDestroyed() && win.webContents !== _event.sender) {
        win.webContents.send("studio:layout-changed", saved || {});
      }
    });
    return saved;
  });
  ipcMain.handle("studio:keymap", () => hostPrefs.loadPrefs(app.getPath("userData")).keymap || hostPrefs.DEFAULT_KEYMAP);
  ipcMain.handle("studio:keymap-save", (_event, keymap) => {
    const next = keymap || hostPrefs.DEFAULT_KEYMAP;
    const conflicts = hostPrefs.keymapConflicts(next);
    if (conflicts.length) {
      return { ok: false, conflicts, keymap: hostPrefs.loadPrefs(app.getPath("userData")).keymap || hostPrefs.DEFAULT_KEYMAP };
    }
    const saved = hostPrefs.savePrefs(app.getPath("userData"), { keymap: next }).keymap;
    return { ok: true, conflicts: [], keymap: saved };
  });
  ipcMain.handle("studio:keymap-export", () => {
    const keymap = hostPrefs.loadPrefs(app.getPath("userData")).keymap || hostPrefs.DEFAULT_KEYMAP;
    const dest = path.join(app.getPath("userData"), "keymap.json");
    fs.writeFileSync(dest, JSON.stringify(keymap, null, 2));
    return { ok: true, path: dest, keymap };
  });
  ipcMain.handle("studio:keymap-import", (_event, payload) => {
    let next = payload;
    if (typeof payload === "string") {
      try {
        next = JSON.parse(payload);
      } catch {
        return { ok: false, error: "keymap json invalid", conflicts: [], keymap: hostPrefs.DEFAULT_KEYMAP };
      }
    }
    const merged = hostPrefs.mergeKeymap(next);
    const conflicts = hostPrefs.keymapConflicts(merged);
    if (conflicts.length) return { ok: false, conflicts, keymap: hostPrefs.loadPrefs(app.getPath("userData")).keymap };
    const saved = hostPrefs.savePrefs(app.getPath("userData"), { keymap: merged }).keymap;
    return { ok: true, conflicts: [], keymap: saved };
  });
  ipcMain.handle("studio:relaunch", () => {
    app.relaunch();
    app.exit(0);
    return { ok: true };
  });
  ipcMain.handle("studio:git-diff", () => hostPrefs.gitDiff(app.getPath("userData")));
  ipcMain.handle("studio:git-log", () => hostPrefs.gitLog(app.getPath("userData")));
  ipcMain.handle("studio:git-ignore", () => hostPrefs.gitIgnore(app.getPath("userData")));
  ipcMain.handle("studio:dirty", (_event, dirty) => {
    hostPrefs.savePrefs(app.getPath("userData"), { dirty: Boolean(dirty) });
    return { ok: true };
  });
  ipcMain.handle("studio:notify", (_event, payload) => {
    const title = String((payload && payload.title) || "Zintriq");
    const body = String((payload && payload.body) || "");
    if (Notification.isSupported()) {
      new Notification({ title, body }).show();
    }
    return { ok: true };
  });
  ipcMain.handle("studio:git-init", () => hostPrefs.gitInit(app.getPath("userData")));
  ipcMain.handle("studio:git-status", () => hostPrefs.gitStatus(app.getPath("userData")));
  ipcMain.handle("studio:git-commit", (_event, payload) =>
    hostPrefs.gitCommit(app.getPath("userData"), String((payload && payload.message) || "Save local work"))
  );
  ipcMain.handle("studio:new-window", (_event, studioPath) => {
    if (!flaskInfo) return { ok: false };
    const extra = new BrowserWindow({
      width: 1200,
      height: 800,
      title: "Zintriq Studio",
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webviewTag: false,
      },
    });
    hardenContents(extra.webContents, flaskInfo.port);
    const rel = String(studioPath || "/studio").startsWith("/") ? String(studioPath || "/studio") : "/studio";
    extra.loadURL(`http://127.0.0.1:${flaskInfo.port}${rel}`);
    const prefs = hostPrefs.loadPrefs(app.getPath("userData"));
    const windows = Array.isArray(prefs.windows) ? prefs.windows.slice() : [];
    windows.push({ host: "127.0.0.1", path: rel, port: flaskInfo.port });
    hostPrefs.savePrefs(app.getPath("userData"), { windows: windows.slice(-8) });
    return { ok: true, host: "127.0.0.1" };
  });
  ipcMain.handle("studio:open-pack", async (_event, filePath) => {
    queuePackPath(filePath);
    return flushPendingPacks();
  });
  ipcMain.handle("studio:login", () => startLogin());
  ipcMain.handle("studio:signup", () => startSignup());
  ipcMain.handle("studio:logout", () => completeLogout());
  ipcMain.handle("studio:http", async (event, payload) => {
    const allowed = BrowserWindow.getAllWindows().some((win) => !win.isDestroyed() && win.webContents === event.sender);
    if (!allowed) {
      return { status: 403, body: { error: "forbidden" }, text: "" };
    }
    const extra = { "X-Studio-Client": "desktop" };
    if (localOrigin) {
      const cookies = await session.defaultSession.cookies.get({ url: localOrigin });
      const cookie = cookies.map((item) => `${item.name}=${item.value}`).join("; ");
      if (cookie) extra.Cookie = cookie;
    }
    const result = await metaHttp.studioHttp(flaskInfo, payload || {}, extra);
    maybePushDraft(payload || {}, result);
    return result;
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
  ipcMain.handle("studio:community-catalog", async (_event, query) => {
    const origin = studioConfig().accountOrigin;
    const result = await cloudHost.listCatalog(origin, query || {});
    return result.data || { packages: [], descriptions: [] };
  });
  ipcMain.handle("studio:community-mine", async () => {
    const origin = studioConfig().accountOrigin;
    const { token } = loadSession();
    const result = await cloudHost.listMine(origin, token);
    return result.data || { shares: [], drafts: [], error: result.data && result.data.error };
  });
  ipcMain.handle("studio:plugin-catalog", async () => {
    if (!flaskInfo) return { packs: [] };
    const listed = await metaHttp.studioHttp(
      flaskInfo,
      { method: "GET", path: "/api/builder-core/meta/plugins" },
      studioExtra(),
    );
    return listed.body || { packs: [] };
  });
  ipcMain.handle("studio:plugin-install", async (_event, payload) => {
    if (!flaskInfo) return { ok: false, error: "local host down" };
    const body = payload && typeof payload === "object" ? payload : { id: payload };
    const listed = await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/plugins/install",
        json: { csrf_token: body.csrf || "", id: String(body.id || "") },
      },
      studioExtra(),
    );
    return { ok: listed.status < 300, data: listed.body || {}, error: listed.body && listed.body.error };
  });
  ipcMain.handle("studio:plugin-disable", async (_event, payload) => {
    if (!flaskInfo) return { ok: false, error: "local host down" };
    const body = payload && typeof payload === "object" ? payload : { id: payload };
    const listed = await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/plugins/disable",
        json: { csrf_token: body.csrf || "", id: String(body.id || "") },
      },
      studioExtra(),
    );
    return { ok: listed.status < 300, data: listed.body || {}, error: listed.body && listed.body.error };
  });
  ipcMain.handle("studio:plugin-remove", async (_event, payload) => {
    if (!flaskInfo) return { ok: false, error: "local host down" };
    const body = payload && typeof payload === "object" ? payload : { id: payload };
    const listed = await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/plugins/remove",
        json: { csrf_token: body.csrf || "", id: String(body.id || ""), delete_draft: Boolean(body.delete_draft) },
      },
      studioExtra(),
    );
    return { ok: listed.status < 300, data: listed.body || {}, error: listed.body && listed.body.error };
  });
  ipcMain.handle("studio:plugin-project", async (_event, payload) => {
    if (!flaskInfo) return { ok: false, error: "local host down" };
    const body = payload && typeof payload === "object" ? payload : {};
    const listed = await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/plugins/project",
        json: { csrf_token: body.csrf || "", ids: body.ids || [], title: "plugin-project" },
      },
      studioExtra(),
    );
    return { ok: listed.status < 300, data: listed.body || {}, error: listed.body && listed.body.error };
  });
  ipcMain.handle("studio:plugin-publish", async (_event, payload) => {
    const origin = studioConfig().accountOrigin;
    const { token } = loadSession();
    if (!origin || !token) {
      startLogin().catch(() => {});
      return { ok: false, error: "Sign in to publish to your account" };
    }
    const body = payload && typeof payload === "object" ? payload : {};
    return cloudHost.publishPlugin(origin, token, body.pack || body);
  });
  ipcMain.handle("studio:plugin-from-share", async (_event, payload) => {
    if (!flaskInfo) return { ok: false, error: "local host down" };
    const origin = studioConfig().accountOrigin;
    const id = String((payload && payload.id) || "");
    const share = await cloudHost.getShare(origin, id);
    if (!share.ok || !share.data || !share.data.code) {
      return { ok: false, error: (share.data && share.data.error) || "share missing" };
    }
    let pack = share.data.code;
    if (typeof pack === "string") {
      try {
        pack = JSON.parse(pack);
      } catch {
        return { ok: false, error: "pack is not JSON" };
      }
    }
    const listed = await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/plugins/install",
        json: { csrf_token: (payload && payload.csrf) || "", manifest: pack },
      },
      studioExtra(),
    );
    return { ok: listed.status < 300, data: listed.body || {}, error: listed.body && listed.body.error };
  });
  ipcMain.handle("studio:open-share", async (_event, id, surface) => {
    await openCommunityShare(String(id || ""), surface);
    return { ok: true };
  });
  ipcMain.handle("studio:publish", async () => {
    try {
      const data = await publishCurrent();
      return { ok: true, data };
    } catch (err) {
      return { ok: false, error: err && err.message ? err.message : "Publish failed" };
    }
  });
  ipcMain.handle("studio:cloud-entitlement", async () => {
    const { token } = loadSession();
    const origin = studioConfig().accountOrigin;
    if (!token || !origin) {
      return {
        ok: false,
        data: {
          billing_enabled: false,
          cloud_active: false,
          publish: false,
          sync: false,
          local_export: true,
        },
      };
    }
    return cloudHost.entitlement(origin, token);
  });
  ipcMain.handle("studio:unpublish", async (_event, id) => {
    const origin = studioConfig().accountOrigin;
    const { token } = loadSession();
    if (!origin || !token) return { ok: false, error: "not signed in" };
    return cloudHost.unpublishShare(origin, token, String(id || ""));
  });
  ipcMain.handle("studio:sync", async () => pullCloudDrafts());
  ipcMain.handle("studio:collab-sync", async (_event, slug) => {
    const { token } = loadSession();
    const origin = studioConfig().accountOrigin;
    const key = String(slug || "").trim();
    if (!token || !origin || !flaskInfo || !key) return { ok: false };
    const local = await metaHttp.studioHttp(
      flaskInfo,
      { method: "GET", path: `/api/builder-core/meta/collab/${encodeURIComponent(key)}` },
      studioExtra(),
    );
    const remote = await cloudHost.getCollab(origin, token, key);
    const incoming = remote.ok && remote.data ? { clock: remote.data.clock, doc: remote.data.doc } : {};
    const merged = await metaHttp.studioHttp(
      flaskInfo,
      {
        method: "POST",
        path: "/api/builder-core/meta/collab/merge",
        json: { slug: key, clock: incoming.clock || {}, doc: incoming.doc || (local.body && local.body.doc) || null },
      },
      studioExtra(),
    );
    if (merged.status < 300 && merged.body) {
      await cloudHost.pushCollab(origin, token, key, {
        clock: merged.body.clock || {},
        doc: merged.body.doc,
      });
    }
    return { ok: merged.status < 300, data: merged.body || {} };
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
  app.on("open-file", (event, filePath) => {
    event.preventDefault();
    queuePackPath(filePath);
    flushPendingPacks();
  });
  app.on("second-instance", (_event, argv) => {
    const url = argv.find((arg) => String(arg).startsWith(`${PROTOCOL}://`));
    if (url) handleAuthUrl(url).catch(() => {});
    metaZipHost.packPathsFromArgv(argv).forEach(queuePackPath);
    flushPendingPacks();
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    installPermissions();
    registerProtocol();
    registerIpc();
    const prefs = hostPrefs.loadPrefs(app.getPath("userData"));
    if (prefs.proxy) {
      await session.defaultSession.setProxy({ proxyRules: String(prefs.proxy) });
    }
    const python = resolvePythonExecutable();
    if (!pythonExists(python)) {
      await showError("请先创建虚拟环境并安装依赖", "");
      return;
    }
    try {
      const userData = app.getPath("userData");
      launchRecipe = loadLaunchRecipe(userData);
      flaskInfo = await startFlask({
        userData,
        pythonPath: python,
        appVersion: app.getVersion(),
      });
      writeSmokeTokenFile();
      armLoopback(flaskInfo.port, flaskInfo.token);
      if (process.env.ZINTRIQ_SMOKE === "1") installSmokeGuard(flaskInfo.port);
      createWindow(flaskInfo.port);
      metaZipHost.packPathsFromArgv(process.argv).forEach(queuePackPath);
      checkForUpdates({ silent: true }).catch(() => {});
      const bootUrl = process.argv.find((arg) => String(arg).startsWith(`${PROTOCOL}://`));
      if (bootUrl) handleAuthUrl(bootUrl).catch(() => {});
    } catch (err) {
      const message = err && err.message ? err.message : "Flask 启动失败";
      const logPath = err && err.logPath ? err.logPath : "";
      publishSmokeFailure(message, logPath);
      await showError(message, logPath);
    }
  });

  app.on("open-url", (event, url) => {
    event.preventDefault();
    handleAuthUrl(url).catch(() => {});
  });

  app.on("before-quit", (event) => {
    if (quitStarted) return;
    const dirty = Boolean(hostPrefs.loadPrefs(app.getPath("userData")).dirty);
    if (dirty && process.env.ZINTRIQ_SMOKE !== "1") {
      const choice = dialog.showMessageBoxSync({
        type: "question",
        buttons: ["Cancel", "Quit"],
        defaultId: 0,
        cancelId: 0,
        message: "Unsaved work. Quit anyway?",
      });
      if (choice === 0) {
        event.preventDefault();
        return;
      }
    }
    event.preventDefault();
    quitStarted = true;
    try {
      fs.rmSync(userDataPath("smoke-session.json"), { force: true });
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
