import Link from "next/link";
import { notFound } from "next/navigation";

import { AgentOutputViewer } from "@/components/AgentOutputViewer";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { AuditLogTimeline } from "@/components/AuditLogTimeline";
import { ExecutionPanel } from "@/components/ExecutionPanel";
import { OrchestrationFlow } from "@/components/OrchestrationFlow";
import { OrchestratorOverview } from "@/components/OrchestratorOverview";
import { RiskBadge } from "@/components/RiskBadge";
import { TaskBrief } from "@/components/TaskBrief";
import { TaskRunButton } from "@/components/TaskRunButton";
import { api } from "@/lib/api";
import type { OrchestratorOutput } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TaskDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [detail, executions] = await Promise.all([
    api.getTask(params.id),
    api.listTaskExecutions(params.id),
  ]);
  if (!detail.task) {
    notFound();
  }
  const { task, runs, approvals, audit_logs } = detail;
  const orchestratorRuns = runs.filter((r) => r.agent_type === "orchestrator");
  const latestOrchestrator = orchestratorRuns[0] ?? null;
  const orchestratorOutput =
    (latestOrchestrator?.structured_output_json as unknown as
      | OrchestratorOutput
      | undefined) ?? null;
  const workers = latestOrchestrator
    ? runs.filter(
        (r) =>
          r.agent_type !== "orchestrator" &&
          r.orchestrator_run_id === latestOrchestrator.id,
      )
    : [];
  const pendingApproval =
    approvals.find((a) => a.status === "REQUIRED") ?? null;

  return (
    <div>
      <header className="page-header">
        <div>
          <Link href="/tasks" className="muted" style={{ fontSize: 12 }}>
            ← Back to tasks
          </Link>
          <h2 style={{ marginTop: 6 }}>{task.title}</h2>
          <p className="muted">
            {task.external_id ?? task.id.slice(0, 8)} · {task.status} ·{" "}
            {task.assignee ?? "unassigned"}
          </p>
        </div>
        <TaskRunButton taskId={task.id} />
      </header>

      <div className="grid-2">
        <div className="card">
          <h3>Jira ticket</h3>
          <p style={{ marginTop: 0 }}>{task.description ?? "No description."}</p>
          <dl className="kv">
            <dt>Status</dt>
            <dd>{task.status}</dd>
            <dt>Assignee</dt>
            <dd>{task.assignee ?? "—"}</dd>
            <dt>Reporter</dt>
            <dd>{task.reporter ?? "—"}</dd>
            <dt>Priority</dt>
            <dd>{task.priority ?? "—"}</dd>
            <dt>Labels</dt>
            <dd>{task.labels.join(", ") || "—"}</dd>
            <dt>Risk</dt>
            <dd>
              <RiskBadge risk={task.risk_level} />
            </dd>
            <dt>Approval</dt>
            <dd>{task.approval_status}</dd>
          </dl>
        </div>
        <ApprovalPanel
          taskId={task.id}
          approval={pendingApproval}
          blockedActions={
            (orchestratorOutput?.risk_classification.blocked_actions as string[]) ??
            []
          }
          recommendedAction={
            orchestratorOutput?.recommended_next_action ?? null
          }
          riskLevel={orchestratorOutput?.risk_classification.overall_risk ?? null}
        />
      </div>

      {latestOrchestrator && orchestratorOutput ? (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <h3>Implementation plan</h3>
            {orchestratorOutput.implementation_plan.length === 0 ? (
              <p className="muted">No plan recorded.</p>
            ) : (
              <ol>
                {orchestratorOutput.implementation_plan.map((step) => (
                  <li key={step.step} style={{ marginBottom: 6 }}>
                    <span>{step.description}</span>{" "}
                    <RiskBadge risk={step.risk_level} />
                    {step.requires_approval ? (
                      <span className="badge badge-amber" style={{ marginLeft: 6 }}>
                        approval required
                      </span>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </div>
          <TaskBrief output={orchestratorOutput} />
          <div className="card">
            <h3>Recommended next action</h3>
            <p>
              <strong>{orchestratorOutput.recommended_next_action.action_type}</strong>{" "}
              · {orchestratorOutput.recommended_next_action.description}
            </p>
            {orchestratorOutput.recommended_next_action.draft_output ? (
              <pre className="scroll-box">
                {orchestratorOutput.recommended_next_action.draft_output}
              </pre>
            ) : null}
          </div>
          <OrchestratorOverview
            run={latestOrchestrator}
            output={orchestratorOutput}
            workerCount={workers.length}
          />
          <ExecutionPanel
            execution={orchestratorOutput.execution ?? null}
            actions={executions}
            jiraKey={task.external_id}
          />
          <OrchestrationFlow
            orchestrator={latestOrchestrator}
            workers={workers}
            auditLogs={audit_logs}
          />
          <AgentOutputViewer
            payload={
              orchestratorOutput as unknown as Record<string, unknown>
            }
            title="Raw orchestrator output"
          />
        </>
      ) : (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>No orchestrator runs yet</h3>
          <p className="muted">
            Click <strong>Run orchestrator</strong> above to spawn worker agents
            and produce a task brief.
          </p>
        </div>
      )}

      <AuditLogTimeline logs={audit_logs} />
    </div>
  );
}
