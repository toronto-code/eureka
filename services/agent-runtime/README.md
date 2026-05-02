# services/agent-runtime

Agent execution layer with pluggable backends. Supports local execution (dev) and OpenClaw/Claworc (production).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Runtime Service                     │
├─────────────────────────────────────────────────────────────┤
│  Task Worker                                                 │
│    ↓                                                         │
│  Skill Registry → execute skill with context                 │
│    ↓                                                         │
│  Action Executor → propose actions                           │
│    ↓                                                         │
│  Permission Guard → check allowlist/blocklist                │
│    ↓ (if requires_approval)                                  │
│  Learning Client → ask learning service for user preference  │
│    ↓ (if suggestion=auto & confidence≥0.5 → bypass approval) │
│  Execution Backend → LocalBackend | OpenClawBackend          │
└─────────────────────────────────────────────────────────────┘
```

## Responsibilities

- Receive tasks from `agents.tasks` → execute via skills → publish results to `agents.results`
- Permission-based action control (Cursor-style allowlist/blocklist)
- Pluggable execution backends (local dev, OpenClaw production)
- Query knowledge service via HTTP. **Never touch Neo4j or Postgres directly.**

## Key Components

### Permissions (`permissions/`)

Three-tier permission system for agent actions:

| Level | Behavior | Examples |
|-------|----------|----------|
| `auto` | Execute immediately | `ls`, `cat`, `git status`, read files |
| `requires_approval` | Queue for human approval | `rm`, `git push`, write files |
| `blocked` | Never allow | `sudo`, secrets access |

### Learning integration (`learning_client.py`)

When an action falls in `requires_approval`, the executor asks the learning
service for a learned preference for `(user_id, action_type)`:

- `suggestion="auto"` with `confidence ≥ 0.5` → bypass the approval gate
- `suggestion="blocked"` with `confidence ≥ 0.7` → block the action
- anything else → normal approval flow (human review)

Hard-blocked rules (e.g. `sudo`) always win — learned preferences cannot
override safety rules.

Env vars:
- `LEARNING_URL` (default `http://learning:8005`)
- `LEARNING_ENABLED` (default `true`; set `false` to disable lookups)
- `LEARNING_TIMEOUT` (default `2.0` seconds; fails open if learning is down)

### Execution Backends (`execution/`)

- **LocalBackend** — runs actions in-process (shell, file ops, git, HTTP)
- **OpenClawBackend** — delegates to OpenClaw API (production)

Set `EXECUTION_BACKEND=local` or `EXECUTION_BACKEND=openclaw`.

### Skills (`skills/`)

| Skill | Description |
|-------|-------------|
| `project_orchestrator` | Top-level orchestrator: reads `project_data`, plans a team, runs specialist skills |
| `shell` | Execute shell commands |
| `file_ops` | Read/write/delete files |
| `git` | Git version control |
| `search` | Grep/find files |
| `reasoning` | Plan multi-step tasks |
| `summarize` | Summarize content |

### Agent personas (`agents/catalog.py`)

Logical roles (orchestrator + specialists). List at **GET `/agents/personas`**. The orchestrator skill delegates to `reasoning`, `plan`, `summarize`, `onboard`, etc., using keyword routing until an LLM planner is wired.

## Event Bus

| Direction | Topic | Notes |
|-----------|-------|-------|
| Consumes | `agents.tasks` | Tasks from API or workflows |
| Publishes | `agents.results` | Outcome (`succeeded`/`failed`/`pending_approval`) |

## HTTP Endpoints

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Standard `HealthCheck` shape |
| GET | `/skills` | List registered skills |
| GET | `/permissions` | List permission rules |
| POST | `/agents/spawn` | Create an OpenClaw instance |
| POST | `/actions/check` | Check if an action would be allowed |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXECUTION_BACKEND` | `local` | `local` or `openclaw` |
| `WORKING_DIRECTORY` | `/tmp/agent-workspace` | Sandbox directory for local execution |
| `OPENCLAW_API_KEY` | - | OpenClaw API key (production) |
| `OPENCLAW_API_URL` | `https://api.openclaw.ai` | OpenClaw API endpoint |
| `CLAWORC_API_KEY` | - | Claworc API key (production) |
| `CLAWORC_API_URL` | `https://api.claworc.ai` | Claworc API endpoint |
| `KNOWLEDGE_URL` | `http://knowledge:8001` | Knowledge service URL |
| `REDIS_URL` | `redis://redis:6379/0` | Redis for event bus |
| `DEV_MODE` | `true` | Enable dev mode (relaxed auth) |

## DEV_MODE

When `DEV_MODE=true`:
- Auth is disabled
- LocalBackend is used by default
- Skills return real results (via local execution) instead of stubs
