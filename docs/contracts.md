# Contracts

The shared types in `packages/shared-types` are the contract between every service. This document is the plain-English version. **If you change a schema, update this file.**

---

## MyceliumEvent

```ts
{
  id: string,
  type: string,                 // "github.pr.opened", "slack.message.posted", …
  source: string,               // "github" | "slack" | "jira" | "observer" | "agent" | "api"
  actor: { id, type, display_name? },
  object: { id, type, url? },
  timestamp: string,            // ISO 8601
  schema_version: string,       // "1.0" by default; bump on changes
  metadata: object,
  correlation_id: string,       // MANDATORY
  parent_correlation_id?: string
}
```

### correlation_id (mandatory, never null)

Generation rules, in priority order:

1. **Natural ID** if one exists. Examples: PR number (`github:pr-42`), Slack thread ID (`slack:thread-T1.1714000000`), Jira ticket key (`jira:ENG-101`).
2. **`hash(source + object_id + time_window) + uuid suffix`**. The hash uses a 60-second time window by default; the uuid suffix prevents burst collisions (multiple concurrent producers in the same window).
3. **API fallback**. If a producer hits `POST /integrations/ingest` without setting one, `apps/api` derives one using rule 2.

### parent_correlation_id (optional)

Set whenever an event modifies or extends a prior event:

- Slack message edits → parent is the original message correlation_id.
- GitHub force pushes → parent is the original commit correlation_id.
- Jira ticket merges → parent is the surviving ticket correlation_id.
- Threaded replies → parent is the thread correlation_id.

This forms a chain you can walk to reconstruct a case end-to-end.

### schema_version (mandatory)

- Default `"1.0"`.
- **Bump it whenever you add or change a field** on `MyceliumEvent` (or any subtype with versioned semantics).
- Consumers must handle unknown versions gracefully:
  - log a warning,
  - best-effort parse,
  - never crash.
- All version changes must be documented below in the **Schema version log**.

---

## AgentTask

```ts
{
  task_id: string,
  agent_id: string,
  agent_type: string,           // "triage" | "onboard" | "code-review" | …
  input_data: object,
  correlation_id: string,       // same rules as MyceliumEvent
  parent_correlation_id?: string,
  status: "queued" | "running" | "succeeded" | "failed" | "retried" | "cancelled",
  created_at: string,
  updated_at: string,
  result?: object,
  error?: string
}
```

### Lifecycle (no skipping)

```
queued    → running | cancelled
running   → succeeded | failed
failed    → retried | cancelled
retried   → succeeded | cancelled
succeeded → (terminal)
cancelled → (terminal)
```

The single source of truth is `mycelium_shared_types.transitions.VALID_AGENT_TASK_TRANSITIONS` (Python) and `VALID_AGENT_TASK_TRANSITIONS` (TypeScript). Use `is_valid_agent_task_transition` / `isValidAgentTaskTransition` everywhere a state changes. The API's agent-results worker refuses invalid transitions.

---

## Agent

```ts
{
  id: string,
  owner_user_id: string,
  capabilities: string[],
  status: "idle" | "busy" | "offline" | "error",
  created_at: string
}
```

---

## HealthCheck (identical across all services)

```ts
{
  status: "ok" | "error",
  service: string,                  // e.g. "mycelium-api", "mycelium-knowledge"
  timestamp: string                 // ISO 8601
}
```

Defined once in `mycelium_shared_types.health.HealthCheck`. Every Mycelium service exposes `GET /health` returning exactly this shape.

---

## Other types

- **WorkflowState** — `pending → running → awaiting_approval → approved | rejected → completed | failed`.
- **AuditEntry** — immutable record of an agent action.
- **GraphNode / GraphEdge** — used at API boundaries for `/graph`. The Neo4j-backed canonical model lives inside `services/knowledge`.

---

## Event ordering guarantee

**Ordering is guaranteed per `correlation_id` stream partition only.** Each topic in the event bus is split into N partitions (default 8) keyed by `hash(correlation_id)`. Two events with the same `correlation_id` always land in the same partition and arrive at consumers in the order they were published. Two events with **different** `correlation_id`s have **no** ordering guarantee — you may see them interleaved arbitrarily.

If your consumer needs total order across cases, pull from the Postgres `events` table instead.

---

## Redis = transport. Postgres = system of record.

- Redis Streams holds events in flight. Anything you can't lose must be persisted to Postgres before you ack the stream message.
- Read-only analytics that scan history (process-intel, audit dashboards, ML pipelines) read from Postgres, never from Redis.

---

## Database write ownership (strict)

| Table                | Sole writer                                  | Readers                                  |
| -------------------- | -------------------------------------------- | ---------------------------------------- |
| `events`             | `apps/api` ingestion worker                  | `apps/api`, `services/process-intel`     |
| `integration_syncs`  | `services/integrations`                      | `apps/api` (read-only)                   |
| `agents`             | `services/agent-runtime`                     | `apps/api`                               |
| `agent_tasks`        | `services/agent-runtime` and `apps/api` (state-machine updates only) | `apps/api`, `services/learning` |
| `audit_log`          | `services/agent-runtime`, `apps/api` results worker | `apps/api`                          |
| `learning_signals`   | `services/learning`                          | `apps/api`                               |

No service cross-writes another service's tables. Ever.

---

## DLQ retry policy

- Classification retries up to `CLASSIFICATION_RETRY_LIMIT` (default `3`).
- After that, the event is published to `events.dlq` with:
  - `error_category` — one of `mycelium_event_bus.ErrorCategory`.
  - `retry_count` — the number of attempts.
  - `original_event` — the full event payload as received.
- **Never silently drop events.** If you can't classify, DLQ it.

---

## Schema version log

| Version | Date       | Change                                        |
| ------- | ---------- | --------------------------------------------- |
| 1.0     | 2026-05-01 | Initial schema.                               |

When you add/change a field, append a row here, bump `DEFAULT_SCHEMA_VERSION` in shared-types, and update consumers to handle the new version.
