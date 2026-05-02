# apps/api

The Mycelium API gateway. **The only thing the frontend talks to.**

## Endpoints

| Method | Path                     | Notes                                                   |
| ------ | ------------------------ | ------------------------------------------------------- |
| GET    | `/health`                | Standard `HealthCheck` shape (see shared-types).        |
| POST   | `/chat`                  | Inserts `agent_tasks` (`queued`), then publishes to `agents.tasks`. Response includes `agent_id` + `task_id` for polling. |
| GET    | `/graph`                 | Query knowledge graph. Params: `limit`, `depth`, `node_id`. |
| GET    | `/agents`                | List agents owned by the current user.                  |
| POST   | `/agents/{id}/tasks`     | Inserts task row (`queued`), then publishes to Redis. Agents are created lazily when missing (owned by caller). |
| GET    | `/agents/{id}/tasks`      | Recent tasks for that agent (404 if caller does not own the agent). |
| GET    | `/agents/{id}/tasks/{task_id}` | Read one task (`result`/`error` when terminal).   |
| GET    | `/integrations`          | Read `integration_syncs` (read-only on this table).     |
| POST   | `/integrations/ingest`   | Producer entrypoint for events that don't go via the bus directly. Adds correlation_id fallback (rule 3). |
| GET    | `/workflows`             | List active workflows.                                  |
| POST   | `/workflows/approvals`   | Submit a human approval. Publishes to `workflows.approvals`. |
| GET    | `/observability`         | Service health summary scraped from each `/health`.     |

## Event bus

| Direction | Topic              | Notes                                                   |
| --------- | ------------------ | ------------------------------------------------------- |
| Consumes  | `events.processed` | Ingestion worker writes to Postgres `events` table.     |
| Consumes  | `agents.results`   | Updates existing `agent_tasks` rows (+ audit log). Rows must exist before Redis dispatch — done by `/chat` and `/agents/{id}/tasks`. |
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

`packages/security-filter` is applied inside `GET /graph` when merging knowledge graph
responses for the caller. Other routes bypass that filter unless added explicitly.

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
