import Link from "next/link";

import { AgentRunCard } from "@/components/AgentRunCard";
import { RiskBadge } from "@/components/RiskBadge";
import { RunDemoButton } from "@/components/RunDemoButton";
import { WatcherButton } from "@/components/WatcherButton";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [tasks, runs, integrations] = await Promise.all([
    api.listTasks(),
    api.listRuns(8),
    api.integrations(),
  ]);

  const orchestratorRuns = runs.filter((r) => r.agent_type === "orchestrator");
  const pendingApprovals = tasks.filter(
    (t) => t.approval_status === "REQUIRED",
  );
  const botAssignedTasks = integrations.bot_jira_user
    ? tasks.filter(
        (t) =>
          (t.assignee ?? "").toLowerCase() ===
          integrations.bot_jira_user!.toLowerCase(),
      )
    : [];

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p>
            Mycelium watches your Jira board and uses GPT-4o agents to safely
            help complete tasks. Run a demo orchestration to see the full flow.
          </p>
        </div>
        <RunDemoButton />
      </header>

      <div className="grid-3">
        <div className="card">
          <h3>Tasks</h3>
          <div style={{ fontSize: 28, fontWeight: 600 }}>{tasks.length}</div>
          <div className="muted">{pendingApprovals.length} awaiting approval</div>
          <Link href="/tasks" className="btn" style={{ marginTop: 12 }}>
            View tasks
          </Link>
        </div>
        <div className="card">
          <h3>Recent agent runs</h3>
          <div style={{ fontSize: 28, fontWeight: 600 }}>{runs.length}</div>
          <div className="muted">{orchestratorRuns.length} orchestrator runs</div>
          <Link href="/orchestration" className="btn" style={{ marginTop: 12 }}>
            Open orchestration
          </Link>
        </div>
        <div className="card">
          <h3>Integrations</h3>
          <ul style={{ paddingLeft: 18, margin: 0 }}>
            <li>OpenAI: {integrations.openai ? "configured" : "not configured"}</li>
            <li>Jira: {integrations.jira ? "configured" : "fake-seed mode"}</li>
            <li>
              GitHub:{" "}
              {integrations.github
                ? integrations.github_real_mode
                  ? "configured · live writes"
                  : "configured · dry-run"
                : "fake-seed mode"}
            </li>
            <li>DB: {integrations.database ? "ok" : "down"}</li>
          </ul>
        </div>
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>Autonomous execution</h3>
        {integrations.bot_jira_user ? (
          <p className="muted" style={{ marginTop: 0 }}>
            Mycelium auto-executes tasks assigned to{" "}
            <code>{integrations.bot_jira_user}</code>. {botAssignedTasks.length}{" "}
            bot-assigned task{botAssignedTasks.length === 1 ? "" : "s"} in Jira.{" "}
            Auto-execute is{" "}
            <strong>
              {integrations.auto_execute_enabled ? "enabled" : "disabled"}
            </strong>
            .
          </p>
        ) : (
          <p className="muted" style={{ marginTop: 0 }}>
            Set <code>MYCELIUM_BOT_JIRA_USER</code> in <code>.env</code> to let
            Mycelium autonomously execute Jira tasks assigned to it.
          </p>
        )}
        <WatcherButton />
        {botAssignedTasks.length > 0 ? (
          <div className="list-card" style={{ marginTop: 12 }}>
            {botAssignedTasks.map((t) => (
              <div className="row" key={t.id}>
                <div className="flex-col" style={{ gap: 4 }}>
                  <div className="flex">
                    <strong>{t.title}</strong>
                    <span className="badge badge-neutral">
                      {t.external_id ?? t.id.slice(0, 8)}
                    </span>
                    <span className="badge badge-purple">bot</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {t.status} · {t.approval_status}
                  </div>
                </div>
                <Link href={`/tasks/${t.id}`} className="btn">
                  Open
                </Link>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>Recent agent runs</h3>
        <div className="list-card">
          {runs.length === 0 ? (
            <p className="muted">
              No agent runs yet. Click <strong>Run demo orchestration</strong> to
              generate one.
            </p>
          ) : (
            runs.map((r) => <AgentRunCard run={r} key={r.id} />)
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>Pending approvals</h3>
        {pendingApprovals.length === 0 ? (
          <p className="muted">Nothing awaiting human approval right now.</p>
        ) : (
          <div className="list-card">
            {pendingApprovals.map((task) => (
              <div className="row" key={task.id}>
                <div className="flex-col" style={{ gap: 4 }}>
                  <div className="flex">
                    <strong>{task.title}</strong>
                    <span className="badge badge-neutral">
                      {task.external_id ?? task.id.slice(0, 8)}
                    </span>
                    <RiskBadge risk={task.risk_level} />
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {task.assignee ?? "unassigned"} · {task.status}
                  </div>
                </div>
                <Link href={`/tasks/${task.id}`} className="btn">
                  Review
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
