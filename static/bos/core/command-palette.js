import * as store from "../core/store.js";
import { escapeHtml } from "../services/search.js";
import { searchCommands } from "../platform/commands.js";
import { getObjectRecents, getObjectFavorites } from "../platform/recents.js";
import { closeDrawer } from "../services/api.js";
import { closeObjectDrawer } from "../platform/object-detail.js";

let paletteOpen = false;
/** @type {number} */
let activeIndex = -1;

/** @param {import('../platform/commands.js').PlatformCommand[]} commands */
function renderCommandList(commands, container) {
  /** @type {Record<string, import('../platform/commands.js').PlatformCommand[]>} */
  const groups = {};
  commands.forEach((cmd) => {
    if (!groups[cmd.category]) groups[cmd.category] = [];
    groups[cmd.category].push(cmd);
  });

  let html = "";
  Object.entries(groups).forEach(([category, items]) => {
    html += `<p class="bos-palette-hint">${escapeHtml(category)}</p>`;
    items.forEach((cmd) => {
      html += `<button type="button" class="bos-palette-item" data-cmd-index="${html.length}" data-cmd-id="${escapeHtml(cmd.id)}">
        ${cmd.icon ? `<span>${escapeHtml(cmd.icon)}</span>` : ""}
        <span>${escapeHtml(cmd.label)}</span>
      </button>`;
    });
  });

  container.innerHTML = html || `<p class="bos-palette-empty">No commands found</p>`;
  activeIndex = -1;

  const flat = commands;
  container.querySelectorAll(".bos-palette-item").forEach((btn, i) => {
    btn.addEventListener("click", () => flat[i]?.run());
  });
  highlightActive(container);
  return flat;
}

/** @param {HTMLElement} container */
function highlightActive(container) {
  container.querySelectorAll(".bos-palette-item").forEach((btn, i) => {
    btn.classList.toggle("is-active", i === activeIndex);
    if (i === activeIndex) btn.scrollIntoView({ block: "nearest" });
  });
}

export function initCommandPalette() {
  const overlay = document.getElementById("bos-command-palette");
  const input = document.getElementById("bos-command-input");
  const results = document.getElementById("bos-command-results");
  if (!overlay || !input || !results) return;

  /** @type {import('../platform/commands.js').PlatformCommand[]} */
  let currentCommands = [];

  const render = () => {
    const q = input.value.trim();
    const objectHits = q ? store.globalSearch(q) : [];
    currentCommands = searchCommands(q, objectHits, getObjectRecents(), getObjectFavorites());
    renderCommandList(currentCommands, results);
  };

  const open = () => {
    paletteOpen = true;
    overlay.classList.remove("hidden");
    input.value = "";
    render();
    input.focus();
  };

  const close = () => {
    paletteOpen = false;
    overlay.classList.add("hidden");
    activeIndex = -1;
  };

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (paletteOpen) close();
      else open();
    }
    if (e.key === "Escape" && paletteOpen) {
      e.preventDefault();
      close();
      closeObjectDrawer();
    }
    if (!paletteOpen) return;
    const items = results.querySelectorAll(".bos-palette-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      highlightActive(results);
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      highlightActive(results);
    }
    if (e.key === "Enter" && document.activeElement === input) {
      e.preventDefault();
      if (activeIndex >= 0 && currentCommands[activeIndex]) currentCommands[activeIndex].run();
      else if (currentCommands[0]) currentCommands[0].run();
      close();
    }
  });

  overlay.querySelector("[data-palette-close]")?.addEventListener("click", close);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  input.addEventListener("input", render);
}
