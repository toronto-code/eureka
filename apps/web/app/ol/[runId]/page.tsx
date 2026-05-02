import Link from "next/link";
import { notFound } from "next/navigation";

import { api } from "../../../lib/api";
import { OLRunDetail } from "../../../components/OLRunDetail";

export const dynamic = "force-dynamic";

export default async function OLRunDetailPage({
  params,
}: {
  params: { runId: string };
}) {
  const detail = await api.getOrchestratorRun(params.runId).catch(() => null);
  if (!detail || !detail.run) {
    notFound();
    return null; // unreachable; keeps TS happy when next/navigation types are missing
  }
  const run = detail.run;
  return (
    <main className="page">
      <Link href="/ol" className="back-link">
        ← back to runs
      </Link>
      <OLRunDetail run={run} chunks={detail.retrieved_chunks} />
    </main>
  );
}
