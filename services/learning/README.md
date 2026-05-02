# services/learning

OpenClaw-RL integration. **Observe-only.** This service does NOT intercept or proxy agent calls.

## What it does

- Subscribes to `agents.results` and `workflows.approvals`.
- When a human overrides or corrects an agent action, logs it as a training signal to Postgres (`learning_signals`).
- Full RL implementation comes later — this scaffold just wires the data pipeline.

## Event bus

| Direction | Topic                  | Notes                                |
| --------- | ---------------------- | ------------------------------------ |
| Consumes  | `agents.results`       | All agent outcomes.                  |
| Consumes  | `workflows.approvals`  | Human approval / rejection / override. |
| Publishes | (none)                 | Learning signals are written to Postgres only. |

## HTTP

| Method | Path        | Notes                                                        |
| ------ | ----------- | ------------------------------------------------------------ |
| GET    | `/health`   | Standard `HealthCheck`.                                      |
| GET    | `/signals`  | Recent training signals collected. Useful for the dashboard. |

## Env vars

`POSTGRES_DSN`, `REDIS_URL`, `DEV_MODE`.
