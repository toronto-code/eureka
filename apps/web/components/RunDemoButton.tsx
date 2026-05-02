"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function RunDemoButton({
  redirectTo = "/orchestration",
  label = "Run demo orchestration",
}: {
  redirectTo?: string;
  label?: string;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleClick() {
    setError(null);
    startTransition(async () => {
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
      }
    });
  }

  return (
    <div className="flex" style={{ gap: 10 }}>
      <button
        className="btn btn-primary"
        onClick={handleClick}
        disabled={pending}
      >
        {pending ? "Running…" : label}
      </button>
      {error ? <span className="badge badge-red">{error}</span> : null}
    </div>
  );
}
