// Server-side API client shared by every page.
// Uses BACKEND_URL on the server, falls back to NEXT_PUBLIC_BACKEND_URL in the
// browser. Never embed secrets here; this file is bundled to the client.

import type {
  AgentGraph,
  AgentRun,
  ApprovalDecisionPayload,
  AuditLog,
  DocumentDetail,
  DocumentSummary,
  ExecutedAction,
  IntegrationStatus,
  OLRunDetail,
  OLRunRequest,
  OLSearchRequest,
  OLSearchResponse,
  OrchestratorOutput,
  OrchestratorRunDetail,
  OrchestratorRunRecord,
  ProjectDataPreview,
  ProjectSummary,
  SyncResultDto,
  TaskDetailResponse,
  TaskSummary,
  WatcherRunResult,
  WorkerOutput,
} from "./types";

const SERVER_BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const PUBLIC_BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

function backendUrl(): string {
  return typeof window === "undefined" ? SERVER_BACKEND_URL : PUBLIC_BACKEND_URL;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  fallback?: T,
): Promise<T> {
  try {
    const res = await fetch(`${backendUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) {
      throw new Error(`API ${path} responded ${res.status}`);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (fallback !== undefined) {
      return fallback;
    }
    throw err;
  }
}

export const api = {
  health: () => request<{ status: string }>("/health", {}, { status: "down" }),
  integrations: () =>
    request<IntegrationStatus>(
      "/settings/integrations",
      {},
      {
        openai: false,
        jira: false,
        github: false,
        database: false,
        bot_jira_user: null,
        auto_execute_enabled: false,
        github_real_mode: false,
        jira_watcher_enabled: false,
      },
    ),
  projectDataPreview: () =>
    request<ProjectDataPreview>("/settings/project_data", {}, {
      user_goal: null,
      jira_tasks: [],
      docs: [],
      transcripts: [],
      github_repositories: [],
      code_files: [],
      previous_agent_runs: [],
      constraints: [],
      available_tools: [],
    } as unknown as ProjectDataPreview),

  agentTypes: () =>
    request<{
      agent_types: { agent_type: string; agent_name: string; system_prompt: string; default_model: string }[];
    }>("/agents/types", {}, { agent_types: [] }),

  runDemo: (): Promise<{
    orchestrator_run_id: string;
    output: OrchestratorOutput;
    spawned_run_ids: Record<string, string>;
  }> => request("/agents/demo", { method: "POST" }),

  runAgent: (payload: {
    agent_type: string;
    project_data: Record<string, unknown>;
    task?: Record<string, unknown> | null;
    reason?: string;
  }) =>
    request<{ agent_run_id: string; output: WorkerOutput }>(
      "/agents/run-worker",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  listRuns: (limit = 50) =>
    request<AgentRun[]>(`/agents/runs?limit=${limit}`, {}, []),
  getRun: (runId: string) =>
    request<OrchestratorRunDetail>(`/agents/runs/${runId}`, {}, {
      run: null as unknown as AgentRun,
      children: [],
      audit_logs: [],
    } as unknown as OrchestratorRunDetail),
  getRunGraph: (runId: string) =>
    request<AgentGraph>(`/agents/runs/${runId}/graph`, {}, {
      nodes: [],
      edges: [],
    }),

  listTasks: () => request<TaskSummary[]>("/tasks", {}, []),
  getTask: (taskId: string) =>
    request<TaskDetailResponse>(`/tasks/${taskId}`, {}, {
      task: null as unknown as TaskSummary,
      runs: [],
      approvals: [],
      audit_logs: [],
    } as unknown as TaskDetailResponse),
  runAgentForTask: (taskId: string) =>
    request<{
      orchestrator_run_id: string;
      output: OrchestratorOutput;
    }>(`/tasks/${taskId}/run-agent`, { method: "POST" }),
  approveTask: (taskId: string, payload: ApprovalDecisionPayload) =>
    request(`/tasks/${taskId}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rejectTask: (taskId: string, payload: ApprovalDecisionPayload) =>
    request(`/tasks/${taskId}/reject`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listDocuments: () =>
    request<DocumentSummary[]>("/ingestion/documents", {}, []),
  getDocument: (id: string) =>
    request<DocumentDetail>(`/ingestion/documents/${id}`, {}, {
      id,
      title: "",
      source_type: "doc",
      content: "",
      chunk_count: 0,
      chunks: [],
    } as unknown as DocumentDetail),

  listExecutions: (limit = 50) =>
    request<ExecutedAction[]>(`/agents/executions?limit=${limit}`, {}, []),
  listTaskExecutions: (taskId: string, limit = 50) =>
    request<ExecutedAction[]>(
      `/agents/executions?task_id=${taskId}&limit=${limit}`,
      {},
      [],
    ),
  runWatcher: () =>
    request<WatcherRunResult>(
      "/agents/watch",
      { method: "POST" },
      { picked_up: 0, ran: 0, skipped: 0, details: [] },
    ),

  // ---- OL orchestrator --------------------------------------------------
  listProjects: () => request<ProjectSummary[]>("/projects", {}, []),
  getProject: (projectId: string) =>
    request<ProjectSummary>(`/projects/${projectId}`),
  runOrchestrator: (projectId: string, payload: OLRunRequest) =>
    request<OLRunDetail>(`/projects/${projectId}/orchestrator/run`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listOrchestratorRuns: (projectId: string, limit = 50) =>
    request<OrchestratorRunRecord[]>(
      `/projects/${projectId}/orchestrator/runs?limit=${limit}`,
      {},
      [],
    ),
  getOrchestratorRun: (runId: string) =>
    request<OLRunDetail>(`/orchestrator/runs/${runId}`),
  searchProject: (projectId: string, payload: OLSearchRequest) =>
    request<OLSearchResponse>(`/projects/${projectId}/search`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  syncGithub: (projectId: string) =>
    request<SyncResultDto>(`/projects/${projectId}/sync/github`, {
      method: "POST",
    }),
  syncJira: (projectId: string) =>
    request<SyncResultDto>(`/projects/${projectId}/sync/jira`, {
      method: "POST",
    }),
};

export type { AuditLog, OrchestratorOutput };
