"use client";

import { useEffect, useRef, useState } from "react";
import { authFetch } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Service {
  name: string;
  service?: string;
  image: string;
  status: string;
  health?: string | null;
  exit_code?: number;
  restart_count: number;
  ports: string[];
}
interface Stat {
  name: string;
  cpu_percent?: number;
  mem_percent?: number;
  mem_used_mb?: number;
  net_rx_kb?: number;
  net_tx_kb?: number;
  error?: string;
}
interface DockerEvent {
  type: string;
  action: string;
  name?: string;
  exit_code?: string;
  time?: number;
}

function statusColor(s: Service): string {
  if (s.health === "unhealthy") return "var(--red)";
  if (s.status !== "running") return "var(--text-faint)";
  if (s.health === "starting") return "var(--amber)";
  return "var(--green)";
}
function eventColor(action: string): string {
  if (["die", "kill", "oom", "stop"].some((x) => action.includes(x))) return "var(--red)";
  if (["restart", "unhealthy"].some((x) => action.includes(x))) return "var(--amber)";
  if (["start", "create", "healthy"].some((x) => action.includes(x))) return "var(--green)";
  return "var(--text-muted)";
}

export default function ObservabilityPage() {
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
      if (res.ok) setLogs((await res.json()).lines || []);
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
    void refreshAll();
    const es = new EventSource(`${API_URL}/observability/docker/stream`);
    es.onmessage = (e) => {
      try {
        const evt: DockerEvent = JSON.parse(e.data);
        setEvents((prev) => [evt, ...prev].slice(0, 60));
      } catch {}
    };
    es.onerror = () => es.close();
    sseRef.current = es;
    return () => sseRef.current?.close();
  }, []);

  useEffect(() => {
    if (selected) void loadLogs(selected);
  }, [selected]);

  const totalRunning = services.filter((s) => s.status === "running").length;
  const totalUnhealthy = services.filter((s) => s.health === "unhealthy" || (s.status !== "running" && s.exit_code)).length;
  const cpuValues = Object.values(stats).map((s) => s.cpu_percent || 0).filter((n) => n > 0);
  const avgCpu = cpuValues.length ? cpuValues.reduce((a, b) => a + b, 0) / cpuValues.length : 0;
  const totalMemMb = Object.values(stats).reduce((sum, s) => sum + (s.mem_used_mb || 0), 0);
  const totalMemGb = totalMemMb / 1024;

  return (
    <div className="page">
      <header className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h2>Observability</h2>
          <p>Live Docker stack — containers, stats, logs, events.</p>
        </div>
        <div style={{ display: "flex", gap: 18, alignItems: "center", fontSize: 12 }}>
          <Stat label="Running" value={`${totalRunning}/${services.length}`} color={totalUnhealthy ? "var(--red)" : "var(--green)"} />
          <Stat label="Unhealthy" value={String(totalUnhealthy)} color={totalUnhealthy ? "var(--red)" : "var(--text-muted)"} />
          <Stat label="Avg CPU" value={`${avgCpu.toFixed(1)}%`} color="var(--accent)" />
          <Stat label="Memory" value={totalMemGb >= 1 ? `${totalMemGb.toFixed(2)} GB` : `${totalMemMb.toFixed(0)} MB`} color="var(--accent)" />
          <button onClick={refreshAll} className="btn">Refresh</button>
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <div className="card" style={{ padding: 18 }}>
          <h3 style={{ marginBottom: 12 }}>Containers ({services.length})</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
            {services.map((s) => {
              const st = stats[s.name];
              return (
                <div
                  key={s.name}
                  onClick={() => setSelected(s.name)}
                  className="card"
                  style={{
                    padding: 12,
                    cursor: "pointer",
                    borderColor: selected === s.name ? "var(--accent)" : "var(--border)",
                    background: selected === s.name ? "var(--accent-soft)" : "var(--bg-elev)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{s.service || s.name}</div>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor(s) }} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>
                    {s.image} · restarts {s.restart_count}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text)" }}>
                    {s.status}{s.health ? ` / ${s.health}` : ""}
                  </div>
                  {st && !st.error && (
                    <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11 }}>
                      <span><b>{st.cpu_percent}%</b> cpu</span>
                      <span><b>{st.mem_percent}%</b> mem</span>
                      <span style={{ color: "var(--text-muted)" }}>{st.mem_used_mb}MB</span>
                    </div>
                  )}
                  {s.ports.length > 0 && (
                    <div style={{ fontSize: 11, color: "var(--accent)", marginTop: 6, fontFamily: "var(--mono)" }}>
                      {s.ports.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
            {services.length === 0 && (
              <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
                No containers visible. Make sure the API is mounted to /var/run/docker.sock.
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ padding: 18, maxHeight: 380, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <h3 style={{ marginBottom: 12 }}>{selected ? `Logs — ${selected}` : "Select a container for logs"}</h3>
            {logsBusy && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>loading…</p>}
            {!logsBusy && selected && (
              <pre
                style={{
                  fontSize: 10,
                  color: "var(--text)",
                  whiteSpace: "pre-wrap",
                  margin: 0,
                  fontFamily: "var(--mono)",
                  overflowY: "auto",
                  flex: 1,
                  background: "var(--neutral-100)",
                  padding: 10,
                  borderRadius: 4,
                }}
              >
                {logs.length ? logs.slice(-60).join("\n") : "(no log output)"}
              </pre>
            )}
          </div>

          <div className="card" style={{ padding: 18 }}>
            <h3 style={{ marginBottom: 12 }}>Live events ({events.length})</h3>
            <div style={{ maxHeight: 280, overflowY: "auto" }}>
              {events.length === 0 && <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Waiting for docker events…</p>}
              {events.map((e, i) => (
                <div key={i} style={{ borderLeft: `2px solid ${eventColor(e.action)}`, padding: "5px 9px", marginBottom: 4, fontSize: 11 }}>
                  <span style={{ color: eventColor(e.action), fontWeight: 600 }}>{e.action}</span>{" "}
                  <span>{e.name || "?"}</span>
                  {e.exit_code && <span style={{ color: "var(--red)" }}> exit={e.exit_code}</span>}
                  {e.time && <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>{new Date(e.time * 1000).toLocaleTimeString()}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <p style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "right", marginTop: 16 }}>
        Last refresh: {new Date(lastRefresh).toLocaleTimeString()} · live events via SSE
      </p>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color }}>{value}</div>
    </div>
  );
}
