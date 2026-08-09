import { openCreatePicker } from "./create-picker.js";
import { selection } from "../services/selection.js";

export function initQuickActions() {
  const fab = document.getElementById("bos-quick-fab");
  const menu = document.getElementById("bos-quick-menu");
  if (!fab || !menu) return;

  fab.setAttribute("aria-label", "Create");
  fab.title = "Create (⌘N)";

  fab.addEventListener("click", () => {
    if (selection.size > 0) {
      document.getElementById("bos-action-bar")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    openCreatePicker();
  });

  selection.subscribe(() => {
    fab.classList.toggle("bos-quick-fab--active", selection.size > 0);
    fab.setAttribute("aria-label", selection.size > 0 ? `${selection.size} selected` : "Create");
  });
}
