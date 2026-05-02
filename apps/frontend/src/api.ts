/**
 * API client. The frontend talks to apps/api ONLY — never to a service or
 * database directly.
 */

import type { GraphSnapshot } from "@mycelium/shared-types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} on ${path}`);
  }
  return (await res.json()) as T;
}

export interface IntegrationSync {
  connector: string;
  last_sync_at: string | null;
  status: "ok" | "error";
  error_message: string | null;
  updated_at: string | null;
}

export interface AgentSummary {
  id: string;
  owner_user_id: string;
  capabilities: string[];
  status: string;
  created_at: string;
}

export interface AgentTaskSummary {
  task_id: string;
  agent_id: string;
  agent_type: string;
  status: string;
  correlation_id: string;
  parent_correlation_id: string | null;
  created_at: string;
  updated_at: string;
  result: unknown;
  error: string | null;
}

export const api = {
  health: () => request<{ status: string; service: string; timestamp: string }>("/health"),

  graph: (params: { limit?: number; depth?: number; node_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.depth !== undefined) q.set("depth", String(params.depth));
    if (params.node_id) q.set("node_id", params.node_id);
    return request<GraphSnapshot>(`/graph?${q.toString()}`);
  },

  integrations: () => request<IntegrationSync[]>("/integrations"),

  agents: () => request<AgentSummary[]>("/agents"),

  agentTasks: (agentId: string) =>
    request<AgentTaskSummary[]>(`/agents/${encodeURIComponent(agentId)}/tasks`),

  agentTask: (agentId: string, taskId: string) =>
    request<AgentTaskSummary>(
      `/agents/${encodeURIComponent(agentId)}/tasks/${encodeURIComponent(taskId)}`,
    ),

  observability: () =>
    request<{ timestamp: string; services: { service: string; status: string; details: unknown }[] }>(
      "/observability",
    ),

  chat: (
    prompt: string,
    opts?: {
      agent_id?: string;
      correlation_id?: string;
      /** Default API skill is project_orchestrator; use `chat` for legacy stub */
      agent_type?: string;
      project_data?: Record<string, unknown>;
    },
  ) =>
    request<{
      task_id: string;
      agent_id: string;
      correlation_id: string;
      status: string;
      message: string;
    }>("/chat", {
      method: "POST",
      body: JSON.stringify({ prompt, ...opts }),
    }),
};
