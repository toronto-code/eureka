import { GitHubBotSetup } from "@/components/GitHubBotSetup";
import { GitHubPatStorage } from "@/components/GitHubPatStorage";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span className={`badge ${ok ? "badge-green" : "badge-amber"}`}>
      {ok ? "configured" : "not configured"}
    </span>
  );
}

export default async function SettingsPage() {
  const status = await api.integrations();

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Settings</h2>
          <p>
            Prefer environment variables for production. Optionally save a GitHub PAT through this UI —
            it is encrypted at rest (see below). Secrets never appear in API responses or page HTML.
          </p>
        </div>
      </header>

      <div className="card">
        <h3>Integration status</h3>
        <dl className="kv">
          <dt>OpenAI (GPT-4o)</dt>
          <dd>
            <StatusBadge ok={status.openai} />{" "}
            <span className="muted">
              Set <code>OPENAI_API_KEY</code> in <code>.env</code>.
            </span>
          </dd>
          <dt>Jira</dt>
          <dd>
            <StatusBadge ok={status.jira} />{" "}
            <span className="muted">
              Set <code>JIRA_BASE_URL</code>, <code>JIRA_EMAIL</code>,{" "}
              <code>JIRA_API_TOKEN</code> to enable real issue fetching.
            </span>
          </dd>
          <dt>GitHub</dt>
          <dd>
            <StatusBadge ok={status.github} />{" "}
            <span className="muted">
              Set <code>GITHUB_OWNER</code> / <code>GITHUB_REPO</code> (and optionally{" "}
              <code>GITHUB_TOKEN</code> or save an encrypted PAT below).
            </span>
          </dd>
          <dt>Database</dt>
          <dd>
            <span
              className={`badge ${status.database ? "badge-green" : "badge-red"}`}
            >
              {status.database ? "connected" : "down"}
            </span>{" "}
            <span className="muted">
              Postgres + pgvector. Configured via <code>POSTGRES_DSN</code>.
            </span>
          </dd>
        </dl>
      </div>

      <GitHubPatStorage
        storageEnabled={status.github_pat_storage_enabled}
        savedInDatabase={status.github_pat_saved_in_database}
        secretHint={status.github_pat_hint}
      />

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

      <div className="card">
        <h3>Working-session transcripts</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Mycelium <strong>does not</strong> monitor your screen. Working-session
          transcripts must be uploaded explicitly via the Ingestion page.
        </p>
      </div>
    </div>
  );
}
