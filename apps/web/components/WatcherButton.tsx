"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import type { WatcherRunResult } from "@/lib/types";

export function WatcherButton() {
  const router = useRouter();
  const [result, setResult] = useState<WatcherRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleClick() {
    setError(null);
    setResult(null);
    startTransition(async () => {
      try {
        const res = await fetch("/api/agents/watch", { method: "POST" });
        if (!res.ok) throw new Error(`Watcher failed (${res.status})`);
        setResult((await res.json()) as WatcherRunResult);
        router.refresh();
      } catch (err) {
        setError(String(err));
      }
    });
  }

  return (
    <div className="flex-col" style={{ gap: 8 }}>
      <div className="flex">
        <button className="btn" onClick={handleClick} disabled={pending}>
          {pending ? "Polling Jira…" : "Poll Jira now"}
        </button>
        {error ? <span className="badge badge-red">{error}</span> : null}
        {result ? (
          <span className="muted" style={{ fontSize: 12 }}>
            picked up {result.picked_up} · ran {result.ran} · skipped{" "}
            {result.skipped}
          </span>
        ) : null}
      </div>
      {result && result.details.length > 0 ? (
        <pre className="scroll-box" style={{ maxHeight: 140 }}>
          {JSON.stringify(result.details, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
