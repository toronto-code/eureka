# services/learning

Evolution + Learning service. Collects signals from agent activity, trains models on three axes (permissions, skills, action patterns), and serves recommendations back to the agent runtime.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Learning Service                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Event Bus Consumers                                             │
│    ├─ agents.results      ─→                                     │
│    └─ workflows.approvals ─→    Signal Collector                 │
│                                       ↓                          │
│                                  Signal Buffer                   │
│                              (N signals OR T minutes)            │
│                                       ↓                          │
│                                  Trainer                         │
│                                       ↓                          │
│                            Learning Backend                      │
│                      (LocalBackend | OpenClawRL/Genverse)        │
│                                       ↓                          │
│                     ┌─────────────────┼──────────────────┐       │
│                     ↓                 ↓                  ↓       │
│               PermissionModel   SkillModel        PatternModel   │
│                     ↓                 ↓                  ↓       │
│                     └─── Model Store (Redis) ←───────────┘       │
│                                       ↓                          │
│                         HTTP API (queries)                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## What it does

**Signal sources** (all normalized to one `Signal` shape):
- `agents.results` → TASK_RESULT signals (success/failure per skill)
- `workflows.approvals` → APPROVAL_DECISION signals (approve/reject per action)
- `POST /signals/feedback` → USER_FEEDBACK signals (thumbs up/down)

**Approval request/decision join**: The agent-runtime publishes approval
*requests* (`decision="requested"`) with `pending_actions`. The API publishes
decisions (`decision="approve|reject"`) with only a `workflow_id`. The
`SignalCollector` caches requests (TTL 7d) and joins them with decisions so
the `PermissionModel` learns per `action_type`, not just per workflow.

**Trigger model**: Event-driven with cooldown. Flushes the buffer when *either*:
- `LEARNING_BATCH_SIZE` signals accumulate (default 10), OR
- `LEARNING_BATCH_INTERVAL_SECONDS` elapses (default 900s / 15 min)

**Three models** (per user + global):
- `PermissionModel` — approval rate per action type → auto/approve/block suggestions
- `SkillModel` — success rate per skill → skill recommendations
- `PatternModel` — action patterns → top-performing action sets

**Pluggable backend**:
- `LocalBackend` — frequency-based updates with recency weighting (default)
- `OpenClawRLBackend` — ships signals to OpenClaw RL + Genverse for real RL (stub until API keys)

## Event Bus

| Direction | Topic | Notes |
|-----------|-------|-------|
| Consumes | `agents.results` | All agent task outcomes |
| Consumes | `workflows.approvals` | Human approval/rejection decisions |
| Publishes | (none) | Output is via HTTP API |

## HTTP Endpoints

### Health / Stats
| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Standard `HealthCheck` |
| GET | `/stats` | Service stats: buffer, trainer, backend |

### Preferences (permission learning)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/preferences/global` | Org-wide permission suggestions |
| GET | `/preferences/global/actions/{action_type}` | Suggestion for one action (global) |
| GET | `/preferences/users/{user_id}` | All suggestions for a user |
| GET | `/preferences/users/{user_id}/actions/{action_type}` | Suggestion for one action (user) |

### Recommendations (skill + pattern learning)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/recommendations/skills` | Ranked skills (query: `user_id`, `candidates`, `top_n`) |
| GET | `/recommendations/patterns` | Top action patterns |
| GET | `/recommendations/models/{kind}` | Full summary for `permissions`/`skills`/`patterns` |

### Signals
| Method | Path | Notes |
|--------|------|-------|
| GET | `/signals` | List recent signals from Postgres |
| POST | `/signals/feedback` | Submit user feedback (thumbs up/down) |
| GET | `/signals/buffer` | Buffer stats |
| POST | `/signals/flush` | Manually trigger flush (debugging) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LEARNING_BACKEND` | `local` | `local` or `openclaw` |
| `LEARNING_BATCH_SIZE` | `10` | Flush after this many signals |
| `LEARNING_BATCH_INTERVAL_SECONDS` | `900` | Flush after this many seconds (15 min) |
| `LEARNING_MIN_SIGNALS` | `5` | Minimum signals before recommendations |
| `LEARNING_MIN_DECISIONS` | `5` | Minimum decisions before auto-approve suggestions |
| `LEARNING_AUTO_APPROVE_THRESHOLD` | `0.9` | Approval rate above which to suggest auto |
| `LEARNING_AUTO_BLOCK_THRESHOLD` | `0.1` | Approval rate below which to suggest blocked |
| `LEARNING_RECENT_WEIGHT` | `2.0` | Boost for recent signals |
| `LEARNING_RECENT_WINDOW_HOURS` | `24` | Recency window |
| `LEARNING_MODEL_CACHE_TTL` | `3600` | Redis TTL for model state |
| `OPENCLAW_RL_API_KEY` | - | OpenClaw RL API key |
| `OPENCLAW_RL_API_URL` | `https://api.openclaw.ai/rl` | OpenClaw RL endpoint |
| `GENVERSE_API_KEY` | - | Genverse API key |
| `GENVERSE_API_URL` | `https://api.genverse.ai` | Genverse endpoint |
| `REDIS_URL` | `redis://redis:6379/0` | Redis for event bus + model store |
| `POSTGRES_DSN` | - | Postgres for signal persistence |
| `DEV_MODE` | `true` | Dev mode (relaxed auth) |

## Integration with agent-runtime

Agent-runtime can query preferences to adapt its behavior:

```python
# Should this action be auto-approved for this user?
resp = await httpx.get(
    f"{LEARNING_URL}/preferences/users/{user_id}/actions/shell_command"
)
suggestion = resp.json()["suggestion"]  # "auto" | "requires_approval" | "blocked" | "insufficient_data"
```

When `suggestion == "auto"` with high confidence, agent-runtime can add
that action to the guard's auto-allow list for that user.
