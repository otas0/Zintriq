/**
 * Loopback navigation allow-list for the Electron shell.
 * Fetch/XHR is not gated here — only top-level navigations / redirects.
 */

function isAuthPagePath(pathname) {
  return pathname === "/login" || pathname === "/register" || pathname.startsWith("/login/");
}

function pathAllowed(pathname) {
  const path = String(pathname || "");
  if (!path || isAuthPagePath(path)) return false;
  if (path === "/") return true;
  if (path === "/studio" || path.startsWith("/studio/")) return true;
  if (path === "/app/community" || path.startsWith("/app/community/")) return true;
  if (path === "/build" || path.startsWith("/build/")) return true;
  if (path.startsWith("/builder-runtime/")) return true;
  if (path.startsWith("/static/")) return true;
  if (path.startsWith("/api/builder-core/") || path.startsWith("/api/studio/")) return true;
  if (path === "/healthz" || path === "/favicon.ico" || path === "/logout") return true;
  return false;
}

function navigationAllowed(url, port) {
  let dest;
  try {
    dest = new URL(url);
  } catch {
    return false;
  }
  if (dest.protocol !== "http:" || dest.hostname !== "127.0.0.1" || dest.port !== String(port)) {
    return false;
  }
  return pathAllowed(dest.pathname);
}

module.exports = {
  isAuthPagePath,
  pathAllowed,
  navigationAllowed,
};
