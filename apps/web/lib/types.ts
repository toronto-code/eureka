// Shared TypeScript types mirroring the FastAPI response shapes.

export type RiskLevel = "READ_ONLY" | "LOW_RISK_WRITE" | "HIGH_RISK_WRITE";
export type ApprovalStatus =
  | "NOT_REQUIRED"
  | "REQUIRED"
  | "APPROVED"
  | "REJECTED";

export interface IntegrationStatus {
  openai: boolean;
  jira: boolean;
  github: boolean;
  database: boolean;
  bot_jira_user: string | null;
  auto_execute_enabled: boolean;
  github_real_mode: boolean;
  jira_watcher_enabled: boolean;
}

export interface ExecutedAction {
  id: string;
  task_id: string | null;
  agent_run_id: string | null;
  integration: "github" | "jira";
  action_type: string;
  status: string;
  dry_run: boolean;
  summary: string;
  target_url: string | null;
  error_message: string | null;
  created_at: string;
}

export interface ExecutionResultDto {
  executed: boolean;
  dry_run: boolean;
  branch: string | null;
  base_branch: string | null;
  pr_url: string | null;
  pr_number: number | null;
  jira_comment_url: string | null;
  jira_transition: string | null;
  file_changes: Array<{
    path: string;
    operation?: string;
    description?: string;
    commit_sha?: string | null;
    html_url?: string | null;
    dry_run?: boolean;
    safety_blocked?: boolean;
  }>;
  errors: string[];
  skipped_reason: string | null;
}

export interface WatcherRunResult {
  picked_up: number;
  ran: number;
  skipped: number;
  details: Array<Record<string, unknown>>;
}

export interface TaskSummary {
  id: string;
  external_id: string | null;
  source: string;
  project_key: string | null;
  title: string;
  description: string | null;
  status: string;
  assignee: string | null;
  reporter: string | null;
  labels: string[];
  priority: string | null;
  risk_level: RiskLevel | null;
  approval_status: ApprovalStatus;
  created_at: string;
  updated_at: string;
}

export interface AgentRun {
  id: string;
  orchestrator_run_id: string | null;
  parent_agent_run_id: string | null;
  spawned_by_agent_run_id: string | null;
  task_id: string | null;
  agent_type: string;
  agent_name: string;
  input_summary: string | null;
  output_summary: string | null;
  status: string;
  model: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  structured_output_json: Record<string, unknown>;
  project_data_subset_json: Record<string, unknown>;
  full_prompt: string | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  actor: string;
  actor_type: string;
  task_id: string | null;
  agent_run_id: string | null;
  action_type: string;
  risk_level: RiskLevel;
  approval_status: ApprovalStatus;
  input_summary: string | null;
  output_summary: string | null;
  sources_used: string[];
  created_at: string;
}

export interface ApprovalRecord {
  id: string;
  task_id: string | null;
  agent_run_id: string | null;
  action_type: string;
  risk_level: RiskLevel;
  status: ApprovalStatus;
  reason: string | null;
  approver: string | null;
  decided_at: string | null;
  decision_notes: string | null;
  created_at: string;
}

export interface OrchestratorOutput {
  orchestrator_summary: string;
  task_understanding: {
    task_id: string | null;
    plain_english_goal: string;
    technical_goal: string;
    known_constraints: string[];
    missing_information: string[];
  };
  agents_spawned: Array<{
    agent_type: string;
    agent_name: string;
    reason: string;
    input_summary: string;
    agent_run_id: string | null;
  }>;
  merged_findings: {
    jira_summary: string;
    code_context: string;
    doc_context: string;
    transcript_context: string;
    previous_run_context: string;
  };
  implementation_plan: Array<{
    step: number;
    description: string;
    requires_approval: boolean;
    risk_level: RiskLevel;
  }>;
  risk_classification: {
    overall_risk: RiskLevel;
    reasoning: string;
    approval_required: boolean;
    blocked_actions: string[];
  };
  recommended_next_action: {
    action_type: string;
    description: string;
    requires_human_approval: boolean;
    draft_output: string;
  };
  audit_log_entry: {
    agents_spawned: string[];
    sources_used: string[];
    decisions: string[];
    approval_status: ApprovalStatus;
  };
  execution?: ExecutionResultDto;
}

export interface WorkerOutput {
  agent_type: string;
  agent_name: string;
  status: string;
  summary: string;
  structured_output: Record<string, unknown>;
  risk_level: RiskLevel | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  model: string;
  full_prompt: string | null;
}

export interface OrchestratorRunDetail {
  run: AgentRun;
  children: AgentRun[];
  audit_logs: AuditLog[];
}

export interface TaskDetailResponse {
  task: TaskSummary;
  runs: AgentRun[];
  approvals: ApprovalRecord[];
  audit_logs: AuditLog[];
}

export interface DocumentSummary {
  id: string;
  source_type: string;
  source_id: string | null;
  title: string;
  project_key: string | null;
  related_task_id: string | null;
  chunk_count: number;
  created_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  content: string;
  chunks: Array<{
    id: string;
    chunk_index: number;
    content: string;
    token_count: number | null;
  }>;
}

export interface AgentGraphNode {
  id: string;
  type: "orchestrator" | "worker";
  label: string;
  status: string;
  agent_type: string;
  summary: string;
}

export interface AgentGraphEdge {
  from: string;
  to: string;
  label: string;
}

export interface AgentGraph {
  nodes: AgentGraphNode[];
  edges: AgentGraphEdge[];
}

export interface ProjectDataPreview {
  user_goal: string | null;
  current_task: Record<string, unknown> | null;
  jira_tasks: Array<Record<string, unknown>>;
  docs: Array<Record<string, unknown>>;
  transcripts: Array<Record<string, unknown>>;
  github_repositories: Array<Record<string, unknown>>;
  code_files: Array<Record<string, unknown>>;
  previous_agent_runs: Array<Record<string, unknown>>;
  constraints: string[];
  available_tools: string[];
}

export interface ApprovalDecisionPayload {
  approver?: string;
  notes?: string;
}
