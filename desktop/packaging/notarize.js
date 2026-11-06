/**
 * Notarize the macOS app when Apple credentials are present.
 * Local/CI packs without APPLE_ID skip this and stay unsigned or ad-hoc.
 */
const path = require("path");

async function notarizeMac(context) {
  if (!context || context.electronPlatformName !== "darwin") return { skipped: true, reason: "not-mac" };
  const appleId = process.env.APPLE_ID;
  const appleIdPassword = process.env.APPLE_APP_SPECIFIC_PASSWORD;
  const teamId = process.env.APPLE_TEAM_ID;
  if (!appleId || !appleIdPassword || !teamId) {
    console.log("notarize skipped: set APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID");
    return { skipped: true, reason: "missing-credentials" };
  }
  const appName = context.packager.appInfo.productFilename;
  const appPath = path.join(context.appOutDir, `${appName}.app`);
  const { notarize } = require("@electron/notarize");
  await notarize({
    appPath,
    appleId,
    appleIdPassword,
    teamId,
  });
  console.log(`notarized ${appPath}`);
  return { skipped: false, appPath };
}

exports.default = notarizeMac;
exports.notarizeMac = notarizeMac;
