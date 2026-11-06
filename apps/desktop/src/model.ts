export function badgeLabel(status: "success" | "failed" | "idle"): string {
  if (status === "success") return "success";
  if (status === "failed") return "failed";
  return "idle";
}
