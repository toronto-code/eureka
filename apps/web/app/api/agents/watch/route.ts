import { proxy } from "@/app/api/proxy";

export async function POST() {
  return proxy("/agents/watch", { method: "POST" });
}
