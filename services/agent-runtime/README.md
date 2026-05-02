# services/agent-runtime

OpenClaw-based agent execution layer. One OpenClaw instance per employee, managed via Claworc.

## Responsibilities

- Receive a task → execute → return result + audit log entry
- Maintain a basic skill registry — see `src/mycelium_agent_runtime/skills`
- Query the knowledge service via internal HTTP. **Never touch Neo4j or Postgres directly.**

## Event bus

| Direction | Topic            | Notes                                                |
| --------- | ---------------- | ---------------------------------------------------- |
| Consumes  | `agents.tasks`   | Tasks dispatched by API or workflows.                |
| Publishes | `agents.results` | Final outcome (`succeeded` / `failed`).              |

## HTTP

| Method | Path                | Notes                                          |
| ------ | ------------------- | ---------------------------------------------- |
| GET    | `/health`           | Standard `HealthCheck` shape.                  |
| GET    | `/skills`           | List registered skills.                        |
| POST   | `/agents/spawn`     | Create an OpenClaw instance (one per employee). |

## Env vars

`OPENCLAW_API_KEY`, `CLAWORC_API_KEY`, `KNOWLEDGE_URL`, `REDIS_URL`, `POSTGRES_DSN`, `DEV_MODE`.

## DEV_MODE

When `DEV_MODE=true`, agent execution is stubbed: it sleeps briefly and emits a fake "succeeded" result so the rest of the pipeline can be developed without API keys.
