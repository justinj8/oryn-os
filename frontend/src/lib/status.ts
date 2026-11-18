export type RunStatus = "running" | "waiting_approval" | "completed" | "failed" | "cancelled" | "escalated";

export const STATUS: Record<RunStatus, { label: string; color: string; text: string }> = {
  running: { label: "Running", color: "bg-flight", text: "text-flight" },
  waiting_approval: { label: "Needs approval", color: "bg-hold", text: "text-hold" },
  completed: { label: "Completed", color: "bg-clear", text: "text-clear" },
  escalated: { label: "Escalated", color: "bg-divert", text: "text-divert" },
  failed: { label: "Failed", color: "bg-fail", text: "text-fail" },
  cancelled: { label: "Cancelled", color: "bg-idle", text: "text-idle" },
};

export function statusOf(s: string) {
  return STATUS[s as RunStatus] ?? STATUS.cancelled;
}
