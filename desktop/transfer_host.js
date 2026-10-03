/**
 * Desktop project package transfer. The renderer never sees the file path
 * or the startup token. Bytes stay in the main process.
 */

const { dialog } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");

const MAX_PACKAGE = 32 * 1024 * 1024;

function senderAllowed(event, flaskInfo) {
  if (!flaskInfo || !flaskInfo.port) return false;
  const frame = event.senderFrame;
  const url = frame && frame.url ? String(frame.url) : "";
  return url.startsWith(`http://127.0.0.1:${flaskInfo.port}/`);
}

function stagingRoot(userData) {
  return path.join(userData, "incoming-packages");
}

function cleanStaging(userData, stagingId) {
  if (!stagingId || !/^[a-f0-9]{16}$/.test(stagingId)) return;
  fs.rmSync(path.join(stagingRoot(userData), stagingId), { recursive: true, force: true });
}

function cleanAllStaging(userData) {
  fs.rmSync(stagingRoot(userData), { recursive: true, force: true });
}

function postBytes(flaskInfo, route, body, extraHeaders) {
  return new Promise((resolve, reject) => {
    const headers = {
      Host: `127.0.0.1:${flaskInfo.port}`,
      "X-Zintriq-Desktop-Token": flaskInfo.token,
      "Content-Type": "application/octet-stream",
      "Content-Length": String(body.length),
      ...extraHeaders,
    };
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: flaskInfo.port,
        path: route,
        method: "POST",
        headers,
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const raw = Buffer.concat(chunks);
          let parsed = null;
          try {
            parsed = JSON.parse(raw.toString("utf8"));
          } catch {
            parsed = null;
          }
          resolve({ status: res.statusCode, body: parsed, raw });
        });
      }
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function emitProgress(window, stage, detail) {
  if (!window || window.isDestroyed()) return;
  window.webContents.send("studio:transfer-progress", { stage, detail: detail || "" });
}

function defaultExportName(name) {
  const cleaned = String(name || "project")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "")
    .trim()
    .slice(0, 80);
  return `${cleaned || "project"}.zintriq`;
}

async function exportProject({ event, window, flaskInfo, projectId, suggestedName }) {
  if (!senderAllowed(event, flaskInfo)) return { ok: false, error: "来源不受信任" };
  const id = Number(projectId);
  if (!Number.isInteger(id) || id < 1) return { ok: false, error: "项目无效" };
  const choice = await dialog.showSaveDialog(window, {
    title: "导出作品",
    defaultPath: defaultExportName(suggestedName),
    filters: [{ name: "Zintriq", extensions: ["zintriq"] }],
  });
  if (choice.canceled || !choice.filePath) return { ok: false, canceled: true };
  emitProgress(window, "读取", "正在读取作品");
  const response = await postBytes(flaskInfo, `/api/builder-core/transfer/export/${id}`, Buffer.alloc(0));
  if (response.status !== 200) {
    const message = (response.body && response.body.error) || "导出失败";
    return { ok: false, error: message };
  }
  emitProgress(window, "写入", "正在保存文件");
  const dest = choice.filePath.endsWith(".zintriq") ? choice.filePath : `${choice.filePath}.zintriq`;
  const tmp = `${dest}.${crypto.randomBytes(6).toString("hex")}.part`;
  try {
    fs.writeFileSync(tmp, response.raw);
    fs.renameSync(tmp, dest);
  } catch (err) {
    try {
      fs.unlinkSync(tmp);
    } catch {
      /* ignore */
    }
    return { ok: false, error: "无法写入所选位置" };
  }
  emitProgress(window, "完成", "导出完成");
  return { ok: true };
}

