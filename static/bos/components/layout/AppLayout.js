/** AppLayout — shell structure (rendered server-side in templates/bos/shell.html). */

export { sidebarNavItems } from "./Sidebar.js";
export { initWorkspaceSelector } from "./WorkspaceSelector.js";

export function describeAppLayout() {
  return {
    structure: ["TopBar", "Sidebar", "Content"],
    responsive: { mobile: "sidebar collapses to menu", desktop: "sidebar + content" },
  };
}
