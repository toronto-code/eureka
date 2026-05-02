# services/knowledge

The company brain. **Sole owner of Neo4j** — no other service reads or writes Neo4j directly.

## Sub-modules

- `graph/` — Graphiti integration. Ingests events and builds the temporal knowledge graph. Every fact stored with timestamp + source.
- `code-index/` — GitNexus / CodeGraphContext. Tree-sitter-based structural code graph. Exposes: who owns what, blast radius, dependency graph.
- `onboarding/` — Understand-Anything integration. Given a service name, produces a human-readable briefing.

## Event bus

| Direction | Topic              | Notes                                                |
| --------- | ------------------ | ---------------------------------------------------- |
| Consumes  | `events.processed` | Builds the temporal graph from clean events.         |
| Publishes | `graph.updates`    | Whenever a node/edge is added or changed.            |

## HTTP

| Method | Path                    | Notes                                                |
| ------ | ----------------------- | ---------------------------------------------------- |
| GET    | `/health`               | Standard `HealthCheck`.                              |
| GET    | `/graph`                | Query: `limit`, `depth`, `node_id`. Pebblo filter applied to agent-mode queries. |
| POST   | `/code-index/index`     | Index or re-index a repo.                            |
| GET    | `/code-index/owners`    | Who owns what.                                       |
| GET    | `/code-index/blast`     | Blast radius for a path.                             |
| POST   | `/onboarding/brief`     | Produce a human-readable briefing.                   |
| POST   | `/seed`                 | DEV: seed a fake company graph.                      |

## Pebblo enforcement

`packages/security-filter` is applied to all **agent** queries before returning results. User-facing queries are filtered at the API gateway. We apply the filter at both layers — defense in depth — using the same shared library.

## Env vars

`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `REDIS_URL`, `POSTGRES_DSN`, `DEV_MODE`.
