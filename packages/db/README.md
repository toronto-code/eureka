# mycelium-db

Database clients and Alembic migrations.

## Postgres (system of record)

PostgreSQL 16 + `pgvector`. Migrations are in `alembic/versions/` and run automatically on `docker compose up` (the API container's entrypoint runs `alembic upgrade head` before starting uvicorn).

### Migration chain

| Revision | What it does |
| --- | --- |
| `0001_init` | All 6 base tables + their indexes + `CREATE EXTENSION vector` |
| `0002_add_vectors` | `events.embedding vector(1536)` (nullable), `document_embeddings` table, IVFFlat cosine indexes |
| `0003_updated_at_triggers` | Postgres trigger on `agent_tasks` + `integration_syncs` to keep `updated_at` correct even for raw-SQL writes |

### Tables

- `events` — all normalized `MyceliumEvent`s (written by API ingestion worker, read by `process-intel`)
- `integration_syncs` — connector, last_sync_at, status, error_message (**written only by `services/integrations`**, read by API)
- `agents`, `agent_tasks`, `audit_log`, `learning_signals`
- `document_embeddings` — text chunks embedded by `services/knowledge` for semantic search
- LangGraph checkpointing (add a migration when ready)

### pgvector notes

- Extension: `CREATE EXTENSION IF NOT EXISTS vector` (migration 0001).
- Embedding columns: `events.embedding vector(1536)` and `document_embeddings.embedding vector(1536)` (migration 0002).
- Index type: `IVFFlat` with `lists=10` — right-sized for ≤100k rows (small company). Upgrade to `HNSW` or more lists if the dataset grows.
- All similarity queries use **cosine distance** (`<=>` operator).
- Change `EMBEDDING_DIM` in `models.py` and `0002_add_vectors.py` together, then write a new migration.

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
