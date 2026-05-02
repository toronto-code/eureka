export type AgentStatus = "idle" | "busy" | "offline" | "error";

export interface Agent {
  id: string;
  owner_user_id: string;
  capabilities: string[];
  status: AgentStatus;
  /** ISO 8601 timestamp */
  created_at: string;
}

/**
 * Lifecycle states. Transitions are strict — see {@link VALID_AGENT_TASK_TRANSITIONS}.
 *
 *   queued           → running | pending_approval | cancelled
 *   pending_approval → running | cancelled
 *   running          → succeeded | failed
 *   failed           → retried   | cancelled
 *   retried          → succeeded | cancelled
 */
export type AgentTaskStatus =
  | "queued"
  | "pending_approval"
  | "running"
  | "succeeded"
  | "failed"
  | "retried"
  | "cancelled";

export interface AgentTask {
  task_id: string;
  agent_id: string;
  /** Class of agent: "triage" | "onboard" | "code-review" | ... */
  agent_type: string;
  input_data: Record<string, unknown>;

  /** Mandatory. Same rules as MyceliumEvent. */
  correlation_id: string;
  parent_correlation_id?: string | null;

  status: AgentTaskStatus;

  /** ISO 8601 timestamps */
  created_at: string;
  updated_at: string;

  result?: Record<string, unknown> | null;
  error?: string | null;
}