async function previewImport({ event, window, flaskInfo, userData }) {
  if (!senderAllowed(event, flaskInfo)) return { ok: false, error: "来源不受信任" };
  const choice = await dialog.showOpenDialog(window, {
    title: "导入作品",
    properties: ["openFile"],
    filters: [{ name: "Zintriq", extensions: ["zintriq"] }],
  });
  if (choice.canceled || !choice.filePaths || !choice.filePaths[0]) return { ok: false, canceled: true };
  const source = choice.filePaths[0];
  let stat;
  try {
    stat = fs.statSync(source);
  } catch {
    return { ok: false, error: "无法读取所选文件" };
  }
  if (!stat.isFile() || stat.size > MAX_PACKAGE) {
    return { ok: false, error: "文件过大或不是普通文件" };
  }
  emitProgress(window, "读取", "正在读取作品包");
  const data = fs.readFileSync(source);
  const sha256 = crypto.createHash("sha256").update(data).digest("hex");
  const stagingId = crypto.randomBytes(8).toString("hex");
  const dir = path.join(stagingRoot(userData), stagingId);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const staged = path.join(dir, "package.zintriq");
  const tmp = `${staged}.part`;
  try {
    fs.writeFileSync(tmp, data, { mode: 0o600 });
    fs.renameSync(tmp, staged);
    fs.writeFileSync(path.join(dir, "sha256"), sha256, { mode: 0o600 });
  } catch {
    cleanStaging(userData, stagingId);
    return { ok: false, error: "无法暂存作品包" };
  }
  emitProgress(window, "校验", "正在校验作品包");
  try {
    const response = await postBytes(flaskInfo, "/api/builder-core/transfer/preview", data, {
      "X-Zintriq-Package-Sha256": sha256,
    });
    if (response.status !== 200) {
      cleanStaging(userData, stagingId);
      const message = (response.body && response.body.error) || "作品包未通过校验";
      return { ok: false, error: message };
    }
    emitProgress(window, "预览", "等待确认");
    return { ok: true, stagingId, preview: response.body };
  } catch (err) {
    cleanStaging(userData, stagingId);
    return { ok: false, error: "无法预览作品包" };
  }
}

async function commitImport({ event, window, flaskInfo, userData, stagingId, enableKeys }) {
  if (!senderAllowed(event, flaskInfo)) return { ok: false, error: "来源不受信任" };
  if (!stagingId || !/^[a-f0-9]{16}$/.test(stagingId)) return { ok: false, error: "暂存已失效" };
  const dir = path.join(stagingRoot(userData), stagingId);
  const staged = path.join(dir, "package.zintriq");
  const hashFile = path.join(dir, "sha256");
  try {
    const data = fs.readFileSync(staged);
    const expected = fs.readFileSync(hashFile, "utf8").trim();
    const actual = crypto.createHash("sha256").update(data).digest("hex");
    if (actual !== expected) {
      cleanStaging(userData, stagingId);
      return { ok: false, error: "作品包内容与校验值不一致" };
    }
    emitProgress(window, "写入", "正在写入作品");
    const enabled = Array.isArray(enableKeys) ? enableKeys.filter((item) => typeof item === "string") : [];
    const response = await postBytes(flaskInfo, "/api/builder-core/transfer/commit", data, {
      "X-Zintriq-Package-Sha256": expected,
      "X-Zintriq-Enable": enabled.join(","),
    });
    cleanStaging(userData, stagingId);
    if (response.status !== 200) {
      const message = (response.body && response.body.error) || "导入失败，已回滚";
      return { ok: false, error: message };
    }
    emitProgress(window, "完成", "导入完成");
    return { ok: true, project: response.body };
  } catch (err) {
    cleanStaging(userData, stagingId);
    return { ok: false, error: "导入失败，已回滚" };
  }
}

async function cancelImport({ event, flaskInfo, userData, stagingId }) {
  if (!senderAllowed(event, flaskInfo)) return { ok: false, error: "来源不受信任" };
  cleanStaging(userData, stagingId);
  return { ok: true };
}

module.exports = {
  senderAllowed,
  exportProject,
  previewImport,
  commitImport,
  cancelImport,
  cleanAllStaging,
};
