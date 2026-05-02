# apps/api

The Mycelium API gateway. **The only thing the frontend talks to.**

## Endpoints

| Method | Path                     | Notes                                                   |
| ------ | ------------------------ | ------------------------------------------------------- |
| GET    | `/health`                | Standard `HealthCheck` shape (see shared-types).        |
| POST   | `/chat`                  | Routes prompts to the agent-runtime via `agents.tasks`. |
| GET    | `/graph`                 | Query knowledge graph. Params: `limit`, `depth`, `node_id`. |
| GET    | `/agents`                | List agents owned by the current user.                  |
| POST   | `/agents/{id}/tasks`     | Dispatch an `AgentTask`.                                |
| GET    | `/integrations`          | Read `integration_syncs` (read-only on this table).     |
| POST   | `/integrations/ingest`   | Producer entrypoint for events that don't go via the bus directly. Adds correlation_id fallback (rule 3). |
| GET    | `/workflows`             | List active workflows.                                  |
| POST   | `/workflows/approvals`   | Submit a human approval. Publishes to `workflows.approvals`. |
| GET    | `/observability`         | Service health summary scraped from each `/health`.     |

## Event bus

| Direction | Topic              | Notes                                                   |
| --------- | ------------------ | ------------------------------------------------------- |
| Consumes  | `events.processed` | Ingestion worker writes to Postgres `events` table.     |
| Consumes  | `agents.results`   | Updates `agent_tasks.status` + audit log.               |
| Consumes  | `graph.updates`    | Server-sent events to the frontend dashboard.           |
| Publishes | `agents.tasks`     | From `/chat` and `/agents/{id}/tasks`.                  |
| Publishes | `events.raw`       | When `/integrations/ingest` is used.                    |
| Publishes | `workflows.approvals` | From `/workflows/approvals`.                         |

## Auth

JWT middleware. In `DEV_MODE=true` it short-circuits to `DEV_USER_ID` and logs:
```
Running in DEV_MODE — auth disabled
```

## Security

`packages/security-filter` is applied to `/graph`, `/agents/*` and `/chat` responses
before returning them to the user.

## Data ownership

- The API ingestion worker is the **sole writer** of the `events` table.
- The API is **read-only** on `integration_syncs`. Only `services/integrations` writes that table.

## Env vars

See `.env.example` at repo root.

## Run

```bash
# from repo root
docker compose up api

# locally
cd apps/api && poetry install && poetry run uvicorn mycelium_api.main:app --reload
```
