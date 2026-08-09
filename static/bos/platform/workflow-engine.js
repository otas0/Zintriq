/**
 * Business OS Workflow Engine — registry mirror (JavaScript).
 *
 * Spec: docs/bos/WORKFLOW_ENGINE.md
 * Backend: bos/workflows.py, workflow_platform.py
 */

/** @typedef {'draft'|'active'|'paused'|'archived'} WorkflowStatus */
/** @typedef {'running'|'completed'|'failed'|'cancelled'} RunStatus */

/** @type {readonly string[]} */
export const WORKFLOW_STATUSES = ["draft", "active", "paused", "archived"];

/** @type {readonly string[]} */
export const RUN_STATUSES = ["running", "completed", "failed", "cancelled"];

/** @type {readonly string[]} */
export const TRIGGER_TYPES = ["event", "manual", "scheduled", "api"];

/** @type {readonly string[]} */
export const ACTION_TYPES = [
  "send_notification", "create_task", "assign_employee", "add_tag",
  "update_status", "move_object", "generate_document", "send_email", "call_api",
];

/** @type {readonly string[]} */
export const CONDITION_OPS = ["eq", "ne", "lt", "lte", "gt", "gte", "in", "contains", "exists"];

/** @type {readonly { id: string, label: string }[]} */
export const WORKFLOW_STRUCTURE = [
  { id: "trigger", label: "Trigger" },
  { id: "conditions", label: "Conditions" },
  { id: "actions", label: "Actions" },
  { id: "completion", label: "Completion" },
];

/** @type {readonly { name: string, trigger: string, description: string }[]} */
export const DEFAULT_TEMPLATES = [
  { name: "Negative feedback follow-up", trigger: "feedback.submitted", description: "Rating below 3 → notify + task" },
  { name: "New customer welcome", trigger: "customer.joined", description: "Welcome notification on join" },
  { name: "Customer onboarding", trigger: "manual", description: "Manual onboarding checklist" },
];

/** @param {number} [workspaceId] @param {string} [status] */
export async function fetchWorkflows(workspaceId, status) {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", String(workspaceId));
  if (status) params.set("status", status);
  const res = await fetch(`/api/workflows?${params}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error("Failed to load workflows");
  return res.json();
}

/** @param {number} workflowId @param {object} [payload] */
export async function startWorkflow(workflowId, payload = {}) {
  const res = await fetch(`/api/workflows/${workflowId}/start`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "Workflow start failed");
  }
  return res.json();
}

/** @param {number} [workspaceId] @param {number} [limit] */
export async function fetchWorkflowExecutions(workspaceId, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", String(workspaceId));
  const res = await fetch(`/api/workflows/executions?${params}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error("Failed to load executions");
  return res.json();
}

/** @param {number} [workspaceId] */
export async function fetchWorkflowTasks(workspaceId) {
  const params = workspaceId ? `?workspace_id=${workspaceId}` : "";
  const res = await fetch(`/api/workflows/tasks${params}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error("Failed to load tasks");
  return res.json();
}
