const PREFIX = "bos-ui:";

export function getModuleUi(moduleId) {
  try {
    const raw = localStorage.getItem(`${PREFIX}${moduleId}`);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function setModuleUi(moduleId, patch) {
  const current = getModuleUi(moduleId);
  const next = { ...current, ...patch };
  localStorage.setItem(`${PREFIX}${moduleId}`, JSON.stringify(next));
  return next;
}

export function getDefaultUi(moduleId) {
  return {
    view: "table",
    filter: "all",
    sortKey: "name",
    sortAsc: true,
    search: "",
    tagId: "",
    groupBy: false,
    density: "comfortable",
    scrollTop: 0,
    tableLayout: { order: [], hidden: [], widths: {}, pinned: [] },
    drawerTab: "overview",
    ...getModuleUi(moduleId),
  };
}

export function getWorkspacePrefs() {
  try {
    return JSON.parse(localStorage.getItem(`${PREFIX}workspace`) || "{}");
  } catch {
    return {};
  }
}

export function setWorkspacePrefs(patch) {
  const next = { ...getWorkspacePrefs(), ...patch };
  localStorage.setItem(`${PREFIX}workspace`, JSON.stringify(next));
  return next;
}

export function isSidebarCollapsed() {
  return getWorkspacePrefs().sidebarCollapsed === true;
}

export function toggleSidebarCollapsed() {
  const collapsed = !isSidebarCollapsed();
  setWorkspacePrefs({ sidebarCollapsed: collapsed });
  return collapsed;
}

export function getDrawerState() {
  try {
    return JSON.parse(sessionStorage.getItem(`${PREFIX}drawer`) || "null");
  } catch {
    return null;
  }
}

export function setDrawerState(state) {
  if (state) sessionStorage.setItem(`${PREFIX}drawer`, JSON.stringify(state));
  else sessionStorage.removeItem(`${PREFIX}drawer`);
}
