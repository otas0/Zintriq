/** Unified notifications — wraps showToast with semantic types. */

import { showToast } from "./api.js";

/** @param {string} message @param {object} [opts] */
export function notifySuccess(message, opts = {}) {
  showToast(message, { ...opts, type: "success" });
}

/** @param {string} message @param {object} [opts] */
export function notifyWarning(message, opts = {}) {
  showToast(message, { ...opts, type: "warning" });
}

/** @param {string} message @param {object} [opts] */
export function notifyError(message, opts = {}) {
  showToast(message, { ...opts, type: "error" });
}
