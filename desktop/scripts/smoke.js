/**
 * Desktop smoke: Electron starts Flask, the factory opens, a second
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

const { probe: probeInstalledAssocs } = require("./assoc-os");

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
const overallMs = Number(process.env.ZINTRIQ_SMOKE_TIMEOUT_MS || 300000);
/** Cold start: Electron spawn → Flask session loaded. Product gate is 3000ms. */
const coldMsLimit = Number(process.env.ZINTRIQ_SMOKE_COLD_MS || 3000);
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

function launch(extraArgs) {
  const env = { ...process.env, ZINTRIQ_SMOKE: "1", ZINTRIQ_SMOKE_USER_DATA: userData };
  if (packagedApp()) env.ZINTRIQ_PACKAGED = "1";
  return spawn(electronPath, electronArgs().concat(extraArgs || []), {
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
      if (data.error || data.loaded === false) {
        throw new Error(`Flask 启动失败: ${data.error || "loaded=false"}\n${data.logPath || ""}\n${readLog()}`);
      }
      if (data.port && data.token && data.flaskPid && data.loaded) return data;
    }
    await sleep(200);
  }
  throw new Error(`等待 smoke session 超时\n${readLog()}`);
}

async function openFactory(port, token) {
  const studio = await request(port, token, "GET", "/studio");
  if (studio.status !== 200) throw new Error(`/studio 返回 ${studio.status}`);
  const html = studio.body.toString("utf8");
  if (!/da-factory/i.test(html)) throw new Error("Studio 首页不是工厂");
  if (/universal-builder\.js/i.test(html)) throw new Error("工厂页仍加载旧编辑器");
  const csrfMatch = html.match(/csrf-token" content="([^"]+)"/);
  const csrf = csrfMatch ? csrfMatch[1] : "";
  const setCookie = studio.headers["set-cookie"];
  const cookie = Array.isArray(setCookie)
    ? setCookie.map((item) => String(item).split(";")[0]).join("; ")
    : setCookie
      ? String(setCookie).split(";")[0]
      : "";
  const auth = { Cookie: cookie, "X-CSRF-Token": csrf };
  const meta = await request(port, token, "GET", "/studio/meta", null, auth);
  if (meta.status !== 200) throw new Error(`/studio/meta 返回 ${meta.status}`);
  if (!/me-code/i.test(meta.body.toString("utf8"))) throw new Error("描述页缺少编辑器");
  if (!/studio\/editor-views\.js/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页缺少视图插件");
  }
  if (!/data-editor-view="code"/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页缺少 Code 视图");
  }
  if (!/id="me-graph"/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页缺少 Graph 视图");
  }
  if (!/id="me-diagram"/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页缺少 Diagram 插件");
  }
  if (!/studio\/editors\/runtimes\.js/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页未加载编辑器运行时");
  }
  const panes = ["scene", "shader", "quantum", "map", "bitmap", "diagram", "text"];
  for (const pane of panes) {
    const view = await request(port, token, "GET", "/studio/meta?pane=" + pane, null, auth);
    if (view.status !== 200) throw new Error("/studio/meta?pane=" + pane + " 返回 " + view.status);
  }
  if (!/id="me-plugin-host"/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页缺少插件宿主");
  }
  if (!/id="me-uir"/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页缺少 UIR 视图");
  }
  if (/universal-builder\.js/i.test(meta.body.toString("utf8"))) {
    throw new Error("描述页仍加载旧编辑器");
  }
  const sim = await request(port, token, "GET", "/studio/simulate", null, auth);
  if (sim.status !== 200) throw new Error(`/studio/simulate 返回 ${sim.status}`);
  if (!/data-meta-view="simulate"/i.test(sim.body.toString("utf8"))) {
    throw new Error("模拟页缺少 workbench 面");
  }
  const inst = await request(port, token, "GET", "/studio/instantiate", null, auth);
  if (!/id="me-hw-flash"/i.test(inst.body.toString("utf8"))) {
    throw new Error("实例化页缺少 ESP32 烧录");
  }
  if (!/data-meta-view="instantiate"/i.test(inst.body.toString("utf8"))) {
    throw new Error("实例化页缺少 workbench 面");
  }
  if (!/id="me-artifact"/i.test(inst.body.toString("utf8"))) {
    throw new Error("实例化页缺少产物面板");
  }
  if (!/id="me-sim-empty"/i.test(sim.body.toString("utf8"))) {
    throw new Error("模拟页缺少空状态");
  }
  const retired = await request(port, token, "GET", "/studio/p/1", null, auth);
  if (![301, 302, 303, 404].includes(retired.status)) {
    throw new Error(`/studio/p/1 仍打开旧编辑器 (${retired.status})`);
  }
  const space = await request(port, token, "GET", "/studio/space", null, auth);
  if (space.status !== 200) throw new Error(`/studio/space 返回 ${space.status}`);
  if (!/data-meta-view="space"/i.test(space.body.toString("utf8"))) {
    throw new Error("空间页缺少 workbench 面");
  }
  if (!/id="me-space-doc"/i.test(space.body.toString("utf8"))) {
    throw new Error("空间页缺少文档面");
  }
  return { csrf, cookie, auth };
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
      if (!headers["Content-Type"] && !headers["content-type"]) {
        headers["Content-Type"] = "application/json";
      }
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
            body: Buffer.concat(chunks),
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

function jsonBody(res) {
  try {
    return JSON.parse(res.body.toString("utf8"));
  } catch {
    throw new Error(`无法解析 JSON (${res.status}): ${res.body.toString("utf8").slice(0, 200)}`);
  }
}

async function postJson(port, token, urlPath, data, auth) {
  const payload = { ...(data || {}) };
  if (auth && auth["X-CSRF-Token"] && payload.csrf_token == null) payload.csrf_token = auth["X-CSRF-Token"];
  return request(port, token, "POST", urlPath, JSON.stringify(payload), auth);
}

const SMOKE_SITE = {
  fields: {
    kind: { form: "atom", type: "string", value: "software.site" },
    pages: {
      form: "sequence",
      items: [
        {
          fields: {
            body: { form: "sequence", items: [{ form: "atom", type: "string", value: "Welcome." }] },
            key: { form: "atom", type: "string", value: "home" },
            title: { form: "atom", type: "string", value: "Home" },
          },
          form: "struct",
        },
        {
          fields: {
            body: {
              form: "sequence",
              items: [{ form: "atom", type: "string", value: "About this system." }],
            },
            key: { form: "atom", type: "string", value: "about" },
            title: { form: "atom", type: "string", value: "About" },
          },
          form: "struct",
        },
      ],
    },
    title: { form: "atom", type: "string", value: "Smoke" },
  },
  form: "struct",
};

function zipImportBody(zipBuffer, csrf, slug) {
  const boundary = "----zintriqsmoke" + Date.now();
  const head =
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="csrf_token"\r\n\r\n${csrf}\r\n` +
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="slug"\r\n\r\n${slug}\r\n` +
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="site"; filename="site.zip"\r\n` +
    `Content-Type: application/zip\r\n\r\n`;
  const tail = `\r\n--${boundary}--\r\n`;
  return {
    body: Buffer.concat([Buffer.from(head), zipBuffer, Buffer.from(tail)]),
    contentType: `multipart/form-data; boundary=${boundary}`,
  };
}

async function roundTripPackage(port, token, auth) {
  const created = await postJson(
    port,
    token,
    "/api/builder-core/meta/instantiate",
    { slug: "smoke-source", description: SMOKE_SITE },
    auth
  );
  if (created.status !== 201) {
    throw new Error(`实例化返回 ${created.status} ${created.body.toString("utf8").slice(0, 200)}`);
  }
  const exported = await request(port, token, "GET", "/api/builder-core/meta/sites/smoke-source/zip", null, auth);
  if (exported.status !== 200) {
    throw new Error(`导出 zip 返回 ${exported.status} ${exported.body.toString("utf8").slice(0, 200)}`);
  }
  if (exported.body.length < 32) throw new Error("导出包过小");
  const removed = await postJson(
    port,
    token,
    "/api/builder-core/meta/sites/smoke-source/remove",
    {},
    auth
  );
  if (removed.status !== 200) {
    throw new Error(`删除站点返回 ${removed.status} ${removed.body.toString("utf8").slice(0, 200)}`);
  }
  const before = jsonBody(await request(port, token, "GET", "/api/builder-core/meta/index", null, auth));
  const beforeCount = (before.artifacts || []).length;
  const pack = zipImportBody(exported.body, auth["X-CSRF-Token"], "smoke-imported");
  const commit = await request(port, token, "POST", "/api/builder-core/meta/sites/import", pack.body, {
    ...auth,
    "Content-Type": pack.contentType,
  });
  if (commit.status !== 201 && commit.status !== 200) {
    throw new Error(`导入返回 ${commit.status} ${commit.body.toString("utf8").slice(0, 200)}`);
  }
  const imported = jsonBody(commit);
  if (imported.slug !== "smoke-imported") throw new Error(`导入 slug 为 ${imported.slug}`);
  const after = jsonBody(await request(port, token, "GET", "/api/builder-core/meta/index", null, auth));
  const afterCount = (after.artifacts || []).length;
  if (afterCount !== beforeCount + 1) {
    throw new Error(`导入后产物数 ${afterCount}，期望 ${beforeCount + 1}`);
  }
  const page = await request(port, token, "GET", "/build/smoke-imported/home", null, auth);
  if (page.status !== 200) throw new Error(`导入后 /build 返回 ${page.status}`);
  const html = page.body.toString("utf8");
  if (!/Welcome/.test(html)) throw new Error("导入后页面缺少正文");
  if (!/data-boundary="software\.(page|site)"/.test(html) && !/data-page-kind="software\.(page|site)"/.test(html)) {
    throw new Error("导入后页面缺少 software 边界");
  }
  assertNoBlocked();
  return { persistName: "Restart Marker", persistSlug: "smoke-imported" };
}

async function renameForPersistence(port, token, auth, slug, name) {
  const res = await postJson(
    port,
    token,
    "/api/builder-core/meta/drafts",
    { slug, code: JSON.stringify({ marker: name, form: "atom", type: "string", value: name }) },
    auth
  );
  if (res.status !== 200) throw new Error(`保存草稿返回 ${res.status}`);
}

async function assertProjectName(port, token, auth, slug, name) {
  const studio = await request(port, token, "GET", "/studio");
  if (studio.status !== 200) throw new Error(`重启后 /studio 返回 ${studio.status}`);
  const html = studio.body.toString("utf8");
  if (!html.includes(slug)) throw new Error(`重启后工厂未列出 ${slug}`);
  const draft = await request(port, token, "GET", `/api/builder-core/meta/drafts/${slug}`, null, auth);
  if (draft.status !== 200) throw new Error(`重启后草稿返回 ${draft.status}`);
  const body = jsonBody(draft);
  if (!String(body.code || "").includes(name)) {
    throw new Error(`重启后草稿不含 ${name}`);
  }
}

async function stopApp(child, flaskPid, mode) {
  if (mode === "kill") {
    process.kill(child.pid, "SIGKILL");
  } else {
    try {
      process.kill(child.pid, "SIGTERM");
    } catch {
      process.kill(child.pid, "SIGKILL");
    }
  }
  try {
    await waitUntilDead(child.pid, 20000);
  } catch {
    killPid(child.pid);
    await waitUntilDead(child.pid, 8000);
  }
  if (flaskPid) {
    try {
      await waitUntilDead(flaskPid, 8000);
    } catch {
      killPid(flaskPid);
      await waitUntilDead(flaskPid, 8000);
    }
  }
}

async function relaunch() {
  fs.rmSync(sessionFile, { force: true });
  const child = launch();
  const readLog = collect(child);
  const session = await waitForSession(child, readLog);
  return { child, readLog, session };
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

function assertAssocManifest() {
  const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, "package.json"), "utf8"));
  const assocs = ((pkg.build || {}).fileAssociations || []).filter((row) => row && row.rank === "Alternate");
  const exts = assocs.map((row) => row.ext);
  if (!exts.includes("zintriq-plugin.json") || !exts.includes("zip")) {
    throw new Error("fileAssociations must mark zintriq-plugin.json and zip Alternate");
  }
  const install = process.env.ZINTRIQ_SMOKE_INSTALL_DIR || "";
  if (process.platform === "darwin" && install) {
    const plist = fs.readFileSync(path.join(install, "Contents/Info.plist"), "utf8");
    if (!plist.includes("zintriq-plugin.json")) throw new Error("mac Info.plist missing zintriq-plugin.json");
    if (!plist.includes("Alternate") && !plist.includes("LSHandlerRank")) throw new Error("mac Info.plist missing Alternate rank");
  }
  if (process.platform === "linux" && install) {
    const desktopFiles = [];
    function walk(dir, depth) {
      if (depth > 4 || !fs.existsSync(dir)) return;
      for (const name of fs.readdirSync(dir)) {
        const full = path.join(dir, name);
        let stat;
        try {
          stat = fs.statSync(full);
        } catch {
          continue;
        }
        if (stat.isDirectory()) walk(full, depth + 1);
        else if (name.endsWith(".desktop")) desktopFiles.push(full);
      }
    }
    walk(install, 0);
    const text = desktopFiles.map((file) => fs.readFileSync(file, "utf8")).join("\n");
    if (text && !/json|zip/i.test(text)) throw new Error("linux .desktop missing json/zip mime");
  }
  probeInstalledAssocs();
}

async function assertModesScrollLayout(port, token, auth) {
  const pane = "scene";
  const scroll = 240;
  const res = await postJson(
    port,
    token,
    "/api/builder-core/meta/layout",
    { modesScroll: scroll, pane: pane, version: 8 },
    auth
  );
  if (res.status !== 200) {
    throw new Error(`layout save ${res.status}: ${res.body.toString("utf8").slice(0, 200)}`);
  }
  const body = jsonBody(res);
  if (Number(body.modesScroll) !== scroll) {
    throw new Error(`modesScroll roundtrip ${body.modesScroll} on ${process.platform}`);
  }
  if (String(body.pane || "") !== pane) {
    throw new Error(`pane roundtrip ${body.pane} on ${process.platform}`);
  }
  const layoutPath = path.join(userData, "workbench-layout.json");
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline && !fs.existsSync(layoutPath)) {
    await sleep(50);
  }
  if (!fs.existsSync(layoutPath)) {
    throw new Error(`workbench-layout.json missing on ${process.platform}`);
  }
  const disk = JSON.parse(fs.readFileSync(layoutPath, "utf8"));
  if (Number(disk.modesScroll) !== scroll) {
    throw new Error(`disk modesScroll ${disk.modesScroll} on ${process.platform}`);
  }
  if (String(disk.pane || "") !== pane) {
    throw new Error(`disk pane ${disk.pane} on ${process.platform}`);
  }
  console.log(`modesScroll layout ok platform=${process.platform} scroll=${scroll} pane=${pane}`);
}

async function assertAssocOpen() {
  assertAssocManifest();
  if (!packagedApp()) return;
  const fixture = path.join(userData, "assoc-open.zintriq-plugin.json");
  fs.writeFileSync(
    fixture,
    JSON.stringify({
      id: "assoc-open-pack",
      name: "Assoc open",
      form: "view",
      document: { form: "struct", fields: { kind: { form: "atom", type: "string", value: "scene", has_value: true } } },
    })
  );
  const child = launch([fixture]);
  const code = await waitForExit(child, 20000);
  if (code !== 0) throw new Error(`assoc second instance exit ${code}`);
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const folder = path.join(userData, "plugins");
    if (fs.existsSync(folder)) {
      const names = fs.readdirSync(folder).join(" ");
      if (/assoc-open|assoc_open|Assoc/i.test(names) || names.includes(".json")) return;
    }
    const last = path.join(userData, "last-open.json");
    if (fs.existsSync(last) && fs.readFileSync(last, "utf8").includes("assoc")) return;
    await sleep(250);
  }
  throw new Error("assoc open did not import .zintriq-plugin.json");
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
  const coldStartedAt = Date.now();
  let current = launch();
  const readFirst = collect(current);
  let flaskPid = 0;
  const overallTimer = setTimeout(() => {
    console.error(`smoke 超过 ${overallMs}ms`);
    killPid(current && current.pid);
    killPid(flaskPid);
    preserveLogsAndRemoveUserData();
    process.exit(1);
  }, overallMs);
  if (typeof overallTimer.unref === "function") overallTimer.unref();
  try {
    let session = await waitForSession(current, readFirst);
    const coldMs = Date.now() - coldStartedAt;
    console.log(`cold start ${coldMs}ms (limit ${coldMsLimit}ms)`);
    if (coldMs > coldMsLimit) {
      throw new Error(`cold start ${coldMs}ms exceeds ${coldMsLimit}ms`);
    }
    flaskPid = Number(session.flaskPid);
    if (readFirst().includes(session.token)) throw new Error("Electron 输出含有令牌");
    await sleep(1500);
    assertNoBlocked();
    const opened = await openFactory(session.port, session.token);
    await assertModesScrollLayout(session.port, session.token, opened.auth);
    await assertAssocOpen();
    assertLogsHideToken(session.token, session.logPath);
    assertWritableOnlyUserData();
    const persist = await roundTripPackage(session.port, session.token, opened.auth);
    await renameForPersistence(session.port, session.token, opened.auth, persist.persistSlug, persist.persistName);

    const second = launch();
    const readSecond = collect(second);
    const code = await waitForExit(second, 20000);
    if (code !== 0) throw new Error(`第二个实例退出码 ${code}\n${readSecond()}`);
    if (current.exitCode !== null) throw new Error("第一个实例被第二个实例带走了");
    await openFactory(session.port, session.token);

    await stopApp(current, flaskPid, "term");
    const again = await relaunch();
    current = again.child;
    session = again.session;
    flaskPid = Number(session.flaskPid);
    const afterTerm = await openFactory(session.port, session.token);
    await assertProjectName(session.port, session.token, afterTerm.auth, persist.persistSlug, persist.persistName);

    await stopApp(current, flaskPid, "kill");
    const third = await relaunch();
    current = third.child;
    session = third.session;
    flaskPid = Number(session.flaskPid);
    const afterKill = await openFactory(session.port, session.token);
    await assertProjectName(session.port, session.token, afterKill.auth, persist.persistSlug, persist.persistName);

    await stopApp(current, flaskPid, "kill");
    console.log("smoke ok");
  } catch (err) {
    console.error(err && err.message ? err.message : err);
    killPid(current && current.pid);
    killPid(flaskPid);
    process.exitCode = 1;
  } finally {
    clearTimeout(overallTimer);
    preserveLogsAndRemoveUserData();
  }
}

main();
