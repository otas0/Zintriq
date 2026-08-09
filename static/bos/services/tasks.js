/** Task Platform API helpers — quick create from any module. */

import { openDrawer, closeDrawer, showToast } from "./api.js";
import { fetchJson, wsQuery } from "./bos-api.js";
import { getActiveWorkspaceId } from "./workspace-context.js";

/** @type {Set<string>} */
let taskPermissions = new Set();

export async function loadTaskPermissions(wsId) {
  const q = wsId ? `?workspace_id=${wsId}` : wsQuery();
  const ctx = await fetchJson(`/api/tasks/context${q}`);
  taskPermissions = new Set(ctx.permissions || []);
  return ctx;
}

export function canTask(perm) {
  return taskPermissions.has(perm);
}

/**
 * @param {object} opts
 * @param {string} opts.title
 * @param {string} [opts.description]
 * @param {string} [opts.related_object_type]
 * @param {number} [opts.related_object_id]
 * @param {number} [opts.assignee_id]
 * @param {string} [opts.priority]
 * @param {string} [opts.due_date]
 */
export async function createTask(opts) {
  const body = {
    workspace_id: getActiveWorkspaceId(),
    title: opts.title,
    description: opts.description,
    related_object_type: opts.related_object_type,
    related_object_id: opts.related_object_id,
    assignee_id: opts.assignee_id,
    priority: opts.priority || "medium",
    due_date: opts.due_date,
  };
  return fetchJson("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * Open quick-create drawer — used from Customer, Feedback, etc.
 * @param {object} [prefill]
 */
export function openTaskCreateDrawer(prefill = {}) {
  if (!canTask("task.create")) {
    showToast("You don't have permission to create tasks");
    return;
  }
  const rel = prefill.related_object_type
    ? `<p class="bos-card__meta">Linked to ${prefill.related_object_type}${prefill.related_label ? `: ${prefill.related_label}` : ""}</p>`
    : "";
  openDrawer("Create task", `${rel}
    <form id="quick-task-form" class="bos-form">
      <label class="bos-field"><span>Title</span><input name="title" required value="${prefill.title || ""}"></label>
      <label class="bos-field"><span>Description</span><textarea name="description" rows="3">${prefill.description || ""}</textarea></label>
      <label class="bos-field"><span>Priority</span>
        <select name="priority"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option><option value="critical">Critical</option></select>
      </label>
      <label class="bos-field"><span>Due date</span><input name="due_date" type="date"></label>
      <button type="submit" class="bos-btn bos-btn-primary">Create task</button>
    </form>`);
  document.getElementById("quick-task-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await createTask({
        title: String(fd.get("title")),
        description: String(fd.get("description") || ""),
        priority: String(fd.get("priority") || "medium"),
        due_date: fd.get("due_date") || undefined,
        related_object_type: prefill.related_object_type,
        related_object_id: prefill.related_object_id,
      });
      closeDrawer();
      showToast("Task created");
      window.dispatchEvent(new CustomEvent("bos:tasks-changed"));
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to create task");
    }
  });
}

export function initTaskQuickCreate() {
  window.addEventListener("bos:create-task", (e) => {
    openTaskCreateDrawer(e.detail || {});
  });
}
