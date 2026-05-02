# mycelium-db

Database clients and Alembic migrations.

## Postgres (system of record)

PostgreSQL + `pgvector`. Holds:

- `events` — all normalized `MyceliumEvent`s (written by API ingestion worker, read by `process-intel`)
- `integration_syncs` — connector, last_sync_at, status, error_message (**written only by `services/integrations`**, read by API)
- `agents`, `agent_tasks`, `audit_log`
- LangGraph checkpointing (added later as needed)
- Vector embeddings (`pgvector`)

### Write ownership (strict)

| Table              | Sole writer                            | Readers                                  |
| ------------------ | -------------------------------------- | ---------------------------------------- |
| `events`           | `apps/api` ingestion worker            | `process-intel`, `apps/api`              |
| `integration_syncs`| `services/integrations`                | `apps/api`                               |
| `agents`           | `services/agent-runtime`               | `apps/api`                               |
| `agent_tasks`      | `services/agent-runtime`, `apps/api`   | `apps/api`, `services/learning`          |
| `audit_log`        | `services/agent-runtime`               | `apps/api`                               |

No service cross-writes another service's tables. Ever.

## Neo4j

Used **only** by `services/knowledge`. The Neo4j client lives in this package but **must not be imported by any other service**. We rely on convention + code review for this — there's a CI lint check in `tools/check-imports.py` (see `infrastructure/observability`).

## Alembic

```bash
cd packages/db/python
poetry run alembic upgrade head
```

Auto-runs on `docker compose up` via the API container's entrypoint.

## Python install

```toml
mycelium-db = { path = "../../packages/db/python", develop = true }
```
