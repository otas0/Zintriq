/**
 * Starts the local Flask process for the desktop shell.
 * The startup token stays in the child environment and is never written to logs.
 */

const { spawn, spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const MAX_LOG_BYTES = 1024 * 1024;
const MAX_LOG_FILES = 3;
const READY_LINE = /^ZINTRIQ_READY pid=(\d+) port=(\d+)\s*$/;

let currentChild = null;
let currentDaemon = null;
let shuttingDown = false;
let flaskHook = null;
let lastLaunch = { exitCode: null, portInUse: false, tokenOk: true, logTail: "", reason: "" };

function lastFlaskLaunch() {
  return lastLaunch;
}

function onFlaskReady(fn) {
  flaskHook = typeof fn === "function" ? fn : null;
}

function repoRoot() {
  return path.resolve(__dirname, "..");
}

function configDir() {
  const home = os.homedir();
  if (process.platform === "darwin") return path.join(home, "Library", "Application Support");
  if (process.platform === "win32") return process.env.APPDATA || path.join(home, "AppData", "Roaming");
  return process.env.XDG_CONFIG_HOME || path.join(home, ".config");
}

function devUserDataDir() {
  return path.join(configDir(), "Zintriq-dev");
}

function smokeUserDataDir() {
  return path.join(configDir(), "Zintriq-smoke");
}

function resolvePythonExecutable() {
  if (process.env.ZINTRIQ_PYTHON) return process.env.ZINTRIQ_PYTHON;
  if (process.env.ZINTRIQ_PACKAGED === "1" && process.resourcesPath) {
    const name = process.platform === "win32" ? "zintriq-server.exe" : "zintriq-server";
    return path.join(process.resourcesPath, "zintriq-server", name);
  }
  const root = repoRoot();
  if (process.platform === "win32") return path.join(root, ".venv", "Scripts", "python.exe");
  return path.join(root, ".venv", "bin", "python");
}

function pythonExists(pythonPath) {
  try {
    return fs.existsSync(pythonPath);
  } catch {
    return false;
  }
}

function scrub(text, token) {
  const value = String(text == null ? "" : text);
  if (!token) return value;
  return value.split(token).join("<redacted>");
}

class RotatingLog {
  constructor(filePath, token) {
    this.filePath = filePath;
    this.token = token;
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
  }

  write(chunk) {
    const text = scrub(Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk), this.token);
    const buf = Buffer.from(text);
    this._rotateIfNeeded(buf.length);
    fs.appendFileSync(this.filePath, buf);
  }

  _rotateIfNeeded(incoming) {
    let size = 0;
    try {
      size = fs.statSync(this.filePath).size;
    } catch {
      return;
    }
    if (size + incoming <= MAX_LOG_BYTES) return;
    const oldest = `${this.filePath}.${MAX_LOG_FILES - 1}`;
    fs.rmSync(oldest, { force: true });
    for (let index = MAX_LOG_FILES - 2; index >= 1; index -= 1) {
      const src = `${this.filePath}.${index}`;
      const dest = `${this.filePath}.${index + 1}`;
      if (fs.existsSync(src)) fs.renameSync(src, dest);
    }
    if (fs.existsSync(this.filePath)) fs.renameSync(this.filePath, `${this.filePath}.1`);
  }
}

function pickFreePort() {
  return new Promise((resolve, reject) => {
    const server = http.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function probeHealth(port, token) {
  return new Promise((resolve) => {
    const req = http.get(
      {
        hostname: "127.0.0.1",
        port,
        path: "/healthz",
        headers: {
          Host: `127.0.0.1:${port}`,
          "X-Zintriq-Desktop-Token": token,
        },
        timeout: 1000,
      },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function forceKill(child) {
  if (!child || child.exitCode !== null || !child.pid) return;
  const pid = child.pid;
  if (process.platform === "win32") {
    // Retry once: CI runners sometimes return before the tree is gone.
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const result = spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
        windowsHide: true,
        encoding: "utf8",
      });
      const code = result.status;
      // 0 = killed; 128 = already gone.
      if (code === 0 || code === 128) return;
      spawnSync("cmd", ["/c", "ping", "127.0.0.1", "-n", "2", ">nul"], { windowsHide: true });
    }
    return;
  }
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      /* already gone */
    }
  }
}

function signalTerm(child) {
  if (!child || child.exitCode !== null || !child.pid) return;
  if (process.platform === "win32") return;
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    try {
      child.kill("SIGTERM");
    } catch {
      /* already gone */
    }
  }
}

function stopChild(child, timeoutMs) {
  if (!child || child.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      forceKill(child);
      resolve();
    }, timeoutMs);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    try {
      child.stdin.end();
    } catch {
      /* pipe already closed */
    }
    signalTerm(child);
  });
}

