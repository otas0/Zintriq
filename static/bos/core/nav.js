export function renderSidebarFavorites() {
  const host = document.getElementById("bos-sidebar-pinned");
  if (!host) return;
  host.classList.add("hidden");
  host.innerHTML = "";
}

export function wireSidebarPinButtons() {
  /* Pinning disabled in shell nav — platforms are fixed */
}

/** @param {string} _moduleId */
export function initNavigation(_moduleId) {
  /* Breadcrumbs removed — page headers carry context */
}
