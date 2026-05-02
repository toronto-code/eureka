import { useEffect, useRef, useState } from "react";
import { authFetch } from "../lib/auth";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Service {
  name: string;
  service?: string;
  image: string;
  status: string;
  state?: string;
  health?: string | null;
  started_at?: string;
  exit_code?: number;
  restart_count: number;
  ports: string[];
}

interface Stat {
  name: string;
  cpu_percent?: number;
  mem_percent?: number;
  mem_used_mb?: number;
  mem_limit_mb?: number;
  net_rx_kb?: number;
  net_tx_kb?: number;
  blk_read_mb?: number;
  blk_write_mb?: number;
  error?: string;
}

interface DockerEvent {
  type: string;
  action: string;
  name?: string;
  service?: string;
  exit_code?: string;
  time?: number;
}


function statusColor(s: Service): string {
  if (s.health === "unhealthy") return "#ef4444";
  if (s.status !== "running") return "#6b7280";
  if (s.health === "starting") return "#f59e0b";
  return "#22c55e";
}

function eventColor(action: string): string {
  if (["die", "kill", "oom", "stop"].some((x) => action.includes(x))) return "#ef4444";
  if (["restart", "unhealthy"].some((x) => action.includes(x))) return "#f59e0b";
  if (["start", "create", "healthy"].some((x) => action.includes(x))) return "#22c55e";
  return "#6b7280";
}

