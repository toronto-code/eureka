# mycelium-security-filter

Pebblo-pattern enforcement library. **Not a service — a shared package.**

Imported by:

- `apps/api` — applied to user-facing queries.
- `services/knowledge` — applied to agent queries before returning results.

## What it does

Given a query (a string or a structured `QueryContext`) and a set of result rows
(graph nodes/edges, document chunks, fact rows), it:

1. Filters out items whose `sensitivity_level` exceeds the caller's clearance.
2. Redacts inline secrets (API keys, tokens, emails when policy demands it).
3. Records an enforcement decision in the audit log via callback.

In `DEV_MODE=true` (with `SECURITY_ENFORCEMENT_ENABLED=false`) the filter
short-circuits to a permissive identity function and logs a warning so it's
obvious in dev.

## Python

```python
from mycelium_security_filter import SecurityFilter, QueryContext

flt = SecurityFilter.from_env()
allowed = flt.filter(rows, context=QueryContext(user_id="u_1", role="employee"))
```
