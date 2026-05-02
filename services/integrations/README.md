# services/integrations

Connectors to external tools. Each connector:

- Pulls data on a schedule.
- Normalizes into the `MyceliumEvent` schema.
- Assigns `correlation_id` (priority order: natural ID → hash + uuid suffix).
- Publishes to `events.raw` on the event bus **only** — never directly into Postgres.
- After every sync, **writes `integration_syncs`** with `last_sync_at`, `status`, `error_message`. This service is the **sole writer** of that table.

Composio is used for auth + API handling where possible.

## Connectors

- `github/` — PR opened/reviewed/merged, push, issue events.
- `slack/` — message posted, edited, threaded reply.
- `jira/` — ticket created, transitioned, commented.

## Event bus

| Direction | Topic        | Notes                                     |
| --------- | ------------ | ----------------------------------------- |
| Publishes | `events.raw` | All connectors. Only consumer is `security/classification`. |

## HTTP

| Method | Path                          | Notes                                            |
| ------ | ----------------------------- | ------------------------------------------------ |
| GET    | `/health`                     | Standard `HealthCheck`.                          |
| POST   | `/connectors/{name}/sync`     | Force a sync. Useful for tests.                  |
| GET    | `/connectors`                 | List configured connectors.                      |

## Database ownership

This service is the **sole writer** of the `integration_syncs` table. The API
is read-only on that table. No other service writes to it.

## Env vars

`COMPOSIO_API_KEY`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `SLACK_BOT_TOKEN`,
`SLACK_SIGNING_SECRET`, `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
`INTEGRATIONS_SYNC_INTERVAL`.

## DEV_MODE

In `DEV_MODE=true`, connectors run on a fast schedule and emit a small set of fake events (so the frontend has data without configuring real external tokens).
