import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { Core } from "cytoscape";
import type { GraphSnapshot } from "@mycelium/shared-types";

const STYLE: cytoscape.Stylesheet[] = [
  {
    selector: "node",
    style: {
      "background-color": "#5b8def",
      label: "data(label)",
      color: "#e4ecff",
      "font-size": "10px",
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 4,
      width: 24,
      height: 24,
    },
  },
  {
    selector: "node[type = 'person']",
    style: { "background-color": "#9b8df5" },
  },
  {
    selector: "node[type = 'service']",
    style: { "background-color": "#5bd1c2" },
  },
  {
    selector: "node[type = 'repo']",
    style: { "background-color": "#f0a04b" },
  },
  {
    selector: "edge",
    style: {
      width: 1,
      "line-color": "#3a4564",
      "target-arrow-color": "#3a4564",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "font-size": "8px",
      label: "data(label)",
      color: "#7a86a8",
    },
  },
];

export function GraphView({ snapshot }: { snapshot: GraphSnapshot | null }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    cyRef.current = cytoscape({
      container: containerRef.current,
      style: STYLE,
      layout: { name: "cose", animate: false },
      elements: [],
    });
    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !snapshot) return;
    const elements = [
      ...snapshot.nodes.map((n) => ({
        data: { id: n.id, label: n.label, type: n.type },
      })),
      ...snapshot.edges.map((e) => ({
        data: { id: e.id, source: e.source_id, target: e.target_id, label: e.type },
      })),
    ];
    cy.elements().remove();
    cy.add(elements);
    cy.layout({ name: "cose", animate: false }).run();
  }, [snapshot]);

  return (
    <div className="graph-view">
      <div ref={containerRef} className="graph-canvas" />
      {!snapshot && <div className="graph-empty">Loading graph…</div>}
      {snapshot && snapshot.nodes.length === 0 && (
        <div className="graph-empty">No graph data yet.</div>
      )}
    </div>
  );
}
