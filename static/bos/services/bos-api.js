/** Shared fetch helpers for Zintriq API modules. */

import { getActiveWorkspaceId } from "./workspace-context.js";
import { getCsrf } from "./api.js";

/** @type {Map<string, Promise<unknown>>} */
const _inflight = new Map();

export async function fetchJson(url, opts = {}) {
  const method = (opts.method || "GET").toUpperCase();
  const headers = { ...(opts.headers || {}) };

  if (method !== "GET" && method !== "HEAD") {
    headers["X-CSRF-Token"] = getCsrf();
    if (headers["Content-Type"]?.includes("application/json") && typeof opts.body === "string") {
      try {
        const parsed = JSON.parse(opts.body);
        parsed.csrf_token = getCsrf();
        opts = { ...opts, body: JSON.stringify(parsed) };
      } catch {
        /* non-JSON body — header only */
      }
    }
  }

  const dedupeKey = method === "GET" ? url : "";
  if (dedupeKey && _inflight.has(dedupeKey)) {
    return _inflight.get(dedupeKey);
  }

  const run = (async () => {
    const res = await fetch(url, { credentials: "same-origin", ...opts, headers });
  if (!res.ok) {
    const ct = res.headers.get("content-type") || "";
    let message = `Request failed (${res.status})`;
    if (ct.includes("application/json")) {
      const err = await res.json().catch(() => ({}));
      message = err.error || message;
    } else {
      const text = await res.text().catch(() => "");
      if (text) message = text.replace(/<[^>]+>/g, "").trim() || message;
    }
    throw new Error(message);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
  })();

  if (dedupeKey) {
    _inflight.set(dedupeKey, run);
    run.finally(() => _inflight.delete(dedupeKey));
  }
  return run;
}

export function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

export function wsQuery(extra = "") {
  const ws = getActiveWorkspaceId();
  const base = ws ? `workspace_id=${ws}` : "";
  if (!extra) return base ? `?${base}` : "";
  return base ? `?${base}&${extra}` : `?${extra}`;
}

export function money(n) {
  const v = Number(n);
  return Number.isFinite(v) ? `$${v.toFixed(2)}` : "—";
}
