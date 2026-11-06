/**
 * Loopback navigation allow-list for the Electron shell.
 */

function pathAllowed(pathname) {
  const path = String(pathname || "");
  if (!path) return false;
  if (path === "/") return true;
  if (path === "/editor" || path.startsWith("/editor/")) return true;
  if (path.startsWith("/static/")) return true;
  if (path.startsWith("/api/")) return true;
  if (path === "/healthz" || path === "/favicon.ico") return true;
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
  pathAllowed,
  navigationAllowed,
};
