import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { api, type AgentSummary, type AgentTaskSummary } from "../api";
import { formatActivitySummary } from "../lib/taskActivity";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

type Row = AgentTaskSummary & { _agent_id: string };

function statusClass(status: string): string {
  if (status === "succeeded") return "ok";
  if (status === "failed" || status === "cancelled") return "err";
  return "muted";
}

function OrchestrationDetail({ result }: { result: Record<string, unknown> }) {
  const dels = result.delegations;
  const team = result.team_outputs;
  return (
    <div className="agent-detail-sections">
      {Array.isArray(dels) && dels.length > 0 && (
        <div>
          <div className="agent-detail-label">Delegation plan</div>
          <ul className="agent-delegation-list">
            {(dels as { role?: string; skill?: string; rationale?: string; sub_prompt?: string }[]).map(
              (d, i) => (
                <li key={i}>
                  <strong>{d.role ?? "?"}</strong>
                  <span className="muted"> · {d.skill ?? "—"}</span>
                  {d.rationale && <div className="agent-detail-rationale">{d.rationale}</div>}
                </li>
              ),
            )}
          </ul>
        </div>
      )}
      {Array.isArray(team) && team.length > 0 && (
        <div>
          <div className="agent-detail-label">Specialist outputs</div>
          <div className="agent-team-grid">
            {(team as { role?: string; skill?: string; result?: unknown }[]).map((t, i) => (
              <div key={i} className="agent-team-card">
                <div className="agent-team-card-head">
                  <span>{t.role ?? "role"}</span>
                  <span className="muted">{t.skill ?? ""}</span>
                </div>
                <pre className="agent-json">{safeJson(t.result)}</pre>
              </div>
            ))}
          </div>
        </div>
      )}
      <details className="agent-raw-details">
        <summary>Full task JSON</summary>
        <pre className="agent-json">{safeJson(result)}</pre>
      </details>
    </div>
  );
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

export function AgentsActivity() {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const agentList = await api.agents();
      setAgents(agentList);

      const tasksNested = await Promise.all(
        agentList.map(async (a) => {
          try {
            const tasks = await api.agentTasks(a.id);
            return tasks.map((t) => ({ ...t, _agent_id: a.id }));
          } catch {
            return [];
          }
        }),
      );

      const merged = tasksNested.flat();
      merged.sort((a, b) => {
        const tb = new Date(b.updated_at).getTime();
        const ta = new Date(a.updated_at).getTime();
        return tb - ta;
      });
      setRows(merged.slice(0, 80));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      if (cancelled) return;
      await load();
    }
    void tick();
    const fast = setInterval(() => {
      void tick();
    }, 2500);
    return () => {
      cancelled = true;
      clearInterval(fast);
    };
  }, [load]);

  const hasActive = useMemo(
    () => rows.some((r) => !TERMINAL.has(r.status)),
    [rows],
  );

  function toggle(taskKey: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(taskKey)) next.delete(taskKey);
      else next.add(taskKey);
      return next;
    });
  }

  return (
    <div className="agents-activity">
      <header className="page-header">
        <h2>Agents</h2>
        <div className="agents-toolbar">
          {hasActive && <span className="agents-live">Live</span>}
          <button type="button" className="btn-ghost" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="card">
        <h3>Registered agents ({agents.length})</h3>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Capabilities</th>
            </tr>
          </thead>
          <tbody>
            {agents.length === 0 && (
              <tr>
                <td colSpan={3} className="muted">
                  No agents yet — open Chat and send a message to create one.
                </td>
              </tr>
            )}
            {agents.map((a) => (
              <tr key={a.id}>
                <td className="mono">{a.id}</td>
                <td>{a.status}</td>
                <td className="muted">{a.capabilities.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Task activity</h3>
        <p className="agents-hint muted">
          Polls the API every few seconds. Expand a row for orchestration steps and specialist outputs.
        </p>
        <table className="agents-task-table">
          <thead>
            <tr>
              <th className="col-status">Status</th>
              <th>Type</th>
              <th>Activity</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  No tasks yet.
                </td>
              </tr>
            )}
            {rows.map((t) => {
              const key = `${t._agent_id}:${t.task_id}`;
              const open = expanded.has(key);
              const res = t.result;
              const showOrch =
                t.agent_type === "project_orchestrator" &&
                res &&
                typeof res === "object" &&
                (Array.isArray((res as Record<string, unknown>).delegations) ||
                  Array.isArray((res as Record<string, unknown>).team_outputs));

              return (
                <Fragment key={key}>
                  <tr
                    className={`agents-task-row ${open ? "agents-task-row-open" : ""}`}
                    onClick={() => toggle(key)}
                    title="Click to expand details"
                  >
                    <td className={statusClass(t.status)}>{t.status}</td>
                    <td className="mono">{t.agent_type}</td>
                    <td>{formatActivitySummary(t)}</td>
                    <td className="muted mono">{t.updated_at}</td>
                  </tr>
                  {open && (
                    <tr className="agents-detail-row">
                      <td colSpan={4}>
                        <div className="agents-detail-panel">
                          <div className="agents-meta">
                            <span>
                              <strong>task</strong>{" "}
                              <code>{t.task_id}</code>
                            </span>
                            <span>
                              <strong>agent</strong> <code>{t._agent_id}</code>
                            </span>
                            <span className="muted">
                              <strong>cid</strong> {t.correlation_id}
                            </span>
                          </div>
                          {t.error && <div className="error">{t.error}</div>}
                          {showOrch && (
                            <OrchestrationDetail result={res as Record<string, unknown>} />
                          )}
                          {!showOrch && res !== undefined && res !== null && (
                            <pre className="agent-json">{safeJson(res)}</pre>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
