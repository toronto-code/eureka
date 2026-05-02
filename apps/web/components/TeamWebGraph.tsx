"use client";

import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { Core } from "cytoscape";

interface Profile {
  id: string;
  display_name: string | null;
  github_login: string | null;
}
interface ActivityRow {
  user_id: string | null;
  label: string;
}
interface WebData {
  repos?: Array<{ name: string; owner: string }>;
  channels?: string[];
  jira?: Array<{ key: string }>;
}
interface Props {
  profiles: Profile[];
  activity: ActivityRow[];
  currentUserId?: string;
  web?: WebData;
}

const STYLE: any[] = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      color: "#1a1a1a",
      "font-size": "11px",
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 6,
      "background-color": "#2946CA",
      width: 28,
      height: 28,
    },
  },
  { selector: "node[type='you']", style: { "background-color": "#2946CA", width: 44, height: 44, "border-color": "#5b75dc", "border-width": 3, "font-size": "13px", "font-weight": 600 } },
  { selector: "node[type='person']", style: { "background-color": "#7c66e0", width: 30, height: 30 } },
  { selector: "node[type='service']", style: { "background-color": "#2f9d6c", "shape": "round-hexagon", width: 56, height: 36, "font-size": "11px", "font-weight": 600 } },
  { selector: "node[type='repo']", style: { "background-color": "#c8881e", "shape": "round-rectangle", width: 78, height: 24 } },
  { selector: "node[type='jira']", style: { "background-color": "#c2453d", "shape": "round-rectangle", width: 60, height: 22, "font-size": "10px" } },
  { selector: "node[type='channel']", style: { "background-color": "#3b82f6", "shape": "round-rectangle", width: 80, height: 22, "font-size": "10px" } },
  { selector: "node[type='tool']", style: { "background-color": "#535350", "shape": "round-rectangle", width: 68, height: 22, "font-size": "10px", color: "#fff" } },
  {
    selector: "edge",
    style: {
      width: "data(weight)" as any,
      "line-color": "#D1D1CF",
      "curve-style": "bezier",
      opacity: 0.7,
      "target-arrow-shape": "triangle",
      "target-arrow-color": "#D1D1CF",
      "arrow-scale": 0.6,
    },
  },
];

