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
  kind: "agent_action" | "observer_event";
}

interface WebData {
  repos?: Array<{ name: string; owner: string; language?: string | null }>;
  channels?: string[];
  jira?: Array<{ key: string; status: string; assignee?: string | null }>;
  contributors?: Array<{ name: string; commits: number }>;
}

interface Props {
  profiles: Profile[];
  activity: ActivityRow[];
  currentUserId?: string;
  web?: WebData;
}

const STYLE: cytoscape.Stylesheet[] = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      color: "#e5e7eb",
      "font-size": "10px",
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 6,
      "background-color": "#3b82f6",
      width: 26,
      height: 26,
      "border-width": 0,
    },
  },
  // people
  { selector: "node[type='you']", style: { "background-color": "#3b82f6", width: 44, height: 44, "border-color": "#60a5fa", "border-width": 3, "font-size": "12px", "font-weight": 600 } },
  { selector: "node[type='person']", style: { "background-color": "#a78bfa", width: 30, height: 30 } },
  // services
  { selector: "node[type='service']", style: { "background-color": "#5bd1c2", "shape": "round-hexagon", width: 56, height: 36, "font-size": "11px", "font-weight": 600 } },
  // repos
  { selector: "node[type='repo']", style: { "background-color": "#f0a04b", "shape": "round-rectangle", width: 78, height: 24 } },
  // jira tickets
  { selector: "node[type='jira']", style: { "background-color": "#ec4899", "shape": "round-rectangle", width: 60, height: 22, "font-size": "9px" } },
  // channels
  { selector: "node[type='channel']", style: { "background-color": "#22d3ee", "shape": "round-rectangle", width: 80, height: 22, "font-size": "9px" } },
  // tools (actions)
  { selector: "node[type='tool']", style: { "background-color": "#10b981", "shape": "round-rectangle", width: 68, height: 22, "font-size": "9px" } },
  {
    selector: "edge",
    style: {
      width: "data(weight)" as any,
      "line-color": "#374151",
      "curve-style": "bezier",
      opacity: 0.55,
      "target-arrow-shape": "triangle",
      "target-arrow-color": "#374151",
      "arrow-scale": 0.6,
    },
  },
];

export function TeamWebGraph({ profiles, activity, currentUserId, web }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const nodes: cytoscape.NodeDefinition[] = [];
    const edges: cytoscape.EdgeDefinition[] = [];

    // people
    for (const p of profiles) {
      nodes.push({
        data: {
          id: `u:${p.id}`,
          label: p.display_name || (p.github_login ?? "(user)"),
          type: p.id === currentUserId ? "you" : "person",
        },
      });
    }

    // service hubs (always present so the user can see what's plugged in)
    const services = ["GitHub", "Slack", "Jira"];
    for (const s of services) {
      nodes.push({ data: { id: `s:${s}`, label: s, type: "service" } });
      for (const p of profiles) {
        edges.push({ data: { id: `u:${p.id}->s:${s}`, source: `u:${p.id}`, target: `s:${s}`, weight: 2 } });
      }
    }

    // repos under GitHub
    for (const r of web?.repos || []) {
      const id = `r:${r.owner}/${r.name}`;
      nodes.push({ data: { id, label: r.name, type: "repo" } });
      edges.push({ data: { id: `s:GitHub->${id}`, source: "s:GitHub", target: id, weight: 1 } });
    }

    // jira tickets under Jira
    for (const j of web?.jira || []) {
      const id = `j:${j.key}`;
      nodes.push({ data: { id, label: j.key, type: "jira" } });
      edges.push({ data: { id: `s:Jira->${id}`, source: "s:Jira", target: id, weight: 1 } });
    }

    // slack channels under Slack
    for (const c of web?.channels || []) {
      const id = `c:${c}`;
      nodes.push({ data: { id, label: `#${c}`, type: "channel" } });
      edges.push({ data: { id: `s:Slack->${id}`, source: "s:Slack", target: id, weight: 1 } });
    }

    // tools that the user has invoked, attached to that user
    const userToolCounts = new Map<string, Map<string, number>>();
    for (const a of activity) {
      if (!a.user_id) continue;
      const inner = userToolCounts.get(a.user_id) || new Map<string, number>();
      inner.set(a.label, (inner.get(a.label) || 0) + 1);
      userToolCounts.set(a.user_id, inner);
    }
    const toolSeen = new Set<string>();
    for (const [uid, tools] of userToolCounts) {
      for (const [tool, count] of tools) {
        const tid = `t:${tool}`;
        if (!toolSeen.has(tid)) {
          toolSeen.add(tid);
          nodes.push({ data: { id: tid, label: tool, type: "tool" } });
        }
        edges.push({ data: { id: `${uid}-${tool}`, source: `u:${uid}`, target: tid, weight: Math.min(2 + count, 6) } });
      }
    }

    cyRef.current?.destroy();
    cyRef.current = cytoscape({
      container: ref.current,
      elements: [...nodes, ...edges],
      style: STYLE,
      layout: { name: "cose", animate: false, idealEdgeLength: () => 90, nodeRepulsion: () => 4500, padding: 30 } as any,
      wheelSensitivity: 0.2,
    });

    return () => cyRef.current?.destroy();
  }, [profiles, activity, currentUserId, web]);

  return (
    <div style={{ position: "relative" }}>
      <div ref={ref} style={{ height: 460, width: "100%", background: "#0a0a0a", borderRadius: 8 }} />
      <div style={{ position: "absolute", bottom: 6, right: 8, fontSize: 9, color: "#6b7280", display: "flex", flexWrap: "wrap", gap: 8, maxWidth: "60%", justifyContent: "flex-end" }}>
        <Legend color="#3b82f6" label="you" />
        <Legend color="#a78bfa" label="teammate" />
        <Legend color="#5bd1c2" label="service" shape="hex" />
        <Legend color="#f0a04b" label="repo" shape="rect" />
        <Legend color="#ec4899" label="jira" shape="rect" />
        <Legend color="#22d3ee" label="channel" shape="rect" />
        <Legend color="#10b981" label="tool used" shape="rect" />
      </div>
    </div>
  );
}

function Legend({ color, label, shape }: { color: string; label: string; shape?: "hex" | "rect" }) {
  const radius = shape === "rect" ? 2 : "50%";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
      <span style={{ width: 8, height: 8, borderRadius: radius, background: color }} />
      {label}
    </span>
  );
}
