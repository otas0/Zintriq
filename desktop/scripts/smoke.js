/**
 * Desktop smoke: Electron starts Flask, Builder pages return 200, a second
 * instance exits, and killing Electron lets Flask exit on its own.
 */

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

if (process.platform === "linux" && process.env.ZINTRIQ_SMOKE_XVFB !== "1" && !process.env.ZINTRIQ_SMOKE_APP) {
  const result = spawnSync("xvfb-run", ["-a", process.execPath, __filename], {
    stdio: "inherit",
    env: { ...process.env, ZINTRIQ_SMOKE_XVFB: "1" },
  });
  process.exit(result.status == null ? 1 : result.status);
}

const { smokeUserDataDir } = require("../flask_host");

function packagedApp() {
  return process.env.ZINTRIQ_SMOKE_APP || "";
}

function electronArgs() {
  const args = [];
  if (process.env.CI === "true" && process.platform === "linux") args.push("--no-sandbox");
  if (!packagedApp()) args.push(".");
  return args;
}

function assertSandbox() {
  const disabled = electronArgs().includes("--no-sandbox");
  const ciLinux = process.env.CI === "true" && process.platform === "linux";
  if (!ciLinux && disabled) {
    console.error("非 CI 环境必须保持沙箱开启");
    process.exit(1);
  }
  if (!packagedApp() && disabled !== ciLinux) {
    console.error("只有 CI 的 Linux 可以关闭沙箱");
    process.exit(1);
  }
  if (packagedApp() && disabled && !(process.env.CI === "true" && process.platform === "linux")) {
    console.error("正式包不得默认关闭沙箱");
    process.exit(1);
  }
}

assertSandbox();

const electronPath = packagedApp() || require("electron");
const desktopDir = path.join(__dirname, "..");

function resolveUserData() {
  if (process.env.ZINTRIQ_SMOKE_USER_DATA) {
    fs.mkdirSync(process.env.ZINTRIQ_SMOKE_USER_DATA, { recursive: true });
    return process.env.ZINTRIQ_SMOKE_USER_DATA;
  }
  if (process.env.CI === "true") {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "zintriq-smoke-"));
    process.env.ZINTRIQ_SMOKE_USER_DATA = dir;
    return dir;
  }
  return smokeUserDataDir();
}

