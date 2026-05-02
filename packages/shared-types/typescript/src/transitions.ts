import type { AgentTaskStatus } from "./agent.js";

/** Single source of truth for AgentTask lifecycle transitions. */
export const VALID_AGENT_TASK_TRANSITIONS: Record<AgentTaskStatus, AgentTaskStatus[]> = {
  queued: ["running", "cancelled"],
  running: ["succeeded", "failed"],
  failed: ["retried", "cancelled"],
  retried: ["succeeded", "cancelled"],
  succeeded: [],
  cancelled: [],
};

export function isValidAgentTaskTransition(
  current: AgentTaskStatus,
  next: AgentTaskStatus,
): boolean {
  return VALID_AGENT_TASK_TRANSITIONS[current]?.includes(next) ?? false;
}
