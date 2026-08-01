import { MODULE_NAV } from "../features/registry.js";
import { OBJECT_TYPES } from "./object-types.js";

/** @typedef {{ id: string, label: string, category: string, icon?: string, keywords?: string[], run: () => void | Promise<void> }} PlatformCommand */

const CREATE_COLLECTIONS = [
  "organizations", "workspaces", "catalog", "customers", "transactions",
  "team", "operations", "documents", "assets", "tags",
];

function dispatchClearSelection() {
  window.dispatchEvent(new CustomEvent("bos:clear-selection"));
}

function dispatchSelectAll() {
  window.dispatchEvent(new CustomEvent("bos:select-all"));
}

function dispatchBatchAction(action) {
  window.dispatchEvent(new CustomEvent("bos:batch-action", { detail: { action } }));
}

/** @type {PlatformCommand[]} */
const WORKFLOW_COMMANDS = [
  { id: "select-all", label: "Select all in list", category: "Workflow", keywords: ["select", "all"], run: dispatchSelectAll },
  { id: "clear-selection", label: "Clear selection", category: "Workflow", keywords: ["deselect", "clear"], run: dispatchClearSelection },
  { id: "batch-archive", label: "Archive selected", category: "Workflow", keywords: ["archive", "bulk"], run: () => dispatchBatchAction("archive") },
  { id: "batch-export", label: "Export selected", category: "Workflow", keywords: ["export", "download"], run: () => dispatchBatchAction("export") },
  { id: "batch-delete", label: "Delete selected", category: "Workflow", keywords: ["delete", "remove"], run: () => dispatchBatchAction("delete") },
];

/** @type {PlatformCommand[]} */
const ACTION_COMMANDS = [
  ...CREATE_COLLECTIONS.map((collection) => ({
    id: `create-${collection}`,
    label: `Create ${OBJECT_TYPES[collection]?.label?.toLowerCase() || collection}`,
    category: "Actions",
    keywords: ["new", "create", collection],
    run: () => dispatchCreate(collection),
  })),
  ...WORKFLOW_COMMANDS,
  { id: "mark-notifications-read", label: "Mark all notifications read", category: "Actions", keywords: ["notifications", "clear"], run: () => dispatchMarkNotificationsRead() },
];

function dispatchCreate(collection) {
  window.dispatchEvent(new CustomEvent("bos:create-object", { detail: { collection } }));
}

function dispatchMarkNotificationsRead() {
  window.dispatchEvent(new CustomEvent("bos:mark-notifications-read"));
}

function dispatchOpenObject(collection, id) {
  window.dispatchEvent(new CustomEvent("bos:open-object", { detail: { collection, id } }));
}

export function getNavigationCommands() {
  return MODULE_NAV.map((m) => ({
    id: `nav-${m.id}`,
    label: m.label,
    category: "Pages",
    icon: m.icon,
    keywords: [m.id, m.label.toLowerCase()],
    run: () => { window.location.href = m.path; },
  }));
}

export function getActionCommands() {
  return ACTION_COMMANDS;
}

export function getSettingsCommands() {
  return [
    {
      id: "settings-account",
      label: "Account settings",
      category: "Settings",
      keywords: ["profile", "password", "2fa"],
      run: () => { window.location.href = "/account"; },
    },
    {
      id: "settings-qr",
      label: "QR Workspace",
      category: "Settings",
      keywords: ["storefront", "qr"],
      run: () => { window.location.href = "/my-stores"; },
    },
  ];
}

export function buildObjectCommand(collection, id, label) {
  const typeDef = OBJECT_TYPES[collection];
  return {
    id: `obj-${collection}-${id}`,
    label,
    category: typeDef?.labelPlural || collection,
    keywords: [collection, id, label.toLowerCase()],
    run: () => {
      const path = typeDef?.modulePath || "/app";
      if (window.location.pathname === path) {
        dispatchOpenObject(collection, id);
      } else {
        window.location.href = `${path}#obj/${collection}/${id}`;
      }
    },
  };
}

export function searchCommands(query, objectResults = [], recentObjects = [], favoriteObjects = []) {
  const q = query.trim().toLowerCase();
  /** @type {PlatformCommand[]} */
  let commands = [
    ...getNavigationCommands(),
    ...getActionCommands(),
    ...getSettingsCommands(),
  ];

  objectResults.forEach((r) => {
    commands.push(buildObjectCommand(r.collection, r.record.id, r.label));
  });

  recentObjects.forEach((r) => {
    commands.push({ ...buildObjectCommand(r.collection, r.id, r.label), category: "Recent" });
  });

  favoriteObjects.forEach((r) => {
    commands.push({ ...buildObjectCommand(r.collection, r.id, r.label), category: "Favorites" });
  });

  if (!q) return commands;

  return commands.filter((cmd) => {
    const hay = [cmd.label, cmd.category, ...(cmd.keywords || []), cmd.id].join(" ").toLowerCase();
    return hay.includes(q) || cmd.label.toLowerCase().includes(q);
  });
}

export { dispatchOpenObject, dispatchCreate };