const userData = resolveUserData();
const sessionFile = path.join(userData, "smoke-session.json");
const blockedFile = path.join(userData, "logs", "smoke-blocked.txt");
const overallMs = Number(process.env.ZINTRIQ_SMOKE_TIMEOUT_MS || 180000);
const SECRET_NAMES = new Set(["smoke-session.json", "secret_key", "zintriq.db", "zintriq.db-wal", "zintriq.db-shm"]);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function launch() {
  const env = { ...process.env, ZINTRIQ_SMOKE: "1", ZINTRIQ_SMOKE_USER_DATA: userData };
  if (packagedApp()) env.ZINTRIQ_PACKAGED = "1";
  return spawn(electronPath, electronArgs(), {
    cwd: desktopDir,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function collect(child) {
  let text = "";
  child.stdout.on("data", (chunk) => {
    text += chunk.toString("utf8");
  });
  child.stderr.on("data", (chunk) => {
    text += chunk.toString("utf8");
  });
  return () => text;
}

async function waitForSession(child, readLog) {
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Electron 提前退出 (${child.exitCode})\n${readLog()}`);
    }
    if (fs.existsSync(sessionFile)) {
      const data = JSON.parse(fs.readFileSync(sessionFile, "utf8"));
      if (data.port && data.token && data.flaskPid && data.loaded) return data;
    }
    await sleep(200);
  }
  throw new Error(`等待 smoke session 超时\n${readLog()}`);
}

async function openBuilderPages(port, token) {
  const studio = await request(port, token, "GET", "/studio");
  if (studio.status !== 200) throw new Error(`/studio 返回 ${studio.status}`);
  const csrfMatch = studio.body.match(/csrf-token" content="([^"]+)"/);
  const csrf = csrfMatch ? csrfMatch[1] : "";
  const setCookie = studio.headers["set-cookie"];
  const cookie = Array.isArray(setCookie)
    ? setCookie.map((item) => String(item).split(";")[0]).join("; ")
    : setCookie
      ? String(setCookie).split(";")[0]
      : "";
  const list = await request(port, token, "GET", "/api/builder-core/projects", null, { Cookie: cookie, "X-CSRF-Token": csrf });
  if (list.status !== 200) throw new Error(`/api/builder-core/projects 返回 ${list.status}`);
  let projects = [];
  try {
    projects = JSON.parse(list.body).projects || [];
  } catch {
    throw new Error("projects JSON 无法解析");
  }
  let projectId = projects[0] && projects[0].id;
  if (!projectId) {
    const created = await request(
      port,
      token,
      "POST",
      "/api/builder-core/projects",
      JSON.stringify({ name: "Smoke Project", csrf_token: csrf }),
      { Cookie: cookie, "X-CSRF-Token": csrf }
    );
    if (created.status !== 201 && created.status !== 200) {
      throw new Error(`创建项目返回 ${created.status}`);
    }
    const payload = JSON.parse(created.body);
    projectId = payload.id || (payload.project && payload.project.id);
  }
  const editor = await request(port, token, "GET", `/studio/p/${projectId}`, null, { Cookie: cookie });
  if (editor.status !== 200) throw new Error(`/studio/p/${projectId} 返回 ${editor.status}`);
  if (!/universal-builder\.js/i.test(editor.body)) {
    throw new Error("编辑器页面未包含 Builder 脚本");
  }
}

function request(port, token, method, urlPath, body, extraHeaders) {
  return new Promise((resolve, reject) => {
    const payload = body ? Buffer.from(body) : null;
    const headers = {
      Host: `127.0.0.1:${port}`,
      "X-Zintriq-Desktop-Token": token,
      ...(extraHeaders || {}),
    };
    if (payload) {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = String(payload.length);
    }
    const req = http.request(
      { host: "127.0.0.1", port, path: urlPath, method, headers },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body: Buffer.concat(chunks).toString("utf8"),
          });
        });
      }
    );
    req.on("error", reject);
    if (payload) req.write(payload);
    req.end();
  });
}

function assertLogsHideToken(token, logPath) {
  const dir = path.dirname(logPath);
  const names = fs.existsSync(dir) ? fs.readdirSync(dir) : [];
  for (const name of names) {
    if (!name.startsWith("flask.log")) continue;
    const text = fs.readFileSync(path.join(dir, name), "utf8");
    if (text.includes(token)) throw new Error(`日志含有令牌: ${name}`);
  }
}

function assertNoBlocked() {
  if (!fs.existsSync(blockedFile)) return;
  const text = fs.readFileSync(blockedFile, "utf8").trim();
  if (text) throw new Error(`拦截了非本机请求:\n${text}`);
}

async function waitForExit(child, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) return child.exitCode;
    await sleep(100);
  }
  throw new Error("第二个实例没有退出");
}

async function waitUntilDead(pid, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!pidAlive(pid)) return;
    await sleep(200);
  }
  throw new Error(`Flask ${pid} 在 ${timeoutMs}ms 内没有退出`);
}

let cleaned = false;

function preserveLogsAndRemoveUserData() {
  if (cleaned) return;
  cleaned = true;
  const logDir = process.env.ZINTRIQ_SMOKE_LOG_DIR;
  const source = path.join(userData, "logs");
  if (logDir && fs.existsSync(source)) {
    fs.mkdirSync(logDir, { recursive: true });
    for (const name of fs.readdirSync(source)) {
      if (SECRET_NAMES.has(name)) continue;
      const from = path.join(source, name);
      if (!fs.statSync(from).isFile()) continue;
      fs.copyFileSync(from, path.join(logDir, name));
    }
  }
  if (process.env.ZINTRIQ_SMOKE_USER_DATA || process.env.CI === "true") {
    fs.rmSync(userData, { recursive: true, force: true });
  }
}

function killPid(pid) {
  if (!pid || !pidAlive(pid)) return;
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    /* already gone */
  }
}

function assertWritableOnlyUserData() {
  const marker = path.join(userData, "smoke-write-check.txt");
  fs.writeFileSync(marker, "ok", { encoding: "utf8" });
  const install = process.env.ZINTRIQ_SMOKE_INSTALL_DIR;
  if (!install) return;
  try {
    fs.writeFileSync(path.join(install, "should-not-write.txt"), "no");
    throw new Error("安装目录可写，只读 smoke 无效");
  } catch (err) {
    if (err && err.message === "安装目录可写，只读 smoke 无效") throw err;
  }
}

async function main() {
  fs.rmSync(sessionFile, { force: true });
  fs.rmSync(blockedFile, { force: true });
  const first = launch();
  const readFirst = collect(first);
  let flaskPid = 0;
  const overallTimer = setTimeout(() => {
    console.error(`smoke 超过 ${overallMs}ms`);
    killPid(first.pid);
    killPid(flaskPid);
    preserveLogsAndRemoveUserData();
    process.exit(1);
  }, overallMs);
  if (typeof overallTimer.unref === "function") overallTimer.unref();
  try {
    const session = await waitForSession(first, readFirst);
    flaskPid = Number(session.flaskPid);
    if (readFirst().includes(session.token)) throw new Error("Electron 输出含有令牌");
    await sleep(1500);
    assertNoBlocked();
    await openBuilderPages(session.port, session.token);
    assertLogsHideToken(session.token, session.logPath);
    assertWritableOnlyUserData();

    const second = launch();
    const readSecond = collect(second);
    const code = await waitForExit(second, 20000);
    if (code !== 0) throw new Error(`第二个实例退出码 ${code}\n${readSecond()}`);
    if (first.exitCode !== null) throw new Error("第一个实例被第二个实例带走了");
    await openBuilderPages(session.port, session.token);

    fs.rmSync(sessionFile, { force: true });
    process.kill(first.pid, "SIGKILL");
    await waitUntilDead(flaskPid, 8000);
    if (pidAlive(flaskPid)) throw new Error("Flask 仍在运行");
    console.log("smoke ok");
  } catch (err) {
    console.error(err && err.message ? err.message : err);
    killPid(first.pid);
    killPid(flaskPid);
    process.exitCode = 1;
  } finally {
    clearTimeout(overallTimer);
    preserveLogsAndRemoveUserData();
  }
}

main();
