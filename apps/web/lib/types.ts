// Shared TypeScript types mirroring the FastAPI response shapes.

export type RiskLevel = "READ_ONLY" | "LOW_RISK_WRITE" | "HIGH_RISK_WRITE";
export type ApprovalStatus =
  | "NOT_REQUIRED"
  | "REQUIRED"
  | "APPROVED"
  | "REJECTED";

export interface IntegrationDiagnostic {
  ok: boolean;
  status: "operational" | "not_configured" | "error";
  missing: string[];
  detail: string | null;
  last_checked_at: string | null;
}

export interface IntegrationStatus {
  openai: boolean;
  jira: boolean;
  github: boolean;
  slack: boolean;
  database: boolean;
  bot_jira_user: string | null;
  auto_execute_enabled: boolean;
  github_real_mode: boolean;
  jira_watcher_enabled: boolean;
  github_pat_storage_enabled: boolean;
  github_pat_saved_in_database: boolean;
  github_pat_hint: string | null;
  diagnostics: Record<string, IntegrationDiagnostic>;
}

export interface IncomingSourceSummary {
  ok: boolean;
  configured: boolean;
  item_count: number;
  reason: string | null;
}

export interface IncomingGitHubRepo {
  name: string;
  language: string | null;
  owner: string;
  description: string;
}

export interface IncomingGitHubCommit {
  repo: string;
  message: string;
  author: string | null;
  date: string | null;
}

export interface IncomingGitHubPR {
  repo: string;
  number: number;
  title: string;
  state: string;
  merged: boolean;
  author: string | null;
}

export interface IncomingGitHubIssue {
  repo: string;
  number: number;
  title: string;
  state: string;
  author: string | null;
  assignee: string | null;
}

export interface IncomingSlackMessage {
  channel: string;
  user: string;
  userId?: string;
  userEmail?: string | null;
  text: string;
  ts: string;
  thread_ts?: string | null;
  files?: Array<{
    id: string;
    name: string;
    mimetype: string;
    url_private?: string;
  }>;
}

export interface IncomingJiraIssue {
  key: string;
  summary: string | null;
  status: string | null;
  assignee: string;
  reporter: string | null;
  priority: string | null;
  type: string | null;
  updated: string | null;
}

export interface IncomingObserverEvent {
  type: string;
  source: string | null;
  actor: string | null;
  object: string | null;
  timestamp: string | null;
}

export interface IncomingOverview {
  fetched_at: string;
  github: {
    repos: IncomingGitHubRepo[];
    commits: IncomingGitHubCommit[];
    prs: IncomingGitHubPR[];
    issues: IncomingGitHubIssue[];
  };
  slack: {
    messages: IncomingSlackMessage[];
    user_map: Record<string, { name: string; email?: string | null }>;
  };
  jira: { issues: IncomingJiraIssue[] };
  observer: { events: IncomingObserverEvent[] };
  summary: Record<string, IncomingSourceSummary>;
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


// ---------------------------------------------------------------------------
// OL (new orchestrator) types
// ---------------------------------------------------------------------------

export type OLRoute =
  | "inquiry"
  | "simple_code"
  | "complex_code"
  | "planning"
  | "blocked"
  | "needs_human_review";

export type OLRiskLevel = "low" | "medium" | "high";
export type OLOrigin =
  | "manual"
  | "jira_webhook"
  | "jira_polling"
  | "github_webhook"
  | "github_polling"
  | "api";

export interface ProjectSummary {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  primary_language: string | null;
  jira_project_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface RetrievalPlanDto {
  queries: string[];
  source_types: string[];
  file_paths: string[];
  repo_ids: string[];
  jira_ticket_ids: string[];
  max_chunks: number;
  recency_bias: boolean;
}

export interface WorkerDirectiveDto {
  worker: string;
  purpose: string;
  input_requirements: {
    needs_retrieved_chunks: boolean;
    source_types: string[];
    file_paths: string[];
    repo_ids: string[];
    jira_ticket_ids: string[];
  };
  expected_output_schema: string;
  priority: "low" | "medium" | "high";
}

export interface LaneStep {
  at: string;
  label: string;
  detail: string | null;
  ok: boolean;
}

export interface LaneResultDto {
  lane: string;
  status: "pending" | "running" | "completed" | "blocked" | "error";
  summary: string;
  details: string | null;
  pr_url: string | null;
  jira_comment_url: string | null;
  blocked_reason: string | null;
  citations: Array<Record<string, unknown>>;
  steps: LaneStep[];
  extra: Record<string, unknown>;
}

export interface OrchestratorRunRecord {
  id: string;
  project_id: string;
  origin: OLOrigin | string;
  origin_reference: string | null;
  user_request: string;
  route: OLRoute | null;
  confidence: number | null;
  reasoning_summary: string | null;
  risk_level: OLRiskLevel | null;
  retrieval_plan: RetrievalPlanDto | Record<string, unknown>;
  worker_directives: WorkerDirectiveDto[];
  retrieved_chunk_ids: string[];
  lane_used: string | null;
  lane_status: string | null;
  lane_result: LaneResultDto | Record<string, unknown>;
  pr_url: string | null;
  jira_comment_url: string | null;
  blocked_reason: string | null;
  status: string;
  errors: Array<Record<string, unknown>>;
  run_metadata: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RetrievedChunkDto {
  id: string;
  source_type: string;
  source_id: string | null;
  repo_id: string | null;
  jira_ticket_id: string | null;
  file_path: string | null;
  language: string | null;
  start_line: number | null;
  end_line: number | null;
  branch: string | null;
  commit_sha: string | null;
  chunk_text: string;
  score: number;
  semantic_score: number;
  keyword_score: number;
  recency_score: number;
  chunk_metadata: Record<string, unknown>;
}

export interface OLRunDetail {
  run: OrchestratorRunRecord;
  retrieved_chunks: RetrievedChunkDto[];
}

export interface OLRunRequest {
  user_request: string;
  origin?: OLOrigin;
  origin_reference?: string | null;
  jira_ticket_key?: string | null;
  jira_ticket_id?: string | null;
  repo_id?: string | null;
  acceptance_criteria?: string[];
  extra_hints?: Record<string, unknown>;
}

export interface OLSearchRequest {
  text?: string;
  source_types?: string[];
  file_paths?: string[];
  repo_ids?: string[];
  jira_ticket_ids?: string[];
  max_chunks?: number;
  recency_bias?: boolean;
}

export interface OLSearchResponse {
  project_id: string;
  chunks: RetrievedChunkDto[];
  backend: string;
}

export interface SyncResultDto {
  source: string;
  events_ingested: number;
  repos_checked: number;
  skipped: string[];
  errors: string[];
}

// ---------------------------------------------------------------------------
// Observability types
// ---------------------------------------------------------------------------

export interface ObservabilityResponse {
  timestamp: string;
  services: {
    service: string;
    status: string;
  }[];
  integrations: {
    [key: string]: string;
  };
  watchers: {
    jira_watcher: {
      enabled: boolean;
      interval: number;
    };
  };
  config: {
    auto_execute: boolean;
    github_real_mode: boolean;
  };
}
