import type { AgentTaskSummary } from "../api";

export function formatAgentReply(task: AgentTaskSummary): string {
  if (task.status === "failed") {
    return task.error ?? "Agent task failed.";
  }
  if (task.status === "cancelled") {
    return "Task was cancelled.";
  }
  const res = task.result;
  if (
    res &&
    typeof res === "object" &&
    "summary" in res &&
    typeof (res as { summary: unknown }).summary === "string"
  ) {
    return (res as { summary: string }).summary;
  }
  return res !== undefined ? JSON.stringify(res) : "(no body)";
}
