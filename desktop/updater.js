/**
 * Version compare plus packaged auto-install via electron-updater.
 * Dev (`electron .`) never auto-installs.
 */

function parseVersion(value) {
  return String(value || "0")
    .split(".")
    .map((part) => parseInt(part.replace(/[^0-9].*$/, ""), 10) || 0);
}

function isNewer(remote, local) {
  const a = parseVersion(remote);
  const b = parseVersion(local);
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i += 1) {
    if ((a[i] || 0) > (b[i] || 0)) return true;
    if ((a[i] || 0) < (b[i] || 0)) return false;
  }
  return false;
}

function updateFeedUrl(origin) {
  const fromEnv = String(process.env.ZINTRIQ_UPDATE_ORIGIN || "").replace(/\/$/, "");
  if (fromEnv) return `${fromEnv}/desktop/updates`;
  const base = String(origin || "").replace(/\/$/, "");
  if (base) return `${base}/desktop/updates`;
  return "";
}

function canAutoInstall({ packaged, env = process.env } = {}) {
  if (!packaged) return false;
  if (env.ZINTRIQ_SMOKE === "1") return false;
  if (env.ZINTRIQ_DISABLE_AUTO_UPDATE === "1") return false;
  return true;
}

async function installFromFeed({ feedUrl, dialog, autoUpdater }) {
  const url = String(feedUrl || "").replace(/\/$/, "");
  if (!url) throw new Error("missing update feed");
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.setFeedURL({ provider: "generic", url });
  const check = await autoUpdater.checkForUpdates();
  const info = check && check.updateInfo;
  if (!info || !info.version) return { status: "none" };
  const choice = await dialog.showMessageBox({
    type: "info",
    buttons: ["Install", "Later"],
    defaultId: 0,
    cancelId: 1,
    message: `Version ${info.version} is available.`,
    detail: "The update is signed. Zintriq will download it, then restart to install.",
  });
  if (choice.response !== 0) return { status: "later", version: info.version };
  await autoUpdater.downloadUpdate();
  autoUpdater.quitAndInstall(false, true);
  return { status: "installing", version: info.version };
}

module.exports = {
  parseVersion,
  isNewer,
  updateFeedUrl,
  canAutoInstall,
  installFromFeed,
};
