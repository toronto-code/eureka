import { RiskBadge } from "@/components/RiskBadge";
import { StatusDot } from "@/components/StatusDot";
import type { AgentRun, OrchestratorOutput } from "@/lib/types";

interface Props {
  run: AgentRun;
  output: OrchestratorOutput;
  workerCount: number;
}

function durationLabel(run: AgentRun): string {
  if (!run.started_at || !run.completed_at) return "—";
  const ms =
    new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function OrchestratorOverview({ run, output, workerCount }: Props) {
  return (
    <div className="card">
      <h3>Orchestrator overview</h3>
      <dl className="kv">
        <dt>Run id</dt>
        <dd className="code" style={{ display: "inline-block", padding: "2px 8px" }}>
          {run.id}
        </dd>
        <dt>Task</dt>
        <dd>
          {output.task_understanding.task_id ?? "—"} ·{" "}
          <span className="muted">{output.task_understanding.plain_english_goal}</span>
        </dd>
        <dt>Status</dt>
        <dd>
          <StatusDot status={run.status} /> {run.status}
        </dd>
        <dt>Model</dt>
        <dd>{run.model}</dd>
        <dt>Started</dt>
        <dd>{run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</dd>
        <dt>Completed</dt>
        <dd>
          {run.completed_at ? new Date(run.completed_at).toLocaleString() : "—"}
        </dd>
        <dt>Duration</dt>
        <dd>{durationLabel(run)}</dd>
        <dt>Agents spawned</dt>
        <dd>{workerCount}</dd>
        <dt>Recommended action</dt>
        <dd className="muted">{output.recommended_next_action.description}</dd>
        <dt>Overall risk</dt>
        <dd>
          <RiskBadge risk={output.risk_classification.overall_risk} />
        </dd>
      </dl>
    </div>
  );
}
