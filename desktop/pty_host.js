/**
 * Cross-platform interactive PTY via node-pty.
 * Windows: ConPTY; macOS/Linux: unix98 pty.
 */

const os = require("os");
const path = require("path");

let pty = null;
try {
  pty = require("node-pty");
} catch (err) {
  // Wrong Node ABI (host node vs Electron) or missing binary → Flask PTY fallback.
  pty = null;
  if (process.env.ZINTRIQ_DEBUG_PTY === "1") {
    console.warn("[pty_host] node-pty unavailable:", err && err.message);
  }
}

const sessions = new Map();

function available() {
  return Boolean(pty);
}

function defaultShell() {
  if (process.platform === "win32") {
    return process.env.COMSPEC || "powershell.exe";
  }
  return process.env.SHELL || "/bin/bash";
}

function defaultArgs() {
  if (process.platform === "win32") return [];
  return ["-l"];
}

function start({ cwd, cols = 80, rows = 24, onData, onExit }) {
  if (!pty) {
    throw new Error("node-pty is not available");
  }
  const shell = defaultShell();
  const args = defaultArgs();
  const env = { ...process.env };
  delete env.ZINTRIQ_DESKTOP_TOKEN;
  env.TERM = env.TERM || "xterm-256color";
  env.COLORTERM = env.COLORTERM || "truecolor";

  const opts = {
    name: "xterm-256color",
    cols: Math.max(20, Number(cols) || 80),
    rows: Math.max(5, Number(rows) || 24),
    cwd: cwd || os.homedir(),
    env,
  };
  if (process.platform === "win32") {
    opts.useConpty = true;
  }

  const term = pty.spawn(shell, args, opts);
  const id = `${process.platform}-${term.pid}-${Date.now().toString(36)}`;
  const sess = { id, term, shell, cwd: opts.cwd };
  sessions.set(id, sess);

  term.onData((data) => {
    if (typeof onData === "function") onData(id, data);
  });
  term.onExit(({ exitCode }) => {
    sessions.delete(id);
    if (typeof onExit === "function") onExit(id, exitCode);
  });

  return { id, shell, cwd: opts.cwd, pid: term.pid };
}

function write(id, data) {
  const sess = sessions.get(id);
  if (!sess) throw new Error("unknown pty session");
  sess.term.write(data == null ? "" : String(data));
  return { ok: true };
}

function resize(id, cols, rows) {
  const sess = sessions.get(id);
  if (!sess) throw new Error("unknown pty session");
  sess.term.resize(Math.max(20, Number(cols) || 80), Math.max(5, Number(rows) || 24));
  return { ok: true };
}

function kill(id) {
  const sess = sessions.get(id);
  if (!sess) return { ok: true };
  try {
    sess.term.kill();
  } catch {
    /* ignore */
  }
  sessions.delete(id);
  return { ok: true };
}

function killAll() {
  for (const id of [...sessions.keys()]) kill(id);
}

function resolveWorkspaceCwd(userData, recipe) {
  if (process.env.ZINTRIQ_WORKSPACE) return path.resolve(process.env.ZINTRIQ_WORKSPACE);
  if (recipe && recipe.dataDir) return path.join(String(recipe.dataDir), "workspace");
  return path.join(userData, "workspace");
}

module.exports = {
  available,
  start,
  write,
  resize,
  kill,
  killAll,
  resolveWorkspaceCwd,
  defaultShell,
};
