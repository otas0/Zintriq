/**
 * electron-builder merges fileAssociations mimeTypes into Linux .desktop MimeType.
 * Zip/json stay Alternate on Windows/macOS; Linux must only claim the plugin MIME so
 * xdg-mime never makes Zintriq the default handler for application/zip|json.
 */
const fs = require("fs");
const path = require("path");

const PLUGIN_MIME = "application/x-zintriq-plugin+json";

function walkDesktop(dir, out, depth) {
  if (depth > 6 || !dir || !fs.existsSync(dir)) return out;
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    let stat;
    try {
      stat = fs.statSync(full);
    } catch {
      continue;
    }
    if (stat.isDirectory()) walkDesktop(full, out, depth + 1);
    else if (name.endsWith(".desktop")) out.push(full);
  }
  return out;
}

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== "linux") return;
  const files = walkDesktop(context.appOutDir, [], 0);
  // Deb/AppImage regenerate .desktop later from fileAssociations; this only
  // patches linux-unpacked if a desktop file already exists. Real fix: omit
  // zip/json mimeType from fileAssociations (see package.json + docs).
  if (files.length === 0) {
    console.log(
      "after-pack-linux-mime: no .desktop in appOutDir yet (expected); Linux MimeType must stay plugin-only via fileAssociations without zip/json mimeType"
    );
    return;
  }
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    if (!/MimeType=/i.test(text)) continue;
    const next = text.replace(/^MimeType=.*$/im, `MimeType=${PLUGIN_MIME};`);
    if (next === text) continue;
    fs.writeFileSync(file, next);
    console.log("after-pack-linux-mime: plugin-only MimeType →", file);
  }
};
