# apps/frontend

React + Vite frontend.

## Views

1. **Chat** (`/chat`) — backed by `POST /chat` on the API.
2. **Dashboard** (`/`) — knowledge graph (Cytoscape.js), recent agent activity, integration sync status.

## Rules

- The frontend talks to **`apps/api` only**. Never directly to a service or database.
- Graph queries go to `GET /graph?limit=&depth=&node_id=`.
- Integration sync status comes from `GET /integrations` on the API. Never from the integrations service or Postgres.

## Run

```bash
pnpm install
pnpm --filter @mycelium/frontend dev
```

Or via Docker:

```bash
docker compose up frontend
```

The dev server listens on `:5173`. `VITE_API_URL` selects the API host (defaults to `http://localhost:8000`).
