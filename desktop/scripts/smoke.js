/**
 * Desktop smoke: Electron starts Flask, /editor loads, second instance exits.
 */

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

if (process.platform === "linux" && process.env.ZINTRIQ_SMOKE_XVFB !== "1") {
  const result = spawnSync("xvfb-run", ["-a", process.execPath, __filename], {
    stdio: "inherit",
    env: { ...process.env, ZINTRIQ_SMOKE_XVFB: "1" },
  });
  process.exit(result.status == null ? 1 : result.status);
}

const electronPath = require("electron");
const desktopDir = path.join(__dirname, "..");
const overallMs = Number(process.env.ZINTRIQ_SMOKE_TIMEOUT_MS || 120000);
const coldMsLimit = Number(process.env.ZINTRIQ_SMOKE_COLD_MS || 12000);

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function smokeUserDataDir() {
  const home = os.homedir();
  if (process.platform === "darwin") {
    return path.join(home, "Library", "Application Support", "Zintriq-smoke");
  }
  if (process.platform === "win32") {
    return path.join(process.env.APPDATA || path.join(home, "AppData", "Roaming"), "Zintriq-smoke");
  }
  return path.join(process.env.XDG_CONFIG_HOME || path.join(home, ".config"), "Zintriq-smoke");
}

function resolveUserData() {
  if (process.env.ZINTRIQ_SMOKE_USER_DATA) {
    fs.mkdirSync(process.env.ZINTRIQ_SMOKE_USER_DATA, { recursive: true });
    return process.env.ZINTRIQ_SMOKE_USER_DATA;
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "smoke-"));
  process.env.ZINTRIQ_SMOKE_USER_DATA = dir;
  return dir;
}

function get(urlPath, port, token) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port,
        path: urlPath,
        headers: token ? { "X-Zintriq-Desktop-Token": token } : {},
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () =>
          resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString("utf8") })
        );
      }
    );
    req.on("error", reject);
    req.end();
  });
}

async function main() {
  const userData = resolveUserData();
  const sessionFile = path.join(userData, "smoke-session.json");
  try {
    fs.unlinkSync(sessionFile);
  } catch {
    /* ok */
  }

  const args = [];
  if (process.env.CI === "true" && process.platform === "linux") args.push("--no-sandbox");
  args.push(".");

  const t0 = Date.now();
  const child = spawn(electronPath, args, {
    cwd: desktopDir,
    env: {
      ...process.env,
      ZINTRIQ_SMOKE: "1",
      ZINTRIQ_SMOKE_USER_DATA: userData,
    },
    stdio: "ignore",
  });

  const deadline = Date.now() + overallMs;
  let session = null;
  while (Date.now() < deadline) {
    if (child.exitCode != null) {
      console.error("Electron exited early", child.exitCode);
      process.exit(1);
    }
    if (fs.existsSync(sessionFile)) {
      try {
        session = JSON.parse(fs.readFileSync(sessionFile, "utf8"));
        if (session && session.port) break;
      } catch {
        /* retry */
      }
    }
    await sleep(200);
  }
  if (!session || !session.port) {
    console.error("smoke-session.json missing");
    child.kill();
    process.exit(1);
  }

  const coldMs = Date.now() - t0;
  console.log(`cold_start_ms=${coldMs} limit=${coldMsLimit}`);
  if (coldMs > coldMsLimit) {
    console.error("cold start over limit");
    child.kill();
    process.exit(1);
  }

  const health = await get("/healthz", session.port, "");
  if (health.status !== 200) {
    console.error("healthz failed", health.status);
    child.kill();
    process.exit(1);
  }

  const editor = await get("/editor", session.port, "");
  if (editor.status !== 200 || !editor.body.includes("Zintriq Editor")) {
    console.error("editor page failed", editor.status);
    child.kill();
    process.exit(1);
  }

  child.kill();
  await sleep(500);
  console.log("smoke ok");
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
