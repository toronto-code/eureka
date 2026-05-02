import { proxy } from "@/app/api/proxy";

export async function POST(
  _req: Request,
  { params }: { params: { id: string } },
) {
  return proxy(`/tasks/${params.id}/run-agent`, { method: "POST" });
}
