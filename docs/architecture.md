# Architecture

A bird's-eye view of every Mycelium component, what it does, and how the pieces connect.

## High-level

```
┌────────────────────────┐                                      ┌─────────────────────────┐
│ services/observer      │                                      │ services/integrations   │
│ (LOCAL only — laptops) │                                      │ GitHub / Slack / Jira   │
└─────────────┬──────────┘                                      └───────────┬─────────────┘
              │ HTTPS POST                                                  │ publish
              ▼                                                             ▼
   ┌─────────────────────────────────────────────────────────────────────────────────┐
   │                                  apps/api                                       │
   │ /chat /graph /agents /integrations /workflows /observability /health /metrics   │
   │ Auth (JWT, DEV_MODE bypass) · Pebblo filter on user queries                     │
   │ Ingestion worker  ◀────────────────  Redis Streams: events.processed            │
   │ Sole writer of `events` table                                                   │
   └────────┬─────────────┬────────────┬───────────┬───────────────────────┬─────────┘
            │ HTTP        │ HTTP       │ HTTP      │ Redis Streams         │ Redis Streams
            ▼             ▼            ▼           ▼                       ▼
   ┌─────────────┐  ┌─────────────┐  ┌────────────┐  ┌────────────────────┐
   │  knowledge  │  │ agent-      │  │ workflows  │  │ events.raw         │
   │  (Neo4j)    │  │ runtime     │  │            │  │      │             │
   │ + Graphiti  │  │ + Claworc   │  │            │  │      ▼             │
   │ + code-     │  │ + skills    │  │            │  │ services/security  │
   │   index     │  │             │  │            │  │ classification     │
   │ + onboarding│  │             │  │            │  │ retry × 3 → DLQ    │
   └─────┬───────┘  └─────┬───────┘  └────────────┘  └─────────┬──────────┘
         │                │                                    │
         │ graph.updates  │ agents.results                     │ events.processed
         ▼                ▼                                    ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │                            Redis Streams                            │
   └─────────────────────────────────────────────────────────────────────┘
                ▲                                       ▲
                │                                       │
     ┌──────────┴──────────┐               ┌────────────┴────────────┐
     │ services/process-intel              │ services/learning        │
     │ (reads Postgres events)             │ (observe-only)           │
     └─────────────────────┘               └─────────────────────────┘

   Datastores:
   - Postgres + pgvector  (system of record)        — owners listed below
   - Neo4j                                          — knowledge ONLY
   - Redis Streams                                  — transport ONLY
```

## Components

### apps/api

The single entry point for the frontend. Auth + Pebblo filter at this boundary. Runs the events ingestion worker. Sole writer of the `events` table.

### apps/frontend

React + Vite. Two views: chat (backed by `POST /chat`) and dashboard (Cytoscape graph + `integration_syncs` + recent agent activity). Talks to `apps/api` exclusively.

### services/observer

Local-only watcher on developer machines. **Privacy-by-design**: command name (no args), repo path, timestamp, changed filenames (no contents). Posts events to `apps/api` over HTTPS.

### services/agent-runtime

OpenClaw + Claworc. Consumes `agents.tasks`, runs the appropriate skill from the registry, queries the knowledge service via HTTP for context, publishes to `agents.results`.

### services/knowledge

Sole owner of Neo4j. Three sub-modules:

- `graph/` — Graphiti temporal knowledge graph; consumes `events.processed`.
- `code-index/` — GitNexus / CodeGraphContext / Tree-sitter structural code graph.
- `onboarding/` — Understand-Anything briefings.

Pebblo-pattern enforcement applied to all agent queries (defense in depth — API also enforces).

### services/integrations

GitHub / Slack / Jira connectors. Sole writer of `integration_syncs`. Publishes to `events.raw`.

### services/process-intel

`pm4py` over the Postgres `events` table. Publishes process maps to `graph.updates`.

### services/learning

Observe-only. Subscribes to `agents.results` and `workflows.approvals`. Logs human-override training signals to Postgres. Full RL implementation later.

### services/security

`classification/` — sole consumer of `events.raw`. Retries × 3 → DLQ with `error_category` + `retry_count` + `original_event`.

`enforcement/` lives in `packages/security-filter` (shared package, not a service).

## Data ownership

| Resource              | Sole owner / writer                  |
| --------------------- | ------------------------------------ |
| Neo4j                 | `services/knowledge`                 |
| Postgres `events`     | `apps/api` ingestion worker          |
| Postgres `integration_syncs` | `services/integrations`       |
| Postgres `agents`     | `services/agent-runtime`             |
| Postgres `agent_tasks`| `services/agent-runtime` and `apps/api` (state machine writes) |
| Postgres `audit_log`  | `services/agent-runtime`, `apps/api` results worker |
| Postgres `learning_signals` | `services/learning`            |

## Communication patterns

- **Events** → Redis Streams (async, durable, ack/retry, DLQ).
- **Queries** → direct HTTP (sync, request/response).
- **Frontend** → API only. Never to a service or DB.
- **Services** → may HTTP each other for queries; never read another service's DB.
