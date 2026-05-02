# Mycelium

A company-wide agentic intelligence layer that observes how a software company works, builds a living knowledge graph, and deploys agents that can act on that knowledge autonomously or on demand.

> Status: scaffolding. Goal is structure + wiring, not business logic.
> Target scale: ~10 developers. Simple > clever.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

This starts everything except the `services/observer` (which runs locally on developer machines — see `services/observer/README.md`).

After the stack is up:

- API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:5173
- Postgres: localhost:5432
- Neo4j browser: http://localhost:7474
- Redis: localhost:6379

A seed script populates fake events, a fake company graph, fake `integration_syncs` rows, and fake agent activity so the UI is non-empty on first run.

## Layout

```
mycelium/
├── apps/
│   ├── frontend/          React + Vite. Chat + dashboard.
│   └── api/               FastAPI gateway. The only thing the frontend talks to.
├── services/
│   ├── observer/          Local dev-machine watcher. NOT in Docker.
│   ├── agent-runtime/     OpenClaw + Claworc. One agent per employee.
│   ├── knowledge/         Sole owner of Neo4j. graph/, code-index/, onboarding/.
│   ├── integrations/      GitHub, Slack, Jira connectors. Sole writer of integration_syncs.
│   ├── process-intel/     pm4py over Postgres events.
│   ├── learning/          OpenClaw-RL feedback observer.
│   └── security/          classification (Sentra-pattern). enforcement is a package.
├── packages/
│   ├── shared-types/      Pydantic + TypeScript contracts.
│   ├── event-bus/         Redis Streams client. publish/consume/ack/retry.
│   ├── db/                Postgres + Neo4j clients + Alembic migrations.
│   └── security-filter/   Pebblo-pattern enforcement library.
├── infrastructure/
│   ├── gcloud/            Cloud Run, Cloud SQL, Memorystore, Artifact Registry.
│   └── observability/     Prometheus, Grafana, LangSmith.
├── docs/
│   ├── architecture.md
│   ├── data-flow.md
│   └── contracts.md
├── docker-compose.yml
└── .env.example
```

## Implementation rules (read before changing anything)

1. Frontend talks to API. Never to a service. Never to a database.
2. Services may HTTP-call each other for queries. Never read each other's databases.
3. Events flow: producer → `events.raw` → `security/classification` → `events.processed` → consumers.
4. Redis is **transport**. Postgres is the **system of record**.
5. `services/knowledge` is the sole owner of Neo4j.
6. `services/integrations` is the sole writer of `integration_syncs`.
7. The API ingestion worker is the sole writer of the `events` table.
8. `correlation_id` is mandatory. `parent_correlation_id` is set for any event that modifies/extends a prior event.
9. `schema_version` is mandatory. Default `"1.0"`. Bump on field changes. Document in `docs/contracts.md`.
10. Event ordering is per `correlation_id` partition only. Never global.
11. AgentTask lifecycle is strict: `queued → running → succeeded | failed → retried → succeeded | cancelled`. No skipping.
12. Observer captures only: command name (no args), repo path, timestamp, changed filenames (no contents).
13. `DEV_MODE=true` is the default. Every service logs `Running in DEV_MODE — auth disabled` at startup.
14. Stub, don't skip. Return realistic fake data for unbuilt dependencies.

See `docs/contracts.md` for the full contract.
