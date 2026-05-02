/**
 * Knowledge graph primitives shared across services for graph queries.
 * The Neo4j-backed canonical model lives inside services/knowledge.
 */

export interface GraphNode {
  id: string;
  /** "person" | "service" | "repo" | "document" | "concept" | ... */
  type: string;
  label: string;
  properties: Record<string, unknown>;
  source?: string | null;
  /** ISO 8601 timestamp */
  timestamp: string;
}

export interface GraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  /** "OWNS" | "CONTRIBUTES_TO" | "DEPENDS_ON" | "MENTIONED_IN" | ... */
  type: string;
  properties: Record<string, unknown>;
  source?: string | null;
  /** ISO 8601 timestamp */
  timestamp: string;
}

export interface GraphSnapshot {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
