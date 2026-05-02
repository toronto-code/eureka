export type WorkflowStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "completed"
  | "failed";

export interface WorkflowState {
  workflow_id: string;
  name: string;
  status: WorkflowStatus;
  correlation_id: string;
  parent_correlation_id?: string | null;
  steps_completed: string[];
  next_step?: string | null;
  context: Record<string, unknown>;
  /** ISO 8601 timestamps */
  created_at: string;
  updated_at: string;
}
