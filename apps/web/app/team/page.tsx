"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { authFetch } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import { TeamWebGraph } from "@/components/TeamWebGraph";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Profile {
  id: string;
  display_name: string | null;
  github_login: string | null;
  jira_email: string | null;
  created_at: string;
}
interface ActivityRow {
  user_id: string | null;
  label: string;
  kind: "agent_action" | "observer_event";
  display_name: string | null;
  at: string;
  detail: string | null;
  status: string | null;
}

export default function TeamPage() {
  const { user } = useAuth();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [web, setWeb] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [profilesRes, activityRes, webRes] = await Promise.all([
        supabase.from("profiles").select("*").order("created_at", { ascending: true }),
        supabase.from("unified_activity").select("*").limit(40),
        authFetch(`${API_URL}/dashboard/web`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
      ]);
      if (profilesRes.error) throw profilesRes.error;
      if (activityRes.error) throw activityRes.error;
      setProfiles(profilesRes.data || []);
      setActivity((activityRes.data as ActivityRow[]) || []);
      setWeb(webRes || {});
      setLastRefresh(Date.now());
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // Tick every 30s so the 20-minute filter re-evaluates and stale rows roll off
  // even when no new actions arrive.
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    void load();
    let es: EventSource | null = null;
    let closed = false;
    try {
      es = new EventSource(`${API_URL}/chat/actions/stream`);
      es.onmessage = (e) => {
        if (closed) return;
        try {
          const evt = JSON.parse(e.data);
          if (evt && evt.tool) void load();
        } catch {}
      };
      es.onerror = () => {
        if (es && !closed) {
          closed = true;
          es.close();
        }
      };
    } catch {
      // ignore — SSE is optional, page still works without it
    }
    return () => {
      closed = true;
      try { es?.close(); } catch {}
    };
  }, []);

  // 20-minute sliding window for the dashboard
  const RECENT_WINDOW_MS = 20 * 60 * 1000;
  const cutoff = now - RECENT_WINDOW_MS;
  const recentActivity = activity.filter((a) => {
    if (!a.at) return false;
    const t = new Date(a.at).getTime();
    return Number.isFinite(t) && t >= cutoff;
  });

  const userActionMap = new Map<string, Map<string, number>>();
  for (const a of recentActivity) {
    if (!a.user_id) continue;
    const inner = userActionMap.get(a.user_id) || new Map<string, number>();
    inner.set(a.label, (inner.get(a.label) || 0) + 1);
    userActionMap.set(a.user_id, inner);
  }

  return (
    <div className="page">
      <header className="page-header" style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
        <div>
          <h2>Team Web</h2>
          <p>Real users, real activity, real integrations — direct from Supabase.</p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12 }}>
          <span style={{ color: "var(--text-muted)" }}>
            Updated: {new Date(lastRefresh).toLocaleTimeString()}
          </span>
          <button onClick={load} disabled={loading} className="btn">
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && (
        <div className="card" style={{ borderLeft: "3px solid var(--red)", padding: 14, marginBottom: 12, color: "var(--red)" }}>
          {error}
        </div>
      )}

      <div className="card" style={{ padding: 18, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 12 }}>Network</h3>
        <TeamWebGraph
          profiles={profiles}
          activity={recentActivity}
          currentUserId={user?.id}
          web={web}
        />
      </div>

      <div className="card" style={{ padding: 18, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 12 }}>
          Members ({profiles.length} {profiles.length === 1 ? "user" : "users"})
        </h3>
        {profiles.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No users yet.</p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
              alignItems: "stretch",
            }}
          >
            {profiles.map((p) => {
              const isYou = p.id === user?.id;
              const actions = userActionMap.get(p.id);
              const total = actions ? Array.from(actions.values()).reduce((a, b) => a + b, 0) : 0;
              return (
                <div
                  key={p.id}
                  className="card"
                  style={{
                    padding: 14,
                    minHeight: 140,
                    display: "flex",
                    flexDirection: "column",
                    borderColor: isYou ? "var(--accent)" : "var(--border)",
                    background: isYou ? "var(--accent-soft)" : "var(--bg-elev)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>
                      {p.display_name || "(no name)"}
                      {isYou && <span style={{ color: "var(--accent)", fontSize: 11, marginLeft: 6 }}>(you)</span>}
                    </div>
                    <span
                      style={{
                        fontSize: 11,
                        background: total > 0 ? "var(--accent-soft)" : "var(--neutral-100)",
                        color: total > 0 ? "var(--accent)" : "var(--text-muted)",
                        padding: "2px 8px",
                        borderRadius: "var(--radius-pill)",
                      }}
                    >
                      {total} actions
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {p.github_login && <span>github: {p.github_login} · </span>}
                    {p.jira_email && <span>jira: {p.jira_email} · </span>}
                    joined {new Date(p.created_at).toLocaleDateString()}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: "auto", paddingTop: 8 }}>
                    {actions && actions.size > 0
                      ? Array.from(actions.entries()).slice(0, 6).map(([tool, n]) => (
                          <span
                            key={tool}
                            style={{
                              fontSize: 10,
                              background: "var(--bg)",
                              color: "var(--text)",
                              padding: "2px 7px",
                              borderRadius: 4,
                              border: "1px solid var(--border)",
                            }}
                          >
                            {tool} ×{n}
                          </span>
                        ))
                      : <span style={{ fontSize: 10, color: "var(--text-faint)" }}>no recent actions</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 18 }}>
        <h3 style={{ marginBottom: 12 }}>
          Recent activity ({recentActivity.length})
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 8 }}>
            last 20 minutes
          </span>
        </h3>
        {recentActivity.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            No activity in the last 20 minutes. Use the orchestrator to generate some.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {recentActivity.slice(0, 30).map((a, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "100px 160px 130px 1fr 80px",
                  gap: 12,
                  padding: "8px 10px",
                  borderRadius: 4,
                  fontSize: 12,
                  background: i % 2 === 0 ? "var(--neutral-100)" : "transparent",
                }}
              >
                <span style={{ color: "var(--text-muted)" }}>
                  {a.at ? new Date(a.at).toLocaleTimeString() : "—"}
                </span>
                <span style={{ color: "var(--text)" }}>{a.display_name || "system"}</span>
                <span style={{ color: a.kind === "agent_action" ? "var(--accent)" : "var(--green)", fontFamily: "var(--mono)", fontSize: 11 }}>
                  {a.kind}
                </span>
                <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                  <b>{a.label}</b>
                  {a.detail && <span style={{ color: "var(--text-muted)" }}> — {a.detail.slice(0, 80)}</span>}
                </span>
                <span
                  style={{
                    color: a.status === "error" || a.status === "blocked" ? "var(--red)" : a.status === "ok" ? "var(--green)" : "var(--text-muted)",
                    fontSize: 11,
                  }}
                >
                  {a.status || ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
