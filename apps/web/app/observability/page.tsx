import { api } from "../../lib/api";

export const dynamic = "force-dynamic";

export default async function ObservabilityPage() {
  const data = await api.getObservability();

  return (
    <main className="page">
      <header className="page-header">
        <h1>Observability</h1>
        <p className="muted">
          System health, integration status, and configuration overview.
        </p>
      </header>

      <section className="card">
        <h2>Services</h2>
        <div className="status-grid">
          {data.services.map((svc) => (
            <div key={svc.service} className="status-item">
              <div className="status-row">
                <span className="status-label">{svc.service}</span>
                <span
                  className={`status-badge ${svc.status === "ok" ? "status-ok" : "status-error"}`}
                >
                  {svc.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Integrations</h2>
        <div className="status-grid">
          {Object.entries(data.integrations).map(([name, status]) => (
            <div key={name} className="status-item">
              <div className="status-row">
                <span className="status-label">{name}</span>
                <span
                  className={`status-badge ${status === "ok" ? "status-ok" : "status-warning"}`}
                >
                  {status === "ok" ? "configured" : status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Configuration</h2>
        <div className="kv-grid">
          <div>
            <dt>Auto Execute</dt>
            <dd>{data.config.auto_execute ? "Enabled" : "Disabled"}</dd>
          </div>
          <div>
            <dt>GitHub Real Mode</dt>
            <dd>{data.config.github_real_mode ? "Enabled" : "Disabled"}</dd>
          </div>
          <div>
            <dt>Jira Watcher</dt>
            <dd>
              {data.watchers.jira_watcher.enabled
                ? `Enabled (${data.watchers.jira_watcher.interval}s)`
                : "Disabled"}
            </dd>
          </div>
        </div>
      </section>

      <footer className="observability-footer">
        <span className="muted">
          Last updated: {new Date(data.timestamp).toLocaleString()}
        </span>
      </footer>
    </main>
  );
}
