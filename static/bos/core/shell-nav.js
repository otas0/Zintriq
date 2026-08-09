/** Application Shell — QR-centric platform navigation. */

import { visibleNav, PRODUCT_CREATE_ITEMS } from "../product-focus.js";

/** @typedef {{ id: string, label: string, icon: string, path: string, external?: boolean }} ShellNavItem */

/** @type {readonly ShellNavItem[]} */
export const SHELL_NAV = visibleNav();

/** @type {readonly { label: string, action: string, collection?: string, path?: string, href?: string }[]} */
export const CREATE_PICKER_ITEMS = PRODUCT_CREATE_ITEMS;

export function shellNavItem(moduleId) {
  return SHELL_NAV.find((n) => n.id === moduleId) || null;
}
