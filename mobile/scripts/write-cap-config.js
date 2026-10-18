/**
 * Writes capacitor.config.json from PUBLIC_BASE_URL / MOBILE_SERVER_URL.
 * Run: npm run config
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const ENV_PATH = path.join(ROOT, ".env.local");

function loadEnv() {
  const out = {};
  if (!fs.existsSync(ENV_PATH)) return out;
  for (const line of fs.readFileSync(ENV_PATH, "utf8").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const [k, ...rest] = t.split("=");
    out[k.trim()] = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
  }
  return out;
}

const env = { ...process.env, ...loadEnv() };
const base = (env.MOBILE_SERVER_URL || env.PUBLIC_BASE_URL || "http://127.0.0.1:5001").replace(/\/$/, "");
// Studio shell only — Community / marketing stay on the web browser.
const startUrl = `${base}/studio`;
const cleartext = base.startsWith("http://");

const config = {
  appId: "com.zintriq.studio",
  appName: "Zintriq Studio",
  webDir: "www",
  server: {
    url: startUrl,
    cleartext,
    androidScheme: "https",
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1800,
      backgroundColor: "#111111",
      showSpinner: false,
    },
    StatusBar: {
      style: "DARK",
      backgroundColor: "#111111",
    },
  },
};

fs.writeFileSync(path.join(__dirname, "..", "capacitor.config.json"), JSON.stringify(config, null, 2));
console.log(`Capacitor server URL → ${startUrl}`);
