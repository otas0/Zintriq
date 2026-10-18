/**
 * Desktop account PKCE. The verifier stays on the machine; the browser
 * confirms on the public Flask site (/desktop/authorize), not Auth0.
 */

const crypto = require("crypto");

function base64Url(buffer) {
  return Buffer.from(buffer)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createPkcePair() {
  const verifier = base64Url(crypto.randomBytes(32));
  const challenge = base64Url(crypto.createHash("sha256").update(verifier).digest());
  return { verifier, challenge };
}

function buildDesktopAuthorizeUrl({
  origin,
  clientId,
  redirectUri,
  state,
  codeChallenge,
  deviceName,
  os,
  version,
}) {
  const base = String(origin || "").replace(/\/$/, "");
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });
  if (deviceName) params.set("device_name", deviceName);
  if (os) params.set("os", os);
  if (version) params.set("version", version);
  return `${base}/desktop/authorize?${params.toString()}`;
}

function parseAuthCallback(urlString) {
  const url = new URL(urlString);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");
  const errorDescription = url.searchParams.get("error_description");
  return { code, state, error, errorDescription };
}

function authorizePathFromUrl(origin, authorizeUrl) {
  const base = String(origin || "").replace(/\/$/, "");
  const full = String(authorizeUrl || "");
  if (full.startsWith(base)) return full.slice(base.length) || "/";
  try {
    const dest = new URL(full);
    return `${dest.pathname}${dest.search}`;
  } catch {
    return "/desktop/authorize";
  }
}

function buildDesktopRegisterUrl({ origin, authorizeUrl }) {
  const base = String(origin || "").replace(/\/$/, "");
  const next = authorizePathFromUrl(origin, authorizeUrl);
  const params = new URLSearchParams({ from: "desktop", next });
  return `${base}/register?${params.toString()}`;
}

module.exports = {
  createPkcePair,
  buildDesktopAuthorizeUrl,
  buildDesktopRegisterUrl,
  parseAuthCallback,
};
