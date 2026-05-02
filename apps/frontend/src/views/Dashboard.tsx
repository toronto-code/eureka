import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { supabase } from "../lib/supabase";
import { authFetch } from "../lib/auth";
import { TeamWebGraph } from "../components/TeamWebGraph";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Profile {
  id: string;
  display_name: string | null;
  github_login: string | null;
  slack_user_id: string | null;
  jira_email: string | null;
  created_at: string;
}

interface ActivityRow {
  kind: "agent_action" | "observer_event";
  at: string;
  display_name: string | null;
  github_login: string | null;
  user_id: string | null;
  label: string;
  detail: string | null;
  status: string | null;
}

export function Dashboard() {
  const { user } = useAuth();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activity, setActivity] = useState<ActivityRow[]>([]);
  const [web, setWeb] = useState<{ repos?: any[]; channels?: string[]; jira?: any[] }>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
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
      setActivity(activityRes.data || []);
      setWeb(webRes || {});
      setLastRefresh(Date.now());
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // No setInterval — refresh on demand only.
  }, []);

  // Build a simple graph: each user is a node. Each tool used is connected.
  const userActionMap = new Map<string, Map<string, number>>();
  for (const a of activity) {
    if (!a.user_id) continue;
    const inner = userActionMap.get(a.user_id) || new Map<string, number>();
    inner.set(a.label, (inner.get(a.label) || 0) + 1);
    userActionMap.set(a.user_id, inner);
  }

  return (
    <div style={{ background: "#0a0a0a", color: "#e5e7eb", height: "100%", overflow: "auto", padding: 24 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 600 }}>Dashboard</h2>
          <p style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
            Real users from Supabase. Activity from agent_actions + observer_events. No fake data.
          </p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "#6b7280" }}>
            Last refresh: {new Date(lastRefresh).toLocaleTimeString()}
          </span>
          <button
            onClick={load}
            disabled={loading}
            style={{
              padding: "6px 14px",
              borderRadius: 6,
              background: "#1f2937",
              color: "#e5e7eb",
              border: "1px solid #374151",
              cursor: loading ? "wait" : "pointer",
              fontSize: 12,
            }}
          >
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && (
        <div style={{ background: "#1a0c0c", color: "#fca5a5", padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Network web — interactive cytoscape graph */}
      <section
        style={{
          background: "#0c0c0c",
          border: "1px solid #1f2937",
          borderRadius: 10,
          padding: 16,
          marginBottom: 16,
        }}
      >
        <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Team web — connections between users, tools, and integrations
        </h3>
        <TeamWebGraph
          profiles={profiles}
          activity={activity.map((a) => ({ user_id: a.user_id, label: a.label, kind: a.kind }))}
          currentUserId={user?.id}
          web={web}
        />
      </section>

      {/* Knowledge graph — real, from Supabase */}
      <section
        style={{
          background: "#0c0c0c",
          border: "1px solid #1f2937",
          borderRadius: 10,
          padding: 16,
          marginBottom: 16,
        }}
      >
        <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Team cards ({profiles.length} {profiles.length === 1 ? "user" : "users"})
        </h3>
        {profiles.length === 0 ? (
          <p style={{ fontSize: 12, color: "#6b7280" }}>No users yet.</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
            {profiles.map((p) => {
              const isYou = p.id === user?.id;
              const actions = userActionMap.get(p.id);
              const totalActions = actions ? Array.from(actions.values()).reduce((a, b) => a + b, 0) : 0;
              return (
                <div
                  key={p.id}
                  style={{
                    border: `1px solid ${isYou ? "#3b82f6" : "#1f2937"}`,
                    background: isYou ? "#0c1120" : "#0a0a0a",
                    borderRadius: 8,
                    padding: 12,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>
                      {p.display_name || "(no name)"} {isYou && <span style={{ color: "#3b82f6", fontSize: 10, marginLeft: 4 }}>(you)</span>}
                    </div>
                    <span
                      style={{
                        fontSize: 10,
                        background: totalActions > 0 ? "#1e293b" : "#1a1a1a",
                        color: totalActions > 0 ? "#93c5fd" : "#6b7280",
                        padding: "2px 6px",
                        borderRadius: 10,
                      }}
                    >
                      {totalActions} actions
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 8 }}>
                    {p.github_login && <span>github: {p.github_login} · </span>}
                    {p.jira_email && <span>jira: {p.jira_email} · </span>}
                    joined {new Date(p.created_at).toLocaleDateString()}
                  </div>
                  {actions && actions.size > 0 ? (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {Array.from(actions.entries()).slice(0, 6).map(([tool, n]) => (
                        <span
                          key={tool}
                          style={{
                            fontSize: 9,
                            background: "#0f172a",
                            color: "#cbd5e1",
                            padding: "2px 6px",
                            borderRadius: 4,
                            border: "1px solid #1e293b",
                          }}
                        >
                          {tool} ×{n}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p style={{ fontSize: 10, color: "#6b7280", fontStyle: "italic" }}>
                      no activity yet
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Activity timeline */}
      <section
        style={{
          background: "#0c0c0c",
          border: "1px solid #1f2937",
          borderRadius: 10,
          padding: 16,
        }}
      >
        <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>
          Recent activity ({activity.length})
        </h3>
        {activity.length === 0 ? (
          <p style={{ fontSize: 12, color: "#6b7280" }}>No actions yet. Use the chat with agent mode to generate some.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {activity.slice(0, 30).map((a, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "100px 140px 120px 1fr 80px",
                  gap: 10,
                  padding: "6px 10px",
                  borderRadius: 4,
                  fontSize: 11,
                  background: i % 2 === 0 ? "#0a0a0a" : "transparent",
                }}
              >
                <span style={{ color: "#6b7280" }}>
                  {a.at ? new Date(a.at).toLocaleTimeString() : "—"}
                </span>
                <span style={{ color: "#cbd5e1" }}>
                  {a.display_name || a.user_id?.slice(0, 8) || "system"}
                </span>
                <span
                  style={{
                    color: a.kind === "agent_action" ? "#a78bfa" : "#34d399",
                    fontFamily: "ui-monospace, monospace",
                    fontSize: 10,
                  }}
                >
                  {a.kind}
                </span>
                <span style={{ color: "#e5e7eb", fontFamily: "ui-monospace, monospace", fontSize: 10 }}>
                  <b>{a.label}</b>
                  {a.detail && <span style={{ color: "#6b7280" }}> — {a.detail.slice(0, 80)}</span>}
                </span>
                <span
                  style={{
                    color: a.status === "error" || a.status === "blocked" ? "#fca5a5" : a.status === "ok" ? "#86efac" : "#9ca3af",
                    fontSize: 10,
                  }}
                >
                  {a.status || ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
