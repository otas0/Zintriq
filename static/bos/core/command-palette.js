import { escapeHtml } from "../services/search.js";
import { searchCommands } from "../platform/commands.js";
import { getObjectRecents, getObjectFavorites } from "../platform/recents.js";
import { closeDrawer } from "../services/api.js";
import { globalSearchGrouped } from "../services/global-search.js";

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
  let renderSeq = 0;

  const render = async () => {
    const seq = ++renderSeq;
    const q = input.value.trim();
    currentCommands = searchCommands(q, [], getObjectRecents(), getObjectFavorites());

    if (q.length >= 2) {
      const { api } = await globalSearchGrouped(q);
      if (seq !== renderSeq) return;
      api.forEach((hit) => {
        currentCommands.unshift({
          id: `api-${hit.type}-${hit.id}`,
          label: hit.label,
          category: hit.type.charAt(0).toUpperCase() + hit.type.slice(1),
          keywords: [hit.type],
          run: () => { window.location.href = hit.href; },
        });
      });
    }

    currentCommands = renderCommandList(currentCommands, results);
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
    closeDrawer();
  };

  window.addEventListener("bos:open-command-palette", open);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });

  input.addEventListener("input", render);

  input.addEventListener("keydown", (e) => {
    const items = results.querySelectorAll(".bos-palette-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      highlightActive(results);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      highlightActive(results);
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      currentCommands[activeIndex]?.run();
      close();
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  });

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      paletteOpen ? close() : open();
    }
  });

  document.getElementById("bos-search-trigger")?.addEventListener("click", open);
}

export { paletteOpen };
