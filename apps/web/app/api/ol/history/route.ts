import { NextRequest } from "next/server";

import { proxy } from "../../proxy";

function getProjectId(req: NextRequest): string | null {
  const url = new URL(req.url);
  return url.searchParams.get("project_id");
}

export async function GET(req: NextRequest) {
  const projectId = getProjectId(req);
  if (!projectId) {
    return new Response(JSON.stringify({ error: "missing_project_id" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  return proxy(`/projects/${projectId}/orchestrator/chat-history`, { method: "GET" });
}

export async function POST(req: NextRequest) {
  const projectId = getProjectId(req);
  if (!projectId) {
    return new Response(JSON.stringify({ error: "missing_project_id" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  const body = await req.json().catch(() => ({}));
  return proxy(`/projects/${projectId}/orchestrator/chat-history`, {
    method: "POST",
    jsonBody: body,
  });
}
