import { NextRequest } from "next/server";

import { proxy } from "../../proxy";

export async function POST(req: NextRequest) {
  const url = new URL(req.url);
  const projectId = url.searchParams.get("project_id");
  const source = url.searchParams.get("source") ?? "all";
  if (!projectId) {
    return new Response(
      JSON.stringify({ error: "missing_project_id" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }
  return proxy(`/projects/${projectId}/sync/${source}`, { method: "POST" });
}
