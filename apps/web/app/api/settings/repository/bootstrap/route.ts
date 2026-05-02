import { NextRequest } from "next/server";

import { proxy } from "@/app/api/proxy";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  return proxy("/settings/repository/bootstrap", {
    method: "POST",
    jsonBody: body,
  });
}
