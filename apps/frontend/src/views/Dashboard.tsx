import { useEffect, useState } from "react";
import { api, type AgentSummary, type IntegrationSync } from "../api";
import { GraphView } from "../components/GraphView";
import type { GraphSnapshot } from "@mycelium/shared-types";

export function Dashboard() {
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [syncs, setSyncs] = useState<IntegrationSync[]>([]);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [g, s, a] = await Promise.all([
          api.graph({ limit: 100, depth: 2 }),
          api.integrations(),
          api.agents(),
        ]);
        if (cancelled) return;
        setGraph(g);
        setSyncs(s);
        setAgents(a);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }
    load();
    const t = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="dashboard">
      <header className="page-header">
        <h2>Dashboard</h2>
        {error && <span className="error">{error}</span>}
      </header>

      <section className="card graph-card">
        <h3>Knowledge graph</h3>
        <GraphView snapshot={graph} />
      </section>

      <section className="card">
        <h3>Integration sync status</h3>
        <table>
          <thead>
            <tr>
              <th>Connector</th>
              <th>Status</th>
              <th>Last sync</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {syncs.length === 0 && (
              <tr><td colSpan={4} className="muted">No integrations configured.</td></tr>
            )}
            {syncs.map((s) => (
              <tr key={s.connector}>
                <td>{s.connector}</td>
                <td className={s.status === "ok" ? "ok" : "err"}>{s.status}</td>
                <td>{s.last_sync_at ?? "—"}</td>
                <td className="muted">{s.error_message ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Recent agent activity</h3>
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Owner</th>
              <th>Status</th>
              <th>Capabilities</th>
            </tr>
          </thead>
          <tbody>
            {agents.length === 0 && (
              <tr><td colSpan={4} className="muted">No agents yet.</td></tr>
            )}
            {agents.map((a) => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td>{a.owner_user_id}</td>
                <td>{a.status}</td>
                <td className="muted">{a.capabilities.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
