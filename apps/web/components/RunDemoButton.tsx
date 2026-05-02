"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BusyOverlay } from "@/components/BusyOverlay";

export function RunDemoButton({
  redirectTo = "/orchestration",
  label = "Run demo orchestration",
}: {
  redirectTo?: string;
  label?: string;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleClick() {
    setError(null);
    setPending(true);
    try {
      const res = await fetch("/api/agents/demo", { method: "POST" });
      if (!res.ok) throw new Error(`Demo failed (${res.status})`);
      const json = (await res.json()) as { orchestrator_run_id?: string };
      const id = json.orchestrator_run_id;
      if (id && redirectTo === "/orchestration") {
        router.push(`/orchestration?run=${id}`);
      } else {
        router.refresh();
        router.push(redirectTo);
      }
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
        title="Running orchestration"
        hint="The orchestrator calls the LLM and may spawn worker agents. This often takes one to several minutes — the UI will update when the run finishes."
      />
      <div className="flex" style={{ gap: 10 }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void handleClick()}
          disabled={pending}
        >
          {pending ? "Running…" : label}
        </button>
        {error ? <span className="badge badge-red">{error}</span> : null}
      </div>
    </>
  );
}
