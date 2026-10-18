/**
 * Client toast/alert i18n. Templates inject window.__MQ_T__ from the active locale.
 * Usage: t("Please sign in to continue.") → localized string, or original if missing.
 */
(function (global) {
  function t(message, vars) {
    var catalog = global.__MQ_T__ || {};
    var text = catalog[message] || message;
    if (vars && typeof vars === "object") {
      Object.keys(vars).forEach(function (key) {
        text = String(text).split("{" + key + "}").join(String(vars[key]));
      });
    }
    return text;
  }
  global.t = t;
  global.mqT = t;
})(typeof window !== "undefined" ? window : globalThis);