function bindOutput(child, log, onLine) {
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    log.write(chunk);
    buffer += chunk.toString("utf8");
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || "";
    for (const line of lines) onLine(line);
  });
  child.stderr.on("data", (chunk) => log.write(chunk));
}

function waitForReady(child, expectedPort, timeoutMs) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.off("exit", onExit);
      fn(value);
    };
    const timer = setTimeout(() => finish(reject, new Error("等待 ZINTRIQ_READY 超时")), timeoutMs);
    const onExit = (code) => finish(reject, new Error(`Flask 提前退出 (${code})`));
    child.on("exit", onExit);
    child._zintriqOnLine = (line) => {
      const match = READY_LINE.exec(line);
      if (!match) return;
      const pid = Number(match[1]);
      const port = Number(match[2]);
      // Windows can announce a worker pid while Node tracks the launcher pid.
      const pidOk = process.platform === "win32" || pid === child.pid;
      if (!pidOk || port !== expectedPort) {
        finish(reject, new Error(`ZINTRIQ_READY 不匹配 pid=${pid} port=${port}`));
        return;
      }
      finish(resolve, { pid, port });
    };
  });
}

async function waitForHealth(port, token, child, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Flask 提前退出 (${child.exitCode})`);
    if (await probeHealth(port, token)) return;
    await sleep(200);
  }
  throw new Error("healthz 未就绪");
}

function stopDaemon() {
  if (!currentDaemon) return;
  forceKill(currentDaemon);
  currentDaemon = null;
}

function spawnCollabDaemon({ pythonPath, userData }) {
  stopDaemon();
  if (process.env.ZINTRIQ_SMOKE === "1" || process.env.ZINTRIQ_COLLAB_DAEMON === "0") return null;
  if (/zintriq-server(\.exe)?$/i.test(pythonPath)) return null;
  const env = { ...process.env };
  env.PYTHONUNBUFFERED = "1";
  env.ZINTRIQ_DATA_DIR = userData;
  env.ZINTRIQ_COLLAB_INTERVAL = env.ZINTRIQ_COLLAB_INTERVAL || "0.5";
  const child = spawn(pythonPath, ["-m", "meta.collab.daemon", userData], {
    cwd: repoRoot(),
    env,
    detached: process.platform !== "win32",
    windowsHide: true,
    stdio: "ignore",
  });
  currentDaemon = child;
  if (typeof child.unref === "function") child.unref();
  return child;
}

function launchRecipePath(userData) {
  const slug = String(process.env.ZINTRIQ_HOST_SLUG || "zintriq").replace(/[^a-z0-9_-]/gi, "") || "zintriq";
  return path.join(userData, "desktop", slug, "launch.json");
}

function loadLaunchRecipe(userData) {
  const file = launchRecipePath(userData);
  if (!fs.existsSync(file)) return null;
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
  if (!raw || typeof raw !== "object") return null;
  const bind = String(raw.bind || "127.0.0.1");
  if (bind !== "127.0.0.1") return null;
  const studioRaw = String(raw.studio || "/studio");
  const studio = studioRaw === "/studio" || studioRaw.startsWith("/studio/") ? studioRaw : "/studio";
  const editors = Array.isArray(raw.editors) ? raw.editors.map((id) => String(id)) : [];
  return {
    bind: "127.0.0.1",
    dataDir: String(raw.data_dir || userData),
    editors,
    env: raw.env && typeof raw.env === "object" ? raw.env : {},
    file,
    loopback: true,
    studio,
    wan: false,
  };
}

function mergeLaunchEnv(env, recipe) {
  if (!recipe) return env;
  env.ZINTRIQ_DESKTOP = "1";
  env.ZINTRIQ_HOST = "127.0.0.1";
  const skip = { ZINTRIQ_DESKTOP_TOKEN: true, PORT: true, HOST: true };
  Object.keys(recipe.env || {}).forEach((key) => {
    if (skip[key]) return;
    if (key === "ZINTRIQ_HOST") {
      env.ZINTRIQ_HOST = "127.0.0.1";
      return;
    }
    env[key] = String(recipe.env[key]);
  });
  return env;
}

function spawnFlask({ pythonPath, userData, token, port, appVersion }) {
  const env = mergeLaunchEnv({ ...process.env }, loadLaunchRecipe(userData));
  env.PYTHONUNBUFFERED = "1";
  env.PYTHONDONTWRITEBYTECODE = "1";
  env.ZINTRIQ_DESKTOP = "1";
  env.ZINTRIQ_DATA_DIR = userData;
  env.ZINTRIQ_DESKTOP_TOKEN = token;
  env.ZINTRIQ_APP_VERSION = appVersion || process.env.ZINTRIQ_APP_VERSION || "0.0.0";
  env.PORT = String(port);
  delete env.HOST;
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  delete env.LD_LIBRARY_PATH;
  const packaged = /zintriq-server(\.exe)?$/i.test(pythonPath);
  const args = packaged ? [] : [path.join(repoRoot(), "app.py")];
  return spawn(pythonPath, args, {
    cwd: packaged ? path.dirname(pythonPath) : repoRoot(),
    env,
    detached: process.platform !== "win32",
    windowsHide: true,
    stdio: ["pipe", "pipe", "pipe"],
  });
}

async function startFlask({ userData, pythonPath, appVersion, token, port }) {
  shuttingDown = false;
  const reusePort = port != null && Number(port) > 0;
  token = token || crypto.randomBytes(32).toString("hex");
  const log = new RotatingLog(path.join(userData, "logs", "flask.log"), token);
  let lastError = "Flask 启动失败";
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const usePort = reusePort ? Number(port) : await pickFreePort();
    const child = spawnFlask({ pythonPath, userData, token, port: usePort, appVersion });
    currentChild = child;
    bindOutput(child, log, (line) => {
      if (typeof child._zintriqOnLine === "function") child._zintriqOnLine(line);
    });
    try {
      const ready = await waitForReady(child, usePort, 30000);
      await waitForHealth(usePort, token, child, 15000);
      const info = { port: usePort, token, pid: ready.pid, logPath: log.filePath };
      if (pythonPath) spawnCollabDaemon({ pythonPath, userData });
      child.once("exit", (code) => {
        lastLaunch.exitCode = code;
        lastLaunch.reason = code ? "flask_exit" : "";
        if (shuttingDown || currentChild !== child) return;
        if (process.env.ZINTRIQ_SMOKE === "1") return;
        log.write(`\n[zintriq] flask exited ${code}, restarting\n`);
        startFlask({ userData, pythonPath, appVersion, token, port: usePort }).catch((err) => {
          log.write(`\n[zintriq] flask restart failed: ${scrub(err && err.message ? err.message : String(err), token)}\n`);
        });
      });
      if (flaskHook) flaskHook(info);
      return info;
    } catch (err) {
      lastError = scrub(err && err.message ? err.message : String(err), token);
      lastLaunch.exitCode = child.exitCode;
      lastLaunch.portInUse = /eaddrinuse|address already in use|port/i.test(lastError);
      lastLaunch.tokenOk = !/token|401|403/i.test(lastError);
      lastLaunch.reason = lastLaunch.portInUse ? "port_in_use" : lastLaunch.tokenOk ? "flask_down" : "token";
      try {
        lastLaunch.logTail = fs.readFileSync(log.filePath, "utf8").slice(-4000);
      } catch {
        lastLaunch.logTail = "";
      }
      log.write(`\n[zintriq] attempt ${attempt} failed: ${lastError}\n`);
      await stopChild(child, 2000);
      if (child.exitCode === null) forceKill(child);
      if (currentChild === child) currentChild = null;
      if (reusePort) break;
    }
  }
  const error = new Error(lastError);
  error.logPath = log.filePath;
  throw error;
}

function stopFlask() {
  shuttingDown = true;
  stopDaemon();
  const child = currentChild;
  currentChild = null;
  return stopChild(child, 3000);
}

function stopFlaskSync() {
  shuttingDown = true;
  stopDaemon();
  const child = currentChild;
  if (!child || child.exitCode !== null) return;
  forceKill(child);
}

module.exports = {
  devUserDataDir,
  smokeUserDataDir,
  resolvePythonExecutable,
  pythonExists,
  startFlask,
  stopFlask,
  stopFlaskSync,
  forceKill,
  scrub,
  onFlaskReady,
  loadLaunchRecipe,
  launchRecipePath,
  mergeLaunchEnv,
  lastFlaskLaunch,
};
