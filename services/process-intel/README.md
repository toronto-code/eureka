# services/process-intel

`pm4py`-based process mining. Reads from the **Postgres `events` table** — not from Redis. Redis is transport; Postgres is the system of record.

## What it does

- Runs process discovery on a schedule.
- Outputs process maps, bottleneck reports, deviation alerts.
- Publishes results to `graph.updates` so the knowledge service can attach them.

## Event bus

| Direction | Topic           | Notes                                |
| --------- | --------------- | ------------------------------------ |
| Publishes | `graph.updates` | Process maps, deviations, bottlenecks. |

## HTTP

| Method | Path             | Notes                                       |
| ------ | ---------------- | ------------------------------------------- |
| GET    | `/health`        | Standard `HealthCheck`.                     |
| POST   | `/discover`      | Force a discovery run on demand.            |
| GET    | `/process-maps`  | Latest discovered process maps.             |

## Env vars

`POSTGRES_DSN`, `REDIS_URL`, `DEV_MODE`.
