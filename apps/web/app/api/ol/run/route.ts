import { NextRequest } from "next/server";

import { proxy } from "../../proxy";

export async function POST(req: NextRequest) {
  const url = new URL(req.url);
  const projectId = url.searchParams.get("project_id");
  if (!projectId) {
    return new Response(
      JSON.stringify({ error: "missing_project_id" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }
  const body = await req.json().catch(() => ({}));
  return proxy(`/projects/${projectId}/orchestrator/run`, {
    method: "POST",
    jsonBody: body,
  });
}
