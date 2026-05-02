import { OrchestrationRunLink } from "@/components/OrchestrationRunLink";
import { RiskBadge } from "@/components/RiskBadge";
import { StatusDot } from "@/components/StatusDot";
import type { AgentRun, RiskLevel } from "@/lib/types";

function elapsed(run: AgentRun): string {
  if (!run.started_at || !run.completed_at) return "—";
  const start = new Date(run.started_at).getTime();
  const end = new Date(run.completed_at).getTime();
  const ms = end - start;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function AgentRunCard({ run }: { run: AgentRun }) {
  const risk =
    (run.structured_output_json?.["risk_level"] as RiskLevel | undefined) ??
    null;
  const flowRunId =
    run.agent_type === "orchestrator"
      ? run.id
      : (run.orchestrator_run_id ?? run.id);
  return (
    <div className="row">
      <div className="flex-col" style={{ flex: 1, gap: 4 }}>
        <div className="flex" style={{ gap: 10 }}>
          <StatusDot status={run.status} />
          <strong>{run.agent_name}</strong>
          <span className="badge badge-neutral">{run.agent_type}</span>
          <RiskBadge risk={risk} />
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {run.output_summary || run.input_summary || "No summary"}
        </div>
        <div className="faint" style={{ fontSize: 11 }}>
          model {run.model} · runtime {elapsed(run)} · {new Date(run.created_at).toLocaleString()}
        </div>
      </div>
      <OrchestrationRunLink runId={flowRunId} className="btn">
        View flow
      </OrchestrationRunLink>
    </div>
  );
}