export function Observability() {
  const [services, setServices] = useState<Service[]>([]);
  const [stats, setStats] = useState<Record<string, Stat>>({});
  const [events, setEvents] = useState<DockerEvent[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsBusy, setLogsBusy] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const sseRef = useRef<EventSource | null>(null);

  async function loadServices() {
    try {
      const res = await authFetch(`${API_URL}/observability/docker/services`);
      if (res.ok) setServices(await res.json());
    } catch {}
  }

  async function loadStats() {
    try {
      const res = await authFetch(`${API_URL}/observability/docker/stats`);
      if (res.ok) {
        const data: Stat[] = await res.json();
        const map: Record<string, Stat> = {};
        for (const s of data) map[s.name] = s;
        setStats(map);
      }
    } catch {}
  }

  async function loadLogs(name: string) {
    setLogsBusy(true);
    try {
      const res = await authFetch(`${API_URL}/observability/docker/logs/${name}?lines=80`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.lines || []);
      }
    } catch {
      setLogs(["error fetching logs"]);
    } finally {
      setLogsBusy(false);
    }
  }

  async function refreshAll() {
    await Promise.all([loadServices(), loadStats()]);
    setLastRefresh(Date.now());
  }

  useEffect(() => {
    refreshAll();

    const es = new EventSource(`${API_URL}/observability/docker/stream`);
    es.onmessage = (e) => {
      try {
        const evt: DockerEvent = JSON.parse(e.data);
        setEvents((prev) => [evt, ...prev].slice(0, 60));
      } catch {}
    };
    es.onerror = () => {
      es.close();
    };
    sseRef.current = es;

    return () => {
      sseRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (selected) loadLogs(selected);
  }, [selected]);

  const totalRunning = services.filter((s) => s.status === "running").length;
  const totalUnhealthy = services.filter((s) => s.health === "unhealthy" || (s.status !== "running" && s.exit_code)).length;
  // Per-container CPU% can exceed 100% on multi-CPU hosts. Average instead of sum.
  const cpuValues = Object.values(stats).map((s) => s.cpu_percent || 0).filter((n) => n > 0);
  const avgCpu = cpuValues.length ? cpuValues.reduce((a, b) => a + b, 0) / cpuValues.length : 0;
  const totalMemMb = Object.values(stats).reduce((sum, s) => sum + (s.mem_used_mb || 0), 0);
  const totalMemGb = totalMemMb / 1024;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0a0a0a", color: "#e5e7eb", overflow: "hidden" }}>
      <header style={{ padding: 16, borderBottom: "1px solid #1f2937", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>Observability</h2>
          <p style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
            Docker containers · live stats · events stream · per-container logs
          </p>
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 12, alignItems: "center" }}>
          <Stat label="Running" value={`${totalRunning}/${services.length}`} color={totalUnhealthy ? "#ef4444" : "#22c55e"} />
          <Stat label="Unhealthy" value={String(totalUnhealthy)} color={totalUnhealthy ? "#ef4444" : "#6b7280"} />
          <Stat label="Avg CPU" value={`${avgCpu.toFixed(1)}%`} color="#3b82f6" />
          <Stat label="Mem used" value={totalMemGb >= 1 ? `${totalMemGb.toFixed(2)} GB` : `${totalMemMb.toFixed(0)} MB`} color="#3b82f6" />
          <button
            onClick={refreshAll}
            style={{ marginLeft: 8, padding: "6px 14px", borderRadius: 6, background: "#1f2937", color: "#e5e7eb", border: "1px solid #374151", cursor: "pointer", fontSize: 12 }}
          >
            Refresh
          </button>
        </div>
      </header>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Services grid */}
        <div style={{ flex: 2, overflowY: "auto", padding: 16 }}>
          <h3 style={{ fontSize: 12, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
            Containers ({services.length})
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
            {services.map((s) => {
              const st = stats[s.name];
              return (
                <div
                  key={s.name}
                  onClick={() => setSelected(s.name)}
                  style={{
                    background: selected === s.name ? "#0f172a" : "#0c0c0c",
                    border: `1px solid ${selected === s.name ? "#3b82f6" : "#1f2937"}`,
                    borderRadius: 8,
                    padding: 12,
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{s.service || s.name}</div>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor(s) }} />
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 6 }}>
                    {s.image} · restarts {s.restart_count}
                  </div>
                  <div style={{ fontSize: 10, color: "#9ca3af" }}>
                    {s.status}{s.health ? ` / ${s.health}` : ""}
                  </div>
                  {st && !st.error && (
                    <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 10 }}>
                      <span><b>{st.cpu_percent}%</b> cpu</span>
                      <span><b>{st.mem_percent}%</b> mem</span>
                      <span style={{ color: "#6b7280" }}>{st.mem_used_mb}MB</span>
                    </div>
                  )}
                  {s.ports.length > 0 && (
                    <div style={{ fontSize: 10, color: "#3b82f6", marginTop: 6 }}>{s.ports.join(", ")}</div>
                  )}
                </div>
              );
            })}
            {services.length === 0 && <div style={{ fontSize: 12, color: "#6b7280" }}>No containers visible. Is the API mounted to /var/run/docker.sock?</div>}
          </div>
        </div>

        {/* Right column: logs + events */}
        <aside style={{ flex: 1, borderLeft: "1px solid #1f2937", display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 360 }}>
          <div style={{ flex: 1, overflowY: "auto", padding: 16, borderBottom: "1px solid #1f2937" }}>
            <h3 style={{ fontSize: 12, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
              {selected ? `Logs: ${selected}` : "Select a container for logs"}
            </h3>
            {logsBusy && <div style={{ fontSize: 11, color: "#6b7280" }}>loading…</div>}
            {!logsBusy && selected && (
              <pre style={{ fontSize: 10, color: "#9ca3af", whiteSpace: "pre-wrap", margin: 0, fontFamily: "ui-monospace, monospace" }}>
                {logs.length ? logs.slice(-60).join("\n") : "(no log output)"}
              </pre>
            )}
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
            <h3 style={{ fontSize: 12, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
              Live events ({events.length})
            </h3>
            {events.length === 0 && <div style={{ fontSize: 11, color: "#6b7280" }}>Waiting for docker events…</div>}
            {events.map((e, i) => (
              <div key={i} style={{ borderLeft: `2px solid ${eventColor(e.action)}`, padding: "4px 8px", marginBottom: 4, fontSize: 11 }}>
                <span style={{ color: eventColor(e.action), fontWeight: 600 }}>{e.action}</span>{" "}
                <span style={{ color: "#e5e7eb" }}>{e.name || "?"}</span>
                {e.exit_code && <span style={{ color: "#ef4444" }}> exit={e.exit_code}</span>}
                {e.time && <span style={{ color: "#6b7280", marginLeft: 6 }}>{new Date(e.time * 1000).toLocaleTimeString()}</span>}
              </div>
            ))}
          </div>
        </aside>
      </div>

      <footer style={{ padding: "6px 16px", fontSize: 10, color: "#6b7280", borderTop: "1px solid #1f2937" }}>
        Last refresh: {new Date(lastRefresh).toLocaleTimeString()} · on-demand · live events via SSE
      </footer>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color }}>{value}</div>
    </div>
  );
}
