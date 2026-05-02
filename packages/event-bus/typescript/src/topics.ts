export const Topic = {
  EVENTS_RAW: "events.raw",
  EVENTS_PROCESSED: "events.processed",
  EVENTS_DLQ: "events.dlq",
  AGENTS_TASKS: "agents.tasks",
  AGENTS_RESULTS: "agents.results",
  WORKFLOWS_APPROVALS: "workflows.approvals",
  GRAPH_UPDATES: "graph.updates",
} as const;

export type Topic = (typeof Topic)[keyof typeof Topic];
