"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

export function TaskRunButton({ taskId }: { taskId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleClick() {
    setError(null);
    startTransition(async () => {
      try {
        const res = await fetch(`/api/tasks/${taskId}/run-agent`, {
          method: "POST",
        });
        if (!res.ok) throw new Error(`Run failed (${res.status})`);
        router.refresh();
      } catch (err) {
        setError(String(err));
      }
    });
  }

  return (
    <div className="flex">
      <button
        className="btn btn-primary"
        onClick={handleClick}
        disabled={pending}
      >
        {pending ? "Running…" : "Run orchestrator"}
      </button>
      {error ? <span className="badge badge-red">{error}</span> : null}
    </div>
  );
}
