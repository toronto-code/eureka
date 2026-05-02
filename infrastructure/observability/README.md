# infrastructure/observability

Prometheus + Grafana + LangSmith.

## Metrics

Every Mycelium service exposes Prometheus metrics on `/metrics`. The standard set:

- `<service>_requests_total{path,status}`
- `<service>_request_duration_seconds_bucket{path}`
- `<service>_events_published_total{topic}`
- `<service>_events_consumed_total{topic,group}`
- `<service>_dlq_total{error_category}` (security/classification only)
- `<service>_agent_tasks_total{status}` (agent-runtime only)

These are emitted via `prometheus_client` on the Python side. The TS frontend
emits browser-side `web-vitals` to `apps/api` for now.

## What's here

- `prometheus.yml` — scrape config for the local docker-compose stack.
- `grafana/dashboards/mycelium-overview.json` — a starting dashboard.
- `langsmith.md` — how to enable agent/LLM tracing.

## LangSmith

Set `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true` in `.env`. The agent-runtime wraps OpenClaw calls in a LangSmith run automatically.
