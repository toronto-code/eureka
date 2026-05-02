"use client";

import Link from "next/link";

/** Visible shortcuts while inspecting a run (demo flows stay long on one page). */
export function OrchestrationQuickNav() {
  function scrollToFlow() {
    document.getElementById("agent-flow")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="flex" style={{ gap: 10, flexWrap: "wrap" }}>
      <Link href="/tasks" className="btn">
        View tasks
      </Link>
      <button type="button" className="btn" onClick={scrollToFlow}>
        View flow
      </button>
    </div>
  );
}
