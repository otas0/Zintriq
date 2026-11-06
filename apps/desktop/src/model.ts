import type { Diagnostic } from "./api.js";

export function badgeLabel(status: "success" | "failed" | "idle"): string {
  if (status === "success") return "success";
  if (status === "failed") return "failed";
  return "idle";
}

export type JumpPlan =
  | { kind: "switch"; path: string; diag: Diagnostic }
  | { kind: "same"; path: string; diag: Diagnostic };

/** Pure planner for cross-file diagnostic jumps (pendingJump). */
export function planDiagnosticJump(
  activePath: string,
  files: { path: string }[],
  diag: Diagnostic,
): JumpPlan {
  const target = files.find((item) => item.path === diag.file);
  if (target && target.path !== activePath) {
    return { kind: "switch", path: target.path, diag };
  }
  return { kind: "same", path: activePath, diag };
}
