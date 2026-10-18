/**
 * Native zip import/export for software.site.
 * The renderer never sees the file path or the startup token.
 */

const { dialog } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");

const MAX_ZIP = 4 * 1024 * 1024;

function requestBytes(flaskInfo, method, route, body, extraHeaders) {
  return new Promise((resolve, reject) => {
    const payload = body ? Buffer.from(body) : null;
    const headers = {
      Host: `127.0.0.1:${flaskInfo.port}`,
      "X-Zintriq-Desktop-Token": flaskInfo.token,
      ...extraHeaders,
    };
    if (payload) {
      if (!headers["Content-Type"] && !headers["content-type"]) {
        headers["Content-Type"] = "application/octet-stream";
      }
      headers["Content-Length"] = String(payload.length);
    }
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: flaskInfo.port,
        path: route,
        method,
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
    if (payload) req.write(payload);
    req.end();
  });
}

function zipForm(zipBuffer, slug, filename) {
  const boundary = "----zintriqmeta" + crypto.randomBytes(6).toString("hex");
  const name = String(filename || "pack.zip").replace(/["\\\r\n]/g, "") || "pack.zip";
  const head =
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="slug"\r\n\r\n${slug || ""}\r\n` +
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="site"; filename="${name}"\r\n` +
    `Content-Type: application/zip\r\n\r\n`;
  const tail = `\r\n--${boundary}--\r\n`;
  return {
    body: Buffer.concat([Buffer.from(head), zipBuffer, Buffer.from(tail)]),
    contentType: `multipart/form-data; boundary=${boundary}`,
  };
}

function safeZipName(slug) {
  const cleaned = String(slug || "site")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "")
    .trim()
    .slice(0, 64);
  return `${cleaned || "site"}.zip`;
}

async function exportSite({ window, flaskInfo }) {
  if (!flaskInfo || !flaskInfo.port) return { ok: false, error: "本地服务未就绪" };
  const listed = await requestBytes(flaskInfo, "GET", "/api/builder-core/meta/index");
  if (listed.status !== 200 || !listed.body) {
    return { ok: false, error: "无法读取本机产物" };
  }
  const artifacts = listed.body.artifacts || [];
  const current = listed.body.current;
  const match = artifacts.find((item) => item.slug === current) || artifacts[0];
  if (!match || !match.slug) {
    await dialog.showMessageBox(window, {
      type: "info",
      message: "还没有实例化产物可导出",
      detail: "先在 Describe 里 Instantiate，再从 File 导出 zip。",
    });
    return { ok: false, canceled: true };
  }
  const choice = await dialog.showSaveDialog(window, {
    title: "Export site",
    defaultPath: safeZipName(match.slug),
    filters: [{ name: "Zip", extensions: ["zip"] }],
  });
  if (choice.canceled || !choice.filePath) return { ok: false, canceled: true };
  const response = await requestBytes(
    flaskInfo,
    "GET",
    `/api/builder-core/meta/sites/${encodeURIComponent(match.slug)}/zip`
  );
  if (response.status !== 200) {
    const message = (response.body && response.body.error) || "导出失败";
    return { ok: false, error: message };
  }
  const dest = choice.filePath.toLowerCase().endsWith(".zip") ? choice.filePath : `${choice.filePath}.zip`;
  const tmp = `${dest}.${crypto.randomBytes(6).toString("hex")}.part`;
  try {
    fs.writeFileSync(tmp, response.raw);
    fs.renameSync(tmp, dest);
  } catch {
    try {
      fs.unlinkSync(tmp);
    } catch {
      /* ignore */
    }
    return { ok: false, error: "无法写入所选位置" };
  }
  return { ok: true, slug: match.slug, path: dest };
}

function isPackPath(filePath) {
  const lower = String(filePath || "").replace(/\\/g, "/").toLowerCase();
  return (
    lower.endsWith(".zintriq-app.zip") ||
    lower.endsWith(".zintriq-app") ||
    lower.endsWith(".zip") ||
    lower.endsWith(".zintriq-plugin.json") ||
    lower.endsWith(".zintriq.json")
  );
}

function packPathsFromArgv(argv) {
  const rows = Array.isArray(argv) ? argv : [];
  const out = [];
  rows.forEach((item, index) => {
    const arg = String(item || "");
    if (!arg || arg === "." || arg.startsWith("-") || arg.startsWith("zintriq://")) return;
    const base = path.basename(arg).toLowerCase();
    if (index === 0 && (base === "electron" || base.endsWith(".exe") || !base.includes("."))) return;
    if (base === "electron" || base === "main.js" || base === "electron.exe") return;
    if (!isPackPath(arg)) return;
    out.push(path.resolve(arg));
  });
  return out;
}

async function importPackFromPath({ window, flaskInfo, origin, loadStudio, filePath }) {
  if (!flaskInfo || !flaskInfo.port) return { ok: false, error: "本地服务未就绪" };
  const source = String(filePath || "");
  if (!isPackPath(source)) return { ok: false, error: "not a pack" };
  let stat;
  try {
    stat = fs.statSync(source);
  } catch {
    return { ok: false, error: "无法读取所选文件" };
  }
  if (!stat.isFile() || stat.size > MAX_ZIP) {
    return { ok: false, error: "文件过大或不是普通文件" };
  }
  const data = fs.readFileSync(source);
  const pack = zipForm(data, "", path.basename(source));
  const response = await requestBytes(flaskInfo, "POST", "/api/builder-core/meta/sites/import", pack.body, {
    "Content-Type": pack.contentType,
  });
  if (response.status !== 201 && response.status !== 200) {
    const message = (response.body && response.body.error) || "导入失败";
    return { ok: false, error: message };
  }
  const slug = response.body && response.body.slug;
  const studioPath = String((response.body && response.body.studio) || "").trim();
  const dest = studioPath.startsWith("/studio/")
    ? studioPath
    : slug
      ? `/studio/meta/${encodeURIComponent(slug)}`
      : "";
  if (dest && origin && window && !window.isDestroyed()) {
    await window.loadURL(`${origin}${dest}`);
  } else if (typeof loadStudio === "function") {
    loadStudio();
  }
  return { ok: true, slug, studio: dest };
}

async function importSite({ window, flaskInfo, origin, loadStudio }) {
  if (!flaskInfo || !flaskInfo.port) return { ok: false, error: "本地服务未就绪" };
  const choice = await dialog.showOpenDialog(window, {
    title: "Open",
    properties: ["openFile"],
    filters: [
      { name: "Zintriq pack", extensions: ["zip", "zintriq-app", "json"] },
      { name: "All files", extensions: ["*"] },
    ],
  });
  if (choice.canceled || !choice.filePaths || !choice.filePaths[0]) return { ok: false, canceled: true };
  return importPackFromPath({
    window,
    flaskInfo,
    origin,
    loadStudio,
    filePath: choice.filePaths[0],
  });
}

module.exports = {
  exportSite,
  importSite,
  importPackFromPath,
  isPackPath,
  packPathsFromArgv,
  safeZipName,
};