export function TeamWebGraph({ profiles, activity, currentUserId, web }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  // Restrict the web to ONLY users + tools + services that have appeared in
  // the (already-windowed) activity. When the activity expires, so does the web.
  const profileIds = new Set(profiles.map((p) => p.id));
  const activeUsers = new Set<string>();
  const activeTools = new Map<string, Map<string, number>>(); // user_id -> tool -> count
  for (const a of activity) {
    if (!a.user_id || !profileIds.has(a.user_id)) continue;
    activeUsers.add(a.user_id);
    const inner = activeTools.get(a.user_id) || new Map<string, number>();
    inner.set(a.label, (inner.get(a.label) || 0) + 1);
    activeTools.set(a.user_id, inner);
  }
  const hasActivity = activeUsers.size > 0;

  useEffect(() => {
    if (!ref.current) return;
    if (!hasActivity) {
      // No recent activity → wipe the graph entirely
      cyRef.current?.destroy();
      cyRef.current = null;
      return;
    }
    const nodes: cytoscape.NodeDefinition[] = [];
    const edges: cytoscape.EdgeDefinition[] = [];

    // Users: only those who have recent activity
    for (const p of profiles) {
      if (!activeUsers.has(p.id)) continue;
      nodes.push({
        data: {
          id: `u:${p.id}`,
          label: p.display_name || p.github_login || "(user)",
          type: p.id === currentUserId ? "you" : "person",
        },
      });
    }

    // Service hubs — only show if any active user has tools touching them
    const allTools = Array.from(activeTools.values()).flatMap((m) => Array.from(m.keys()));
    const usesGitHub = allTools.some((t) => /repo|branch|commit|pr|read_file|list_repo|workflow|github/i.test(t));
    const usesSlack = allTools.some((t) => /slack|channel|invite|topic/i.test(t));
    const usesJira = allTools.some((t) => /jira|comment_jira|transition|assign_jira/i.test(t));

    const activeServices: string[] = [];
    if (usesGitHub) activeServices.push("GitHub");
    if (usesSlack) activeServices.push("Slack");
    if (usesJira) activeServices.push("Jira");

    for (const s of activeServices) {
      nodes.push({ data: { id: `s:${s}`, label: s, type: "service" } });
      for (const uid of activeUsers) {
        edges.push({ data: { id: `u:${uid}->s:${s}`, source: `u:${uid}`, target: `s:${s}`, weight: 2 } });
      }
    }

    // Repos / jira tickets / channels — only if their service is active
    if (usesGitHub) {
      for (const r of web?.repos || []) {
        const id = `r:${r.owner}/${r.name}`;
        nodes.push({ data: { id, label: r.name, type: "repo" } });
        edges.push({ data: { id: `s:GitHub->${id}`, source: "s:GitHub", target: id, weight: 1 } });
      }
    }
    if (usesJira) {
      for (const j of web?.jira || []) {
        const id = `j:${j.key}`;
        nodes.push({ data: { id, label: j.key, type: "jira" } });
        edges.push({ data: { id: `s:Jira->${id}`, source: "s:Jira", target: id, weight: 1 } });
      }
    }
    if (usesSlack) {
      for (const c of web?.channels || []) {
        const id = `c:${c}`;
        nodes.push({ data: { id, label: `#${c}`, type: "channel" } });
        edges.push({ data: { id: `s:Slack->${id}`, source: "s:Slack", target: id, weight: 1 } });
      }
    }

    // Tools (only ones from recent activity), connected to the user who used them
    const toolSeen = new Set<string>();
    for (const [uid, tools] of activeTools) {
      for (const [tool, count] of tools) {
        const tid = `t:${tool}`;
        if (!toolSeen.has(tid)) {
          toolSeen.add(tid);
          nodes.push({ data: { id: tid, label: tool, type: "tool" } });
        }
        edges.push({
          data: { id: `${uid}-${tool}`, source: `u:${uid}`, target: tid, weight: Math.min(2 + count, 6) },
        });
      }
    }

    cyRef.current?.destroy();
    cyRef.current = cytoscape({
      container: ref.current,
      elements: [...nodes, ...edges],
      style: STYLE as any,
      layout: { name: "cose", animate: false, idealEdgeLength: () => 95, nodeRepulsion: () => 4500, padding: 24 } as any,
      wheelSensitivity: 0.2,
    });
    return () => cyRef.current?.destroy();
  }, [profiles, activity, currentUserId, web, hasActivity]);

  return (
    <div style={{ position: "relative" }}>
      <div
        ref={ref}
        style={{
          height: 480,
          width: "100%",
          background: "var(--neutral-100)",
          borderRadius: "var(--radius)",
          overflow: "hidden",
        }}
      />
      {!hasActivity && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-muted)",
            fontSize: 13,
            pointerEvents: "none",
            textAlign: "center",
            padding: 24,
          }}
        >
          <div style={{ fontWeight: 600, color: "var(--text)" }}>No recent activity</div>
          <div style={{ marginTop: 4 }}>
            The team web rebuilds itself when someone uses the orchestrator.
            Activity older than 20 minutes rolls off automatically.
          </div>
        </div>
      )}
      <div style={{ position: "absolute", bottom: 8, right: 12, fontSize: 10, color: "var(--text-muted)", display: "flex", flexWrap: "wrap", gap: 10 }}>
        <Legend color="#2946CA" label="you" />
        <Legend color="#7c66e0" label="teammate" />
        <Legend color="#2f9d6c" label="service" shape="hex" />
        <Legend color="#c8881e" label="repo" shape="rect" />
        <Legend color="#c2453d" label="jira" shape="rect" />
        <Legend color="#3b82f6" label="channel" shape="rect" />
        <Legend color="#535350" label="tool used" shape="rect" />
      </div>
    </div>
  );
}

function Legend({ color, label, shape }: { color: string; label: string; shape?: "hex" | "rect" }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: 9, height: 9, borderRadius: shape === "rect" ? 2 : "50%", background: color }} />
      {label}
    </span>
  );
}
