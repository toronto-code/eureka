# services/security

Two sub-modules:

- `classification/` — Sentra-pattern sensitive data detector. Subscribes to `events.raw`. Scans for PII, secrets, credentials. Publishes clean events to `events.processed`. On failure, retries up to `CLASSIFICATION_RETRY_LIMIT` (default 3) before publishing to `events.dlq`.
- `enforcement/` — **Lives in `packages/security-filter`.** Not a standalone service. A shared package imported by `apps/api` and `services/knowledge`.

## DLQ contract

Every message published to `events.dlq` includes:

- `error_category` (one of `mycelium_event_bus.ErrorCategory`)
- `retry_count`
- `original_event`

Never silently drop events. See `docs/contracts.md`.

## Event flow

`events.raw` is the **only** topic this service consumes. `events.processed` is the **only** topic other services consume. No service consumes `events.raw` directly except this one.

## HTTP

| Method | Path        | Notes                       |
| ------ | ----------- | --------------------------- |
| GET    | `/health`   | Standard `HealthCheck`.     |
| GET    | `/dlq`      | Recent DLQ entries.         |

## Env vars

`REDIS_URL`, `CLASSIFICATION_RETRY_LIMIT`, `DEV_MODE`.
