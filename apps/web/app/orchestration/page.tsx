import Link from "next/link";

import { AgentOutputViewer } from "@/components/AgentOutputViewer";
import { AuditLogTimeline } from "@/components/AuditLogTimeline";
import { ExecutionPanel } from "@/components/ExecutionPanel";
import { OrchestrationFlow } from "@/components/OrchestrationFlow";
import { OrchestrationQuickNav } from "@/components/OrchestrationQuickNav";
import { OrchestrationRunLink } from "@/components/OrchestrationRunLink";
import { OrchestratorOverview } from "@/components/OrchestratorOverview";
import { RiskBadge } from "@/components/RiskBadge";
import { RunDemoButton } from "@/components/RunDemoButton";
import { StatusDot } from "@/components/StatusDot";
import { TaskBrief } from "@/components/TaskBrief";
import { WatcherButton } from "@/components/WatcherButton";
import { api } from "@/lib/api";
import type { OrchestratorOutput } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OrchestrationPage({
  searchParams,
}: {
  searchParams: { run?: string };
}) {
  const [runs, integrations] = await Promise.all([
    api.listRuns(50),
    api.integrations(),
  ]);
  const orchestratorRuns = runs.filter((r) => r.agent_type === "orchestrator");
  const selectedId = searchParams.run ?? orchestratorRuns[0]?.id ?? null;

  if (!selectedId) {
    return (
      <div>
      <header className="page-header">
        <div>
          <h2>Orchestration</h2>
          <p>
            Watch the orchestrator coordinate worker agents in real time. Run
            the demo to populate a flow.
          </p>
        </div>
        <div className="flex" style={{ gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <OrchestrationQuickNav />
          <RunDemoButton />
        </div>
      </header>
      <div className="card">
        <h3>Jira watcher</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          {integrations.bot_jira_user
            ? `Polling Jira for tasks assigned to "${integrations.bot_jira_user}". Auto-execute is ${integrations.auto_execute_enabled ? "ON" : "OFF"}.`
            : "Set MYCELIUM_BOT_JIRA_USER in .env to let Mycelium auto-execute tasks assigned to it."}
        </p>
        <WatcherButton />
      </div>
      <div className="card">
        <p className="muted">
          No orchestrator runs yet. Click <strong>Run demo orchestration</strong>{" "}
          above.
        </p>
      </div>
    </div>
  );
  }

  const detail = await api.getRun(selectedId);
  if (!detail.run) {
    return (
      <div>
        <header className="page-header">
          <div>
            <h2>Orchestration</h2>
            <p className="muted">Run not found.</p>
          </div>
          <div className="flex" style={{ gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
            <OrchestrationQuickNav />
            <RunDemoButton />
          </div>
        </header>
      </div>
    );
  }

  const { run, children, audit_logs } = detail;
  const orchestratorOutput =
    (run.structured_output_json as unknown as OrchestratorOutput | undefined) ??
    null;

  const decisionLog =
    orchestratorOutput?.audit_log_entry?.decisions ?? [];

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Orchestration</h2>
          <p>
            Inspect the orchestrator agent, the worker agents it spawned, and
            the full multi-agent execution flow.
          </p>
        </div>
        <div className="flex" style={{ gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <OrchestrationQuickNav />
          <RunDemoButton />
        </div>
      </header>

      <div className="card">
        <h3>Recent orchestrator runs</h3>
        <div className="list-card">
          {orchestratorRuns.slice(0, 8).map((r) => {
            const active = r.id === selectedId;
            return (
              <OrchestrationRunLink
                runId={r.id}
                key={r.id}
                className="row"
                style={
                  active
                    ? { borderColor: "var(--accent)", textDecoration: "none" }
                    : { textDecoration: "none" }
                }
              >
                <div className="flex" style={{ gap: 8 }}>
                  <StatusDot status={r.status} />
                  <strong>{r.agent_name}</strong>
                  <span className="badge badge-neutral">
                    {r.id.slice(0, 8)}
                  </span>
                  <RiskBadge
                    risk={
                      (orchestratorOutput &&
                        r.id === selectedId &&
                        orchestratorOutput.risk_classification.overall_risk) ||
                      null
                    }
                  />
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {new Date(r.created_at).toLocaleString()}
                </div>
              </OrchestrationRunLink>
            );
          })}
        </div>
      </div>

      {orchestratorOutput ? (
        <>
          <OrchestratorOverview
            run={run}
            output={orchestratorOutput}
            workerCount={children.length}
          />
          <ExecutionPanel
            execution={orchestratorOutput.execution ?? null}
            actions={[]}
            jiraKey={
              (orchestratorOutput.task_understanding as { task_id?: string } | undefined)
                ?.task_id ?? null
            }
          />
          <OrchestrationFlow
            orchestrator={run}
            workers={children}
            auditLogs={audit_logs}
          />

          <div className="card">
            <h3>Spawned agents</h3>
            <div className="list-card">
              {children.length === 0 ? (
                <p className="muted">No worker agents.</p>
              ) : (
                children.map((c) => (
                  <div className="row" key={c.id}>
                    <div className="flex-col" style={{ gap: 4 }}>
                      <div className="flex">
                        <StatusDot status={c.status} />
                        <strong>{c.agent_name}</strong>
                        <span className="badge badge-neutral">
                          {c.agent_type}
                        </span>
                        <span className="badge badge-neutral">{c.model}</span>
                      </div>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {c.input_summary}
                      </div>
                      <div className="faint" style={{ fontSize: 11 }}>
                        {c.output_summary}
                      </div>
                      {c.error_message ? (
                        <div className="badge badge-red">
                          error: {c.error_message}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <TaskBrief output={orchestratorOutput} taskDbId={run.task_id} />

          <div className="card">
            <h3>Orchestrator decision log</h3>
            {decisionLog.length === 0 ? (
              <p className="muted">No explicit decisions recorded.</p>
            ) : (
              <ul>
                {decisionLog.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h3>Human approval visibility</h3>
            {orchestratorOutput.execution?.executed ||
            orchestratorOutput.execution?.dry_run ? (
              <p className="muted">
                Jira assignment to the Mycelium bot counted as the human
                approval for this run, so the orchestrator executed the plan
                autonomously. Humans review the resulting PR instead of
                gating each action.
              </p>
            ) : orchestratorOutput.risk_classification.approval_required ? (
              <div className="flex-col">
                <div className="flex">
                  <span className="badge badge-amber">approval required</span>
                  <RiskBadge
                    risk={orchestratorOutput.risk_classification.overall_risk}
                  />
                </div>
                <p>
                  <strong>Reason:</strong>{" "}
                  <span className="muted">
                    {orchestratorOutput.risk_classification.reasoning}
                  </span>
                </p>
                <div>
                  <div className="section-title">Blocked actions</div>
                  {orchestratorOutput.risk_classification.blocked_actions.length ===
                  0 ? (
                    <p className="muted">None recorded.</p>
                  ) : (
                    <ul>
                      {orchestratorOutput.risk_classification.blocked_actions.map(
                        (b) => (
                          <li key={b}>{b}</li>
                        ),
                      )}
                    </ul>
                  )}
                </div>
                {run.task_id ? (
                  <Link
                    href={`/tasks/${run.task_id}`}
                    className="btn btn-primary"
                  >
                    Approve / reject on task page
                  </Link>
                ) : null}
              </div>
            ) : (
              <p className="muted">
                No approval required for this run — all actions are read-only or
                drafts.
              </p>
            )}
          </div>

          <AuditLogTimeline logs={audit_logs} />

          <AgentOutputViewer
            payload={orchestratorOutput as unknown as Record<string, unknown>}
            title="Raw orchestrator output"
          />
        </>
      ) : (
        <div className="card">
          <p className="muted">Run has no structured output.</p>
        </div>
      )}
    </div>
  );
}
