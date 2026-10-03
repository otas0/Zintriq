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
const overallMs = Number(process.env.ZINTRIQ_SMOKE_TIMEOUT_MS || 300000);
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
  const html = studio.body.toString("utf8");
  const csrfMatch = html.match(/csrf-token" content="([^"]+)"/);
  const csrf = csrfMatch ? csrfMatch[1] : "";
  const setCookie = studio.headers["set-cookie"];
  const cookie = Array.isArray(setCookie)
    ? setCookie.map((item) => String(item).split(";")[0]).join("; ")
    : setCookie
      ? String(setCookie).split(";")[0]
      : "";
  const auth = { Cookie: cookie, "X-CSRF-Token": csrf };
  const list = await request(port, token, "GET", "/api/builder-core/projects", null, auth);
  if (list.status !== 200) throw new Error(`/api/builder-core/projects 返回 ${list.status}`);
  let projects = [];
  try {
    projects = JSON.parse(list.body.toString("utf8")).projects || [];
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
      auth
    );
    if (created.status !== 201 && created.status !== 200) {
      throw new Error(`创建项目返回 ${created.status}`);
    }
    const payload = JSON.parse(created.body.toString("utf8"));
    projectId = payload.id || (payload.project && payload.project.id);
  }
  const editor = await request(port, token, "GET", `/studio/p/${projectId}`, null, auth);
  if (editor.status !== 200) throw new Error(`/studio/p/${projectId} 返回 ${editor.status}`);
  if (!/universal-builder\.js/i.test(editor.body.toString("utf8"))) {
    throw new Error("编辑器页面未包含 Builder 脚本");
  }
  return { csrf, cookie, auth, projectId };
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

async function patchJson(port, token, urlPath, data, auth) {
  const payload = { ...(data || {}) };
  if (auth && auth["X-CSRF-Token"] && payload.csrf_token == null) payload.csrf_token = auth["X-CSRF-Token"];
  return request(port, token, "PATCH", urlPath, JSON.stringify(payload), auth);
}

function countProject(detail) {
  const documents = detail.documents || [];
  const pages = documents.filter((item) => item.type !== "workflow");
  const workflows = documents.filter((item) => item.type === "workflow");
  const models = detail.data_models || [];
  const components = detail.component_definitions || [];
  return {
    pages: pages.length,
    workflows: workflows.length,
    disabledWorkflows: workflows.filter((item) => item.status === "disabled").length,
    models: Array.isArray(models) ? models.length : 0,
    components: Array.isArray(components) ? components.length : 0,
  };
}

async function projectDetail(port, token, projectId, auth) {
  const res = await request(port, token, "GET", `/api/builder-core/projects/${projectId}/bootstrap`, null, auth);
  if (res.status !== 200) throw new Error(`bootstrap 返回 ${res.status}`);
  return jsonBody(res);
}

async function seedTransferProject(port, token, auth) {
  const created = await postJson(port, token, "/api/builder-core/projects", { name: "Transfer Source" }, auth);
  if (created.status !== 201 && created.status !== 200) {
    throw new Error(`创建导出项目返回 ${created.status} ${created.body.toString("utf8").slice(0, 200)}`);
  }
  const project = jsonBody(created);
  const projectId = project.id || (project.project && project.project.id);
  const page = await postJson(
    port,
    token,
    `/api/builder-core/projects/${projectId}/documents`,
    { name: "Home Page", key: "home-page", type: "page", route: "/home-page" },
    auth
  );
  if (page.status !== 201) throw new Error(`创建页面返回 ${page.status} ${page.body.toString("utf8").slice(0, 200)}`);
  const pageId = jsonBody(page).id;
  const node = await postJson(
    port,
    token,
    `/api/builder-core/projects/${projectId}/nodes`,
    { document_id: pageId, component_type: "text", key: "smoke-text", props: { body: "hello" } },
    auth
  );
  if (node.status !== 201) throw new Error(`创建节点返回 ${node.status} ${node.body.toString("utf8").slice(0, 200)}`);
  const nodeKey = jsonBody(node).key;
  const component = await postJson(
    port,
    token,
    `/api/builder-core/projects/${projectId}/components/from-node`,
    { document_id: pageId, node_key: nodeKey, name: "Smoke Component" },
    auth
  );
  if (component.status !== 201) {
    throw new Error(`创建组件返回 ${component.status} ${component.body.toString("utf8").slice(0, 200)}`);
  }
  const model = await postJson(
    port,
    token,
    `/api/builder-core/projects/${projectId}/data-models`,
    { name: "Items", key: "items", schema: { type: "object", properties: { title: { type: "string" } } } },
    auth
  );
  if (model.status !== 201) throw new Error(`创建集合返回 ${model.status} ${model.body.toString("utf8").slice(0, 200)}`);
  const workflow = await postJson(
    port,
    token,
    `/api/builder-core/projects/${projectId}/documents`,
    { name: "On Submit", key: "on-submit", type: "workflow", route: "/on-submit" },
    auth
  );
  if (workflow.status !== 201) {
    throw new Error(`创建工作流返回 ${workflow.status} ${workflow.body.toString("utf8").slice(0, 200)}`);
  }
  const detail = await projectDetail(port, token, projectId, auth);
  return { projectId, counts: countProject(detail), name: detail.name };
}

async function roundTripPackage(port, token, auth) {
  const source = await seedTransferProject(port, token, auth);
  const exported = await request(
    port,
    token,
    "POST",
    `/api/builder-core/transfer/export/${source.projectId}`,
    JSON.stringify({ csrf_token: auth["X-CSRF-Token"] }),
    auth
  );
  if (exported.status !== 200) {
    throw new Error(`导出返回 ${exported.status} ${exported.body.toString("utf8").slice(0, 200)}`);
  }
  if (exported.body.length < 32) throw new Error("导出包过小");
  const zipHeaders = { ...auth, "Content-Type": "application/zip" };
  const preview = await request(port, token, "POST", "/api/builder-core/transfer/preview", exported.body, zipHeaders);
  if (preview.status !== 200) {
    throw new Error(`预览返回 ${preview.status} ${preview.body.toString("utf8").slice(0, 200)}`);
  }
  const before = jsonBody(await request(port, token, "GET", "/api/builder-core/projects", null, auth));
  const beforeCount = (before.projects || []).length;
  const commit = await request(port, token, "POST", "/api/builder-core/transfer/commit", exported.body, zipHeaders);
  if (commit.status !== 200 && commit.status !== 201) {
    throw new Error(`导入返回 ${commit.status} ${commit.body.toString("utf8").slice(0, 200)}`);
  }
  const imported = jsonBody(commit);
  const importedId = imported.id || imported.project_id || (imported.project && imported.project.id);
  if (!importedId) throw new Error("导入未返回项目 id");
  const after = jsonBody(await request(port, token, "GET", "/api/builder-core/projects", null, auth));
  const afterCount = (after.projects || []).length;
  if (afterCount !== beforeCount + 1) {
    throw new Error(`导入后项目数 ${afterCount}，期望 ${beforeCount + 1}`);
  }
  const detail = await projectDetail(port, token, importedId, auth);
  const counts = countProject(detail);
  if (counts.pages !== source.counts.pages) {
    throw new Error(`导入页面数 ${counts.pages}，期望 ${source.counts.pages}`);
  }
  if (counts.models !== source.counts.models) {
    throw new Error(`导入集合数 ${counts.models}，期望 ${source.counts.models}`);
  }
  if (counts.components !== source.counts.components) {
    throw new Error(`导入组件数 ${counts.components}，期望 ${source.counts.components}`);
  }
  if (counts.workflows !== source.counts.workflows) {
    throw new Error(`导入工作流数 ${counts.workflows}，期望 ${source.counts.workflows}`);
  }
  if (counts.workflows && counts.disabledWorkflows !== counts.workflows) {
    throw new Error("导入后工作流必须全部停用");
  }
  assertNoBlocked();
  return { persistName: "Restart Marker", persistId: importedId };
}

async function renameForPersistence(port, token, auth, projectId, name) {
  const res = await patchJson(port, token, `/api/builder-core/projects/${projectId}`, { name }, auth);
  if (res.status !== 200) throw new Error(`重命名返回 ${res.status}`);
}

async function assertProjectName(port, token, auth, projectId, name) {
  const studio = await request(port, token, "GET", "/studio");
  if (studio.status !== 200) throw new Error(`重启后 /studio 返回 ${studio.status}`);
  const detail = await projectDetail(port, token, projectId, auth);
  if (detail.name !== name) throw new Error(`重启后项目名为 ${detail.name}，期望 ${name}`);
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
    flaskPid = Number(session.flaskPid);
    if (readFirst().includes(session.token)) throw new Error("Electron 输出含有令牌");
    await sleep(1500);
    assertNoBlocked();
    const opened = await openBuilderPages(session.port, session.token);
    assertLogsHideToken(session.token, session.logPath);
    assertWritableOnlyUserData();
    const persist = await roundTripPackage(session.port, session.token, opened.auth);
    await renameForPersistence(session.port, session.token, opened.auth, persist.persistId, persist.persistName);

    const second = launch();
    const readSecond = collect(second);
    const code = await waitForExit(second, 20000);
    if (code !== 0) throw new Error(`第二个实例退出码 ${code}\n${readSecond()}`);
    if (current.exitCode !== null) throw new Error("第一个实例被第二个实例带走了");
    await openBuilderPages(session.port, session.token);

    await stopApp(current, flaskPid, "term");
    const again = await relaunch();
    current = again.child;
    session = again.session;
    flaskPid = Number(session.flaskPid);
    const afterTerm = await openBuilderPages(session.port, session.token);
    await assertProjectName(session.port, session.token, afterTerm.auth, persist.persistId, persist.persistName);

    await stopApp(current, flaskPid, "kill");
    const third = await relaunch();
    current = third.child;
    session = third.session;
    flaskPid = Number(session.flaskPid);
    const afterKill = await openBuilderPages(session.port, session.token);
    await assertProjectName(session.port, session.token, afterKill.auth, persist.persistId, persist.persistName);

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
