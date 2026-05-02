import type { AgentTaskSummary } from "../api";

/** One-line description of what the task is doing or did (for activity feed). */
export function formatActivitySummary(task: AgentTaskSummary): string {
  const { status, agent_type, result } = task;
  if (status === "queued") return "Queued — waiting for agent-runtime";
  if (status === "running") return "Running…";
  if (status === "pending_approval") return "Pending approval — human decision needed";
  if (status === "failed") return task.error ? `Failed: ${truncate(task.error, 80)}` : "Failed";
  if (status === "cancelled") return "Cancelled";

  if (!result || typeof result !== "object") {
    return status === "succeeded" ? "Completed" : "—";
  }

  const r = result as Record<string, unknown>;

  if (agent_type === "project_orchestrator") {
    if (Array.isArray(r.delegations)) {
      const dels = r.delegations as { skill?: string; role?: string }[];
      const parts = dels
        .map((d) => (d.skill ? `${d.role ?? "?"}:${d.skill}` : null))
        .filter(Boolean) as string[];
      if (parts.length > 0) {
        return `Team run: ${parts.slice(0, 5).join(" · ")}${parts.length > 5 ? " …" : ""}`;
      }
    }
    if (typeof r.summary === "string" && r.summary.length > 0) {
      return truncate(r.summary, 140);
    }
  }

  if (typeof r.summary === "string" && r.summary.length > 0) {
    return truncate(r.summary, 140);
  }
  if (typeof r.response === "string" && r.response.length > 0) {
    return truncate(r.response, 140);
  }

  return status === "succeeded" ? "Completed" : "—";
}

function truncate(s: string, n: number): string {
  const t = s.trim();
  if (t.length <= n) return t;
  return `${t.slice(0, n)}…`;
}
