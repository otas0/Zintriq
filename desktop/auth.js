/**
 * Auth0 Authorization Code + PKCE helpers for Zintriq Studio (native/desktop).
 * code_verifier stays on the desktop; exchange goes through the Flask API
 * so Auth0 client secrets never ship inside the Electron app.
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

function buildAuthorizeUrl({
  domain,
  clientId,
  redirectUri,
  state,
  codeChallenge,
  audience,
  screenHint,
}) {
  const issuer = domain.startsWith("http") ? domain.replace(/\/$/, "") : `https://${domain}`;
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: "openid profile email offline_access",
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });
  if (audience) params.set("audience", audience);
  if (screenHint) params.set("screen_hint", screenHint);
  return `${issuer}/authorize?${params.toString()}`;
}

function parseAuthCallback(urlString) {
  const url = new URL(urlString);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");
  const errorDescription = url.searchParams.get("error_description");
  return { code, state, error, errorDescription };
}

module.exports = {
  createPkcePair,
  buildAuthorizeUrl,
  parseAuthCallback,
};
