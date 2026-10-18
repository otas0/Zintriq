/**
 * Local website origin for desktop login (loopback only).
 * The Electron child process 404s /desktop/authorize — login uses the
 * normal `python app.py` on 127.0.0.1, never a public tunnel.
 */

const fs = require("fs");
const path = require("path");

const LOCAL_ACCOUNT_ORIGIN = "http://127.0.0.1:5001";

function parseDotEnv(text) {
  const out = {};
  String(text || "")
    .split(/\r?\n/)
    .forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) return;
      const eq = trimmed.indexOf("=");
      if (eq < 1) return;
      const key = trimmed.slice(0, eq).trim();
      let value = trimmed.slice(eq + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      out[key] = value;
    });
  return out;
}

function readDotEnvFile(file) {
  try {
    return parseDotEnv(fs.readFileSync(file, "utf8"));
  } catch {
    return {};
  }
}

function isLoopbackHost(hostname) {
  const host = String(hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  return host === "127.0.0.1" || host === "localhost" || host === "::1";
}

function looksUsableOrigin(value) {
  const origin = String(value || "").trim().replace(/\/$/, "");
  if (!origin) return "";
  if (/trycloudflare\.com|example\.com|your-domain/i.test(origin)) return "";
  try {
    const url = new URL(origin);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    if (!isLoopbackHost(url.hostname)) return "";
    return origin;
  } catch {
    return "";
  }
}

function resolveAccountOrigin({ env = process.env, fileCfg = {} } = {}) {
  const candidates = [env.ZINTRIQ_ACCOUNT_ORIGIN, fileCfg.accountOrigin, LOCAL_ACCOUNT_ORIGIN];
  for (const item of candidates) {
    const origin = looksUsableOrigin(item);
    if (origin) return origin;
  }
  return LOCAL_ACCOUNT_ORIGIN;
}

function loadRepoDotEnv(repoRoot) {
  return {
    ...readDotEnvFile(path.join(repoRoot, ".env")),
    ...readDotEnvFile(path.join(repoRoot, ".env.local")),
  };
}

module.exports = {
  parseDotEnv,
  resolveAccountOrigin,
  loadRepoDotEnv,
  looksUsableOrigin,
  LOCAL_ACCOUNT_ORIGIN,
};
