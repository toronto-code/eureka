import { proxy } from "@/app/api/proxy";

export async function GET() {
  return proxy("/settings/credentials/github-pat");
}

export async function POST(req: Request) {
  const setup = req.headers.get("x-mycelium-setup-token");
  const jsonBody = await req.json();
  return proxy("/settings/credentials/github-pat", {
    method: "POST",
    jsonBody,
    headers: setup ? { "X-Mycelium-Setup-Token": setup } : {},
  });
}

export async function DELETE(req: Request) {
  const setup = req.headers.get("x-mycelium-setup-token");
  return proxy("/settings/credentials/github-pat", {
    method: "DELETE",
    headers: setup ? { "X-Mycelium-Setup-Token": setup } : {},
  });
}
