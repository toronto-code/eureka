export interface AuditEntry {
  id: string;
  agent_id: string;
  task_id?: string | null;
  action: string;
  actor_user_id?: string | null;
  /** ISO 8601 timestamp */
  timestamp: string;
  correlation_id: string;
  parent_correlation_id?: string | null;
  details: Record<string, unknown>;
}
