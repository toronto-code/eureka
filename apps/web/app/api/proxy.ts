// Shared proxy helper for Next.js route handlers that forward to FastAPI.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function proxy(
  path: string,
  init: RequestInit & { jsonBody?: unknown } = {},
): Promise<Response> {
  const { jsonBody, ...rest } = init;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (jsonBody !== undefined) {
    headers["Content-Type"] = "application/json";
    rest.body = JSON.stringify(jsonBody);
  }
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      ...rest,
      headers,
      cache: "no-store",
    });
    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "backend_unreachable", detail: String(err) }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }
}
