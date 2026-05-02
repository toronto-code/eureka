"use client";

import { useElapsedSeconds } from "@/lib/useElapsedSeconds";

interface Props {
  open: boolean;
  title: string;
  hint?: string;
}

/** Full-viewport blocking overlay for long HTTP requests (LLM / orchestration). */
export function BusyOverlay({ open, title, hint }: Props) {
  const elapsed = useElapsedSeconds(open);

  if (!open) return null;

  return (
    <div
      className="busy-overlay"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={title}
    >
      <div className="busy-overlay-card">
        <div className="spinner" aria-hidden />
        <div className="busy-overlay-title">{title}</div>
        {hint ? <p className="busy-overlay-hint muted">{hint}</p> : null}
        <div className="busy-overlay-elapsed faint">
          {elapsed}s elapsed — still working…
        </div>
      </div>
    </div>
  );
}
