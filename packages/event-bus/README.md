# @mycelium/event-bus

Redis Streams-backed event bus. **Not** plain Redis pub/sub — we need durability, ack, retry, and consumer groups.

## Topics

| Topic                  | Producers                       | Consumers                                  |
| ---------------------- | ------------------------------- | ------------------------------------------ |
| `events.raw`           | `observer`, `integrations`      | `security/classification` only             |
| `events.processed`     | `security/classification`       | `apps/api` ingestion worker, `knowledge`, `process-intel` |
| `events.dlq`           | `security/classification`       | (operator inspection)                      |
| `agents.tasks`         | `apps/api`, workflows           | `agent-runtime`                            |
| `agents.results`       | `agent-runtime`                 | `apps/api`, `learning`                     |
| `workflows.approvals`  | `apps/api`                      | `agent-runtime`, `learning`                |
| `graph.updates`        | `knowledge`, `process-intel`    | `apps/api`                                 |

## Ordering guarantee

**Ordering is guaranteed per `correlation_id` stream partition only.** We achieve this by routing each event to a partition keyed by `correlation_id`. Consumers must never assume global ordering across partitions. See `docs/contracts.md`.

## API

Both Python and TypeScript clients expose the same shape:

```python
publish(topic, event, *, correlation_id)          # routes to a partition
consume(topic, group, consumer_name, handler)     # XREADGROUP loop
ack(topic, group, message_id)                     # XACK
retry(topic, group, message_id)                   # claim + requeue
```

## DLQ

`security/classification` retries each event up to `CLASSIFICATION_RETRY_LIMIT` (default 3) before publishing to `events.dlq`. DLQ messages include:

- `error_category`
- `retry_count`
- `original_event`

Never silently drop events.

## Python install

```toml
mycelium-event-bus = { path = "../../packages/event-bus/python", develop = true }
```

## TypeScript install

```json
{ "dependencies": { "@mycelium/event-bus": "workspace:*" } }
```
