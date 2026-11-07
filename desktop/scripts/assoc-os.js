/**
 * Pack-artifact Alternate file-assoc probes.
 * Windows: 手测补 .plugin.json：NSIS 后截该扩展「打开方式」与 OpenWithProgids，对照文档。
 * macOS: 访达补 content type：pack .app 上对插件 JSON 跑 mdls，确认不是 Archive Utility。
 * Linux: mime 补 application/json：用户目录 xdg-mime query default application/json 非 Zintriq，zip 继续 Alternate。
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

function run(cmd, args) {
  return spawnSync(cmd, args, { encoding: "utf8" });
}

function fixturePlugin() {
  const dest = path.join(os.tmpdir(), "assoc-probe.plugin.json");
  fs.writeFileSync(
    dest,
    JSON.stringify({ id: "assoc-probe", form: "view", document: { form: "atom", type: "string", value: "x" } })
  );
  return dest;
}

function probeMac() {
  const file = fixturePlugin();
  const mdls = run("mdls", ["-raw", "-name", "kMDItemContentType", file]);
  const uti = String(mdls.stdout || "").trim();
  const tree = run("mdls", ["-raw", "-name", "kMDItemContentTypeTree", file]);
  const treeText = String(tree.stdout || "") + String(tree.stderr || "");
  if (/zip-archive|org\.gnu\.gnu-zip|com\.pkware\.zip/i.test(uti)) {
    throw new Error("mdls maps .plugin.json to zip/unzip UTI: " + uti);
  }
  if (/zip-archive/i.test(treeText) && !/json/i.test(uti + treeText)) {
    throw new Error("mdls content type tree treats .plugin.json as zip");
  }
  const install = process.env.ZINTRIQ_SMOKE_INSTALL_DIR || "";
  if (install) {
    const plist = fs.readFileSync(path.join(install, "Contents/Info.plist"), "utf8");
    if (!plist.includes("plugin.json")) throw new Error("mac Info.plist missing plugin.json");
    if (!plist.includes("LSHandlerRank") && !plist.includes("Alternate")) {
      throw new Error("mac Info.plist missing Alternate rank");
    }
  }
  const duti = run("duti", ["-x", "json"]);
  if (duti.status === 0) {
    const out = String(duti.stdout || "");
    if (/unzip|the-unarchiver|archive utility/i.test(out) && /zintriq-plugin\.json/i.test(out)) {
      throw new Error("duti default for plugin json is unzip");
    }
  }
}

function probeLinux() {
  const install = process.env.ZINTRIQ_SMOKE_INSTALL_DIR || "";
  const desktopFiles = [];
  function walk(dir, depth) {
    if (depth > 5 || !dir || !fs.existsSync(dir)) return;
    for (const name of fs.readdirSync(dir)) {
      const full = path.join(dir, name);
      let stat;
      try {
        stat = fs.statSync(full);
      } catch {
        continue;
      }
      if (stat.isDirectory()) walk(full, depth + 1);
      else if (name.endsWith(".desktop")) desktopFiles.push(full);
    }
  }
  walk(install, 0);
  const homeApps = path.join(os.homedir(), ".local/share/applications");
  walk(homeApps, 0);
  const text = desktopFiles.map((file) => fs.readFileSync(file, "utf8")).join("\n");
  // Linux .desktop only claims the plugin MIME (not application/zip|json defaults).
  // zip/json associations omit mimeType so electron-builder does not merge them here.
  if (text && !/x-zintriq-plugin|plugin\.json/i.test(text)) {
    throw new Error("linux .desktop missing plugin mime");
  }
  if (text && (/MimeType=.*application\/zip/i.test(text) || /MimeType=.*application\/json(?!\+)/i.test(text))) {
    throw new Error("linux MimeType must not claim application/zip or application/json defaults");
  }
  for (const file of desktopFiles) {
    const body = fs.readFileSync(file, "utf8");
    const match = body.match(/^MimeType=(.*)$/im);
    if (!match) continue;
    const entries = match[1]
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean);
    const unique = new Set(entries);
    if (unique.size !== entries.length) {
      throw new Error(
        "linux MimeType has duplicate entries (merge mimeTypes+desktop+fileAssociations?): " + match[1]
      );
    }
    if (entries.length !== 1 || entries[0] !== "application/x-zintriq-plugin+json") {
      throw new Error(
        "linux MimeType must be exactly application/x-zintriq-plugin+json once, got: " + match[1]
      );
    }
  }
  const zipDefault = String(run("xdg-mime", ["query", "default", "application/zip"]).stdout || "").trim();
  const jsonDefault = String(run("xdg-mime", ["query", "default", "application/json"]).stdout || "").trim();
  if (/zintriq/i.test(zipDefault)) {
    throw new Error("xdg-mime default for application/zip is Zintriq (zip must stay Alternate)");
  }
  if (/zintriq/i.test(jsonDefault)) {
    throw new Error("xdg-mime default for application/json is Zintriq");
  }
  if (process.env.ZINTRIQ_SMOKE_LINUX_MIME === "1") {
    if (!text) throw new Error("linux mime probe found no .desktop in install or ~/.local/share/applications");
    if (!/x-zintriq-plugin|MimeType=.*plugin/i.test(text)) {
      throw new Error("linux MimeType missing application/x-zintriq-plugin+json");
    }
  }
  return { zipDefault: zipDefault, jsonDefault: jsonDefault };
}

function probeWindows() {
  if (process.env.ZINTRIQ_SMOKE_NSIS !== "1") return;
  const plugin = run("reg", ["query", "HKCU\\Software\\Classes\\.plugin.json"]);
  if (plugin.status !== 0) {
    throw new Error("HKCU missing .plugin.json after NSIS");
  }
  const pluginOpenWith = run("reg", ["query", "HKCU\\Software\\Classes\\.plugin.json\\OpenWithProgids"]);
  const openWith = run("reg", ["query", "HKCU\\Software\\Classes\\.zip\\OpenWithProgids"]);
  const zipDefault = run("reg", ["query", "HKCU\\Software\\Classes\\.zip", "/ve"]);
  const zipText = String(openWith.stdout || "") + String(zipDefault.stdout || "");
  if (!/zintriq/i.test(String(plugin.stdout || "") + String(pluginOpenWith.stdout || ""))) {
    throw new Error("HKCU .plugin.json ProgId is not Zintriq");
  }
  if (/zintriq/i.test(String(zipDefault.stdout || "")) && !/OpenWithProgids/i.test(String(zipDefault.stdout || ""))) {
    const def = String(zipDefault.stdout || "");
    if (/REG_SZ\s+\S*Zintriq/i.test(def)) {
      throw new Error("HKCU .zip default is Zintriq; zip must stay Alternate");
    }
  }
  if (openWith.status === 0 && zipText && !/zintriq/i.test(zipText) && !/zintriq/i.test(String(plugin.stdout || ""))) {
    throw new Error("HKCU zip OpenWithProgids missing Zintriq Alternate");
  }
  const exe = process.env.ZINTRIQ_SMOKE_APP || "";
  if (exe && fs.existsSync(exe)) {
    const opened = spawnSync(exe, [fixturePlugin()], { timeout: 20000, windowsHide: true, encoding: "utf8" });
    if (opened.error && opened.error.code !== "ETIMEDOUT") {
      throw new Error("NSIS assoc-open failed: " + opened.error.message);
    }
  } else {
    throw new Error("NSIS assoc-open missing ZINTRIQ_SMOKE_APP");
  }
}

function probe(opts) {
  const options = opts || {};
  if (options.requireNsis) process.env.ZINTRIQ_SMOKE_NSIS = "1";
  if (process.platform === "darwin") probeMac();
  else if (process.platform === "linux") probeLinux();
  else if (process.platform === "win32") probeWindows();
}

if (require.main === module) {
  probe();
  console.log("assoc-os ok " + process.platform);
}

module.exports = { probe };
