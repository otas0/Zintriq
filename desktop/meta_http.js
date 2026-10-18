/**
 * Main-process proxy for Workbench HTTP.
 * Renderer sends method + path; this process talks to loopback Flask.
 */

const http = require("http");
const crypto = require("crypto");

const META_PREFIX = "/api/builder-core/meta/";
const MAX_JSON = 512 * 1024;
const MAX_FILE = 256 * 1024;
const MAX_PATH = 256;

function allowedRoute(method, path) {
  const verb = String(method || "").toUpperCase();
  if (verb !== "GET" && verb !== "POST") return false;
  const raw = String(path || "");
  if (raw.length < META_PREFIX.length || raw.length > MAX_PATH) return false;
  if (!raw.startsWith(META_PREFIX)) return false;
  if (raw.includes("..") || raw.includes("//") || raw.includes("\\")) return false;
  if (raw.includes("://") || raw.includes("?") || raw.includes("#") || raw.includes("\0")) return false;
  for (let i = 0; i < raw.length; i += 1) {
    const code = raw.charCodeAt(i);
    if (code < 33 || code > 126) return false;
  }
  return true;
}

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

function safeName(value, fallback) {
  const cleaned = String(value || "")
    .replace(/[^\w.-]/g, "")
    .slice(0, 80);
  return cleaned || fallback;
}

function encodeMultipart(fields, files) {
  const boundary = "----zintriqhttp" + crypto.randomBytes(6).toString("hex");
  const parts = [];
  Object.keys(fields || {}).forEach((key) => {
    const name = safeName(key, "field");
    parts.push(
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${String(fields[key])}\r\n`
      )
    );
  });
  (files || []).forEach((file) => {
    const name = safeName(file.field, "file");
    const filename = safeName(file.filename, "file");
    const type = String(file.type || "application/octet-stream").split(";")[0].slice(0, 80);
    const data = Buffer.from(Array.isArray(file.data) ? file.data : []);
    if (data.length > MAX_FILE) {
      const err = new Error("file too large");
      err.code = "TOO_LARGE";
      throw err;
    }
    parts.push(
      Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${filename}"\r\nContent-Type: ${type}\r\n\r\n`
      )
    );
    parts.push(data);
    parts.push(Buffer.from("\r\n"));
  });
  parts.push(Buffer.from(`--${boundary}--\r\n`));
  return {
    body: Buffer.concat(parts),
    contentType: `multipart/form-data; boundary=${boundary}`,
  };
}

async function studioHttp(flaskInfo, payload, extraHeaders) {
  const method = String((payload && payload.method) || "").toUpperCase();
  const path = String((payload && payload.path) || "");
  if (!flaskInfo || !flaskInfo.port) {
    return { status: 503, body: { error: "本地服务未就绪" }, text: "" };
  }
  if (!allowedRoute(method, path)) {
    return { status: 403, body: { error: "forbidden" }, text: "" };
  }
  const headers = { ...(extraHeaders || {}) };
  let body = null;
  const kind = payload && payload.kind;
  try {
    if (method === "POST" && kind === "form") {
      const pack = encodeMultipart(payload.fields, payload.files);
      body = pack.body;
      headers["Content-Type"] = pack.contentType;
    } else if (method === "POST") {
      const json = payload.json && typeof payload.json === "object" ? payload.json : {};
      const raw = Buffer.from(JSON.stringify(json), "utf8");
      if (raw.length > MAX_JSON) {
        return { status: 413, body: { error: "payload too large" }, text: "" };
      }
      body = raw;
      headers["Content-Type"] = "application/json";
    }
  } catch (err) {
    if (err && err.code === "TOO_LARGE") {
      return { status: 413, body: { error: "payload too large" }, text: "" };
    }
    throw err;
  }
  const csrf =
    (payload && payload.csrf) ||
    (payload && payload.json && payload.json.csrf_token) ||
    (payload && payload.fields && payload.fields.csrf_token) ||
    "";
  if (csrf) headers["X-CSRF-Token"] = String(csrf);
  const response = await requestBytes(flaskInfo, method, path, body, headers);
  const text = response.raw ? response.raw.toString("utf8") : "";
  return { status: response.status, body: response.body, text, raw: response.raw || null };
}

module.exports = {
  META_PREFIX,
  allowedRoute,
  studioHttp,
};
