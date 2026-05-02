import Link from "next/link";

import { AgentRunCard } from "@/components/AgentRunCard";
import { RiskBadge } from "@/components/RiskBadge";
import { RunDemoButton } from "@/components/RunDemoButton";
import { WatcherButton } from "@/components/WatcherButton";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Inline icons keep the dashboard light (no extra deps) and let us tint via currentColor. */
function InboxIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

function integrationStatus(integrations: Awaited<ReturnType<typeof api.integrations>>) {
  return [
    {
      label: "OpenAI",
      value: integrations.openai ? "configured" : "not configured",
      tone: integrations.openai ? "configured" : "down",
    },
    {
      label: "Jira",
      value: integrations.jira ? "configured" : "fake-seed mode",
      tone: integrations.jira ? "configured" : "fake-seed",
    },
    {
      label: "GitHub",
      value: integrations.github
        ? integrations.github_real_mode
          ? "configured · live writes"
          : "configured · dry-run"
        : "fake-seed mode",
      tone: integrations.github ? "configured" : "fake-seed",
    },
    {
      label: "Database",
      value: integrations.database ? "ok" : "down",
      tone: integrations.database ? "configured" : "down",
    },
  ] as const;
}

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

  const integrationRows = integrationStatus(integrations);

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
          <div className="stat-number">{tasks.length}</div>
          <div className="stat-meta">
            {pendingApprovals.length} awaiting approval
          </div>
          <Link href="/tasks" className="btn" style={{ marginTop: 16 }}>
            View tasks
          </Link>
        </div>
        <div className="card">
          <h3>Recent agent runs</h3>
          <div className="stat-number">{runs.length}</div>
          <div className="stat-meta">
            {orchestratorRuns.length} orchestrator runs
          </div>
          <Link
            href="/orchestration"
            className="btn"
            style={{ marginTop: 16 }}
          >
            Open orchestration
          </Link>
        </div>
        <div className="card">
          <h3>Integrations</h3>
          <ul className="integrations-list">
            {integrationRows.map((row) => (
              <li key={row.label}>
                <span className={`dot-indicator ${row.tone}`} />
                <span className="label">{row.label}</span>
                <span className="value">{row.value}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>Autonomous execution</h3>
        {integrations.bot_jira_user ? (
          <p className="muted" style={{ marginTop: 0 }}>
            Mycelium auto-executes tasks assigned to{" "}
            <span className="code-pill">{integrations.bot_jira_user}</span>.{" "}
            {botAssignedTasks.length} bot-assigned task
            {botAssignedTasks.length === 1 ? "" : "s"} in Jira. Auto-execute is{" "}
            <strong>
              {integrations.auto_execute_enabled ? "enabled" : "disabled"}
            </strong>
            .
          </p>
        ) : (
          <p className="muted" style={{ marginTop: 0 }}>
            Set <span className="code-pill">MYCELIUM_BOT_JIRA_USER</span> in{" "}
            <span className="code-pill">.env</span> to let Mycelium autonomously
            execute Jira tasks assigned to it.
          </p>
        )}
        <div style={{ marginTop: 14 }}>
          <WatcherButton />
        </div>
        {botAssignedTasks.length > 0 ? (
          <div className="list-card" style={{ marginTop: 14 }}>
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
        {runs.length === 0 ? (
          <div className="empty-state">
            <InboxIcon />
            <p>
              No agent runs yet. Click <strong>Run demo orchestration</strong>{" "}
              to generate one.
            </p>
          </div>
        ) : (
          <div className="list-card">
            {runs.map((r) => (
              <AgentRunCard run={r} key={r.id} />
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h3>Pending approvals</h3>
        {pendingApprovals.length === 0 ? (
          <div className="empty-state">
            <CheckCircleIcon />
            <p>Nothing awaiting human approval right now.</p>
          </div>
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
