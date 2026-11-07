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
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    if (!/MimeType=/i.test(text)) continue;
    const next = text.replace(/^MimeType=.*$/im, `MimeType=${PLUGIN_MIME};`);
    if (next === text) continue;
    fs.writeFileSync(file, next);
    console.log("after-pack-linux-mime: plugin-only MimeType →", file);
  }
};
