# Data flow

How a raw GitHub event becomes a knowledge graph node, becomes an agent action, becomes an audit log entry.

## Walkthrough: PR opened → triage agent → audit log

### 1. Capture

`services/integrations/github` polls GitHub on its schedule (or receives a webhook in the future). It builds a `MyceliumEvent`:

```json
{
  "id": "8b4c…",
  "type": "github.pr.opened",
  "source": "github",
  "actor": { "id": "u_alice", "type": "user" },
  "object": { "id": "42", "type": "pull_request" },
  "timestamp": "2026-05-01T19:01:23Z",
  "schema_version": "1.0",
  "metadata": { "title": "feat: idempotent retry" },
  "correlation_id": "github:pr-42",
  "parent_correlation_id": null
}
```

The `correlation_id` is the natural ID `github:pr-42` (rule 1).

### 2. Publish to events.raw

The connector calls `event_bus.publish(Topic.EVENTS_RAW, event, correlation_id="github:pr-42")`. The bus routes it to partition `hash("github:pr-42") % 8`. After publishing, the connector writes `integration_syncs` with `last_sync_at = now`, `status = "ok"`.

### 3. Classification

`services/security/classification` is the **only** consumer of `events.raw`. It scrubs for PII / secrets, then publishes the (possibly redacted) event to `events.processed`.

If classification fails, it retries up to `CLASSIFICATION_RETRY_LIMIT` (default 3) and then publishes to `events.dlq` with:
- `error_category`
- `retry_count`
- `original_event`

### 4. API ingestion

`apps/api` runs the events ingestion worker. It consumes `events.processed` and `INSERT … ON CONFLICT DO NOTHING` into the Postgres `events` table. The API ingestion worker is the **sole writer** of this table.

### 5. Knowledge graph projection

`services/knowledge` also consumes `events.processed`. For each event it upserts:
- a node for the actor (`u_alice`, type `person`)
- a node for the object (`github:42`, type `pull_request`)
- an edge `u_alice -[GITHUB.PR.OPENED]-> github:42`

It then publishes a small `graph.updates` message so dashboards can refresh.

### 6. Trigger a triage agent

A workflow (or the API directly) calls `POST /agents/{agent_id}/tasks` with `agent_type=triage` and `correlation_id=github:pr-42` (so this task is *linked* to the PR's correlation chain).

The API publishes an `AgentTask` to `agents.tasks`. The task starts in status `queued`.

### 7. Agent execution

`services/agent-runtime` consumes `agents.tasks`. It transitions the task `queued → running` (publishing an interim result), queries `services/knowledge/graph` over HTTP for context about PR #42, and runs the `triage` skill.

When the skill returns, the runtime publishes the final outcome to `agents.results` with `status=succeeded`.

### 8. Result reconciliation

`apps/api`'s agent-results worker consumes `agents.results`, validates the lifecycle transition (`running → succeeded` is valid), updates the `agent_tasks` row, and inserts an `audit_log` entry recording the action.

### 9. Learning signal (when applicable)

`services/learning` also consumes `agents.results` and `workflows.approvals`. If a human later submits an approval/rejection for the agent's action, the learning service writes a `learning_signals` row to Postgres. No other action — full RL is deferred.

### 10. UI refresh

The dashboard polls:
- `GET /graph` → fresh subgraph including new `u_alice -> github:42` edge.
- `GET /integrations` → `last_sync_at` updated.
- `GET /agents` → new agent task visible.

The frontend never touches Redis or Postgres directly. The API is the only door.

## Correlation chain visualization

```
github:pr-42                  (correlation_id)
├── github.pr.opened          (parent: null)
├── github.pr.review_requested (parent: github:pr-42)
├── github.pr.reviewed        (parent: github:pr-42)
└── github.pr.merged          (parent: github:pr-42)

agent task triage-PR42        (correlation_id: github:pr-42, parent: github:pr-42)
└── agents.results succeeded
```

Each step preserves the `correlation_id` so process-intel can reconstruct the full case end-to-end.
