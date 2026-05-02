import { proxy } from "@/app/api/proxy";

export async function POST(
  req: Request,
  { params }: { params: { id: string } },
) {
  const body = await req.json().catch(() => ({}));
  return proxy(`/tasks/${params.id}/reject`, {
    method: "POST",
    jsonBody: body,
  });
}
