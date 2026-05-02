# services/observer

Local developer-machine watcher.

> **Do not run in Docker. Run with: `poetry run python main.py`**

The observer runs on each developer's laptop. It's intentionally NOT included in `docker-compose.yml`. It watches local git activity and file change events, normalizes them into `MyceliumEvent`s, and POSTs them to the `apps/api` over HTTP.

## What we capture

- **Command name** (no arguments)
- **Repo path**
- **Timestamp**
- **List of changed filenames** (no contents)

## What we never capture

- ✗ No command arguments
- ✗ No file contents
- ✗ No stdin/stdout
- ✗ No terminal session contents
- ✗ No env vars or secrets
- ✗ No keystrokes or window titles

These constraints are non-negotiable. They are enforced in `mycelium_observer.privacy` — there is no opt-out.

## How it works

1. Watches a configurable set of directories (`OBSERVER_WATCH_DIRS`, defaults to the user's home `~/dev` if present, else nothing).
2. Subscribes to git filesystem events (`.git/HEAD`, `.git/index`, `.git/refs/heads/*`).
3. On a debounced batch of changes, computes:
   - the current command (best-effort, name only)
   - the repo path
   - the list of changed filenames (`git diff --name-only`)
4. Builds a `MyceliumEvent`:
   - `source = "observer"`
   - `type = "observer.command.run"` or `"observer.git.update"`
   - `correlation_id = derive_correlation_id(source, object_id, ...)`
5. POSTs to `${OBSERVER_API_URL}/integrations/ingest`.

## correlation_id generation

Uses rule 2 (hash + uuid suffix). Local events rarely have natural IDs and the API will fall back to assigning one if we omit it (rule 3) — but we try to set it anyway so retries are idempotent.

## Run

```bash
cd services/observer
cp ../../.env.example .env
poetry install
poetry run python main.py
```

Or:

```bash
poetry run mycelium-observer
```

## Stop

`Ctrl-C`. State is checkpointed to `.observer-state.json` in the working directory.

## Env vars

| Var                   | Default                  | Notes                                |
| --------------------- | ------------------------ | ------------------------------------ |
| `OBSERVER_API_URL`    | `http://localhost:8000`  | Where to POST events.                |
| `OBSERVER_WATCH_DIRS` | (auto-detect `~/dev`)    | Comma-separated list of directories. |
| `OBSERVER_USER_ID`    | `dev-user-1`             | Identity to attach to actor.         |
| `DEV_MODE`            | `true`                   | Logs `Running in DEV_MODE — auth disabled`. |
