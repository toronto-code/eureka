"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BusyOverlay } from "@/components/BusyOverlay";

export function TaskRunButton({ taskId }: { taskId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch(`/api/tasks/${taskId}/run-agent`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Run failed (${res.status})`);
      const json = (await res.json()) as { orchestrator_run_id?: string };
      const runId = json.orchestrator_run_id;
      if (runId) {
        router.push(`/orchestration?run=${runId}`);
      }
      router.refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <BusyOverlay
        open={pending}
        title="Running orchestrator"
        hint="Planning and worker agents run on the server. Large models can take several minutes."
      />
      <div className="flex">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void handleClick()}
          disabled={pending}
        >
          {pending ? "Running…" : "Run orchestrator"}
        </button>
        {error ? <span className="badge badge-red">{error}</span> : null}
      </div>
    </>
  );
}
