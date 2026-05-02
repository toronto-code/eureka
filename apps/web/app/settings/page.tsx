import { GitHubBotSetup } from "@/components/GitHubBotSetup";
import { GitHubPatStorage } from "@/components/GitHubPatStorage";
import { RepoBootstrapCard } from "@/components/RepoBootstrapCard";
import { api } from "@/lib/api";
import type { IntegrationDiagnostic } from "@/lib/types";

export const dynamic = "force-dynamic";

type StatusKind = "operational" | "not_configured" | "error";

const STATUS_LABEL: Record<StatusKind, string> = {
  operational: "operational",
  not_configured: "not configured",
  error: "error",
};

const STATUS_BADGE: Record<StatusKind, string> = {
  operational: "badge-green",
  not_configured: "badge-amber",
  error: "badge-red",
};

function StatusPill({ status }: { status: StatusKind }) {
  return (
    <span className={`badge ${STATUS_BADGE[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

function IntegrationRow({
  name,
  description,
  diag,
}: {
  name: string;
  description: string;
  diag: IntegrationDiagnostic | undefined;
}) {
  const status: StatusKind = diag?.status ?? "not_configured";
  const missing = diag?.missing ?? [];
  const detail = diag?.detail ?? null;
  const lastChecked = diag?.last_checked_at;

  return (
    <div className="row" style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div className="flex" style={{ justifyContent: "space-between", gap: 12 }}>
        <div className="flex-col" style={{ gap: 4, minWidth: 0 }}>
          <div className="flex" style={{ gap: 8, alignItems: "center" }}>
            <strong>{name}</strong>
            <StatusPill status={status} />
          </div>
          <div className="faint" style={{ fontSize: 12 }}>
            {description}
          </div>
        </div>
        {lastChecked ? (
          <div className="faint" style={{ fontSize: 11, whiteSpace: "nowrap" }}>
            checked {new Date(lastChecked).toLocaleTimeString()}
          </div>
        ) : null}
      </div>

      {detail ? (
        <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
          {detail}
        </div>
      ) : null}

      {missing.length > 0 ? (
        <div style={{ marginTop: 8 }}>
          <div className="section-title" style={{ marginBottom: 4 }}>
            Required to enable
          </div>
          <div className="flex" style={{ gap: 6, flexWrap: "wrap" }}>
            {missing.map((m) => (
              <code key={m}>{m}</code>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default async function SettingsPage() {
  const [status, projects] = await Promise.all([api.integrations(), api.listProjects()]);
  const d = status.diagnostics ?? {};

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Settings</h2>
          <p>
            Agents pull their live context from these integrations. Each row
            shows whether the connection is currently operational and — if not
            — what is missing. Secrets are loaded from <code>.env</code> (or
            encrypted in Postgres for the GitHub PAT) and never appear in API
            responses or page HTML.
          </p>
        </div>
      </header>

      <div className="card">
        <h3>Integration status</h3>
        <div className="list-card" style={{ marginTop: 8 }}>
          <IntegrationRow
            name="GitHub"
            description="Commits, pull requests, issues, and repo metadata."
            diag={d.github}
          />
          <IntegrationRow
            name="Jira"
            description="Tickets, statuses, assignees, and comments."
            diag={d.jira}
          />
          <IntegrationRow
            name="Slack"
            description="Public channel messages, files, and user directory."
            diag={d.slack}
          />
          <IntegrationRow
            name="OpenAI"
            description="Model provider for orchestrator and worker agents."
            diag={d.openai}
          />
          <IntegrationRow
            name="Database"
            description="Postgres + pgvector for long-term memory and embeddings."
            diag={d.database}
          />
        </div>
      </div>

      <GitHubPatStorage
        storageEnabled={status.github_pat_storage_enabled}
        savedInDatabase={status.github_pat_saved_in_database}
        secretHint={status.github_pat_hint}
      />

      <RepoBootstrapCard hasProjects={projects.length > 0} />

      <GitHubBotSetup githubConfigured={status.github} />

      <div className="card">
        <h3>Autonomous execution</h3>
        <dl className="kv">
          <dt>Bot Jira user</dt>
          <dd>
            {status.bot_jira_user ? (
              <code>{status.bot_jira_user}</code>
            ) : (
              <span className="muted">not set</span>
            )}{" "}
            <span className="muted">
              Set <code>MYCELIUM_BOT_JIRA_USER</code>. Tasks assigned to this
              user are auto-executed end-to-end.
            </span>
          </dd>
          <dt>Auto-execute</dt>
          <dd>
            <span
              className={`badge ${status.auto_execute_enabled ? "badge-green" : "badge-amber"}`}
            >
              {status.auto_execute_enabled ? "enabled" : "disabled"}
            </span>{" "}
            <span className="muted">
              Kill-switch: <code>MYCELIUM_AUTO_EXECUTE=false</code>.
            </span>
          </dd>
          <dt>GitHub real mode</dt>
          <dd>
            <span
              className={`badge ${status.github_real_mode ? "badge-green" : "badge-amber"}`}
            >
              {status.github_real_mode ? "live" : "dry-run"}
            </span>{" "}
            <span className="muted">
              Requires <code>GITHUB_TOKEN</code> + <code>GITHUB_OWNER</code> +{" "}
              <code>GITHUB_REPO</code> + <code>MYCELIUM_ALLOW_REAL_GITHUB=true</code>.
            </span>
          </dd>
          <dt>Jira watcher</dt>
          <dd>
            <span
              className={`badge ${status.jira_watcher_enabled ? "badge-green" : "badge-amber"}`}
            >
              {status.jira_watcher_enabled ? "polling" : "off"}
            </span>{" "}
            <span className="muted">
              Enable with <code>JIRA_WATCHER_ENABLED=true</code>. Interval via{" "}
              <code>JIRA_WATCHER_INTERVAL_SECONDS</code>.
            </span>
          </dd>
        </dl>
      </div>

      <div className="card">
        <h3>Permission model</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Mycelium ships with three roles. Wire them into auth when ready.
        </p>
        <ul>
          <li>
            <strong>admin</strong> — manage integrations, approve any action.
          </li>
          <li>
            <strong>reviewer</strong> — approve or reject agent-recommended writes.
          </li>
          <li>
            <strong>agent</strong> — execute approved actions only.
          </li>
        </ul>
      </div>
    </div>
  );
}
