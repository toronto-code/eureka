"use client";

import { useEffect, useRef, useState } from "react";
import { authFetch } from "@/lib/auth";

const API_URL =
  (typeof window !== "undefined" && (window as any).__API_URL__) ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

interface Insight {
  type: "alert" | "warning" | "info";
  title: string;
  description: string;
}

interface AgentAction {
  tool: string;
  args?: Record<string, unknown>;
  summary?: string;
  status?: string;
  ts?: number;
}

const insightStyles: Record<string, { bg: string; fg: string; border: string }> = {
  alert: { bg: "var(--red-soft)", fg: "var(--red)", border: "var(--red)" },
  warning: { bg: "var(--amber-soft)", fg: "var(--amber)", border: "var(--amber)" },
  info: { bg: "var(--accent-soft)", fg: "var(--accent)", border: "var(--accent)" },
};

const actionColor = (s?: string) =>
  s === "error" || s === "blocked"
    ? "var(--red)"
    : s === "running" || s === "awaiting_confirm"
    ? "var(--amber)"
    : "var(--green)";

type Open = "none" | "insights" | "actions";

export function OLPagePanels() {
  const [open, setOpen] = useState<Open>("none");
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => {
    authFetch(`${API_URL}/chat/insights`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setInsights)
      .catch(() => setInsights([]));
  }, []);

  useEffect(() => {
    const es = new EventSource(`${API_URL}/chat/actions/stream`);
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        if (evt.tool) setActions((prev) => [evt, ...prev].slice(0, 30));
      } catch {}
    };
    es.onerror = () => es.close();
    sseRef.current = es;
    return () => sseRef.current?.close();
  }, []);

  const insightsCount = insights?.length ?? 0;
  const actionsCount = actions.length;

  return (
    <div className="ol-panels">
      <div className="ol-panels-bar">
        <button
          type="button"
          className={`ol-panel-btn ${open === "insights" ? "active" : ""}`}
          onClick={() => setOpen(open === "insights" ? "none" : "insights")}
          title="Insights"
          aria-label="Insights"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21h6M12 17v4M12 3a7 7 0 0 0-4 12.7V17h8v-1.3A7 7 0 0 0 12 3z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {insightsCount > 0 && <span className="ol-panel-badge">{insightsCount}</span>}
        </button>
        <button
          type="button"
          className={`ol-panel-btn ${open === "actions" ? "active" : ""}`}
          onClick={() => setOpen(open === "actions" ? "none" : "actions")}
          title="Live agent actions"
          aria-label="Live agent actions"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {actionsCount > 0 && <span className="ol-panel-badge">{actionsCount}</span>}
        </button>
      </div>

      {open === "insights" && (
        <div className="ol-panel-popover">
          <div className="ol-panel-header">
            <span>Insights</span>
            <button onClick={() => setOpen("none")} className="ol-panel-close" aria-label="Close">×</button>
          </div>
          <div className="ol-panel-body">
            {!insights && <p className="ol-panel-empty">Loading…</p>}
            {insights?.length === 0 && <p className="ol-panel-empty">No insights yet.</p>}
            {insights?.map((ins, i) => {
              const c = insightStyles[ins.type] ?? insightStyles.info;
              return (
                <div
                  key={i}
                  className="ol-panel-insight"
                  style={{ borderLeft: `3px solid ${c.border}`, background: c.bg }}
                >
                  <div className="ol-panel-insight-title" style={{ color: c.fg }}>{ins.title}</div>
                  <div className="ol-panel-insight-desc">{ins.description}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {open === "actions" && (
        <div className="ol-panel-popover">
          <div className="ol-panel-header">
            <span>Live agent actions</span>
            <button onClick={() => setOpen("none")} className="ol-panel-close" aria-label="Close">×</button>
          </div>
          <div className="ol-panel-body">
            {actions.length === 0 && <p className="ol-panel-empty">None yet.</p>}
            {actions.map((a, i) => (
              <div
                key={i}
                className="ol-panel-action"
                style={{ borderLeft: `2px solid ${actionColor(a.status)}` }}
              >
                <div className="ol-panel-action-row">
                  <span style={{ color: actionColor(a.status), fontWeight: 600 }}>{a.tool}</span>
                  <span className="ol-panel-action-time">
                    {a.ts ? new Date(a.ts * 1000).toLocaleTimeString() : ""}
                  </span>
                </div>
                {a.summary && a.status !== "running" && (
                  <div className="ol-panel-action-summary">{a.summary.slice(0, 100)}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
