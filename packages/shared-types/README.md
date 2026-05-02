# @mycelium/shared-types

The contract between every Mycelium service. Both Python (Pydantic v2) and TypeScript bindings.

> **Get these right — changing them later is painful.**

## Schemas

- `MyceliumEvent` — every observed/emitted event in the system.
- `Agent` — an agent instance bound to an employee.
- `AgentTask` — a unit of work dispatched to an agent.
- `WorkflowState` — current state of a multi-step workflow.
- `AuditEntry` — an immutable record of an agent action.
- `GraphNode` / `GraphEdge` — knowledge graph primitives.
- `HealthCheck` — identical shape across all services.

See `docs/contracts.md` for plain-English documentation.

## Python

```python
from mycelium_shared_types import MyceliumEvent, AgentTask, HealthCheck
```

Install (from a Python service):

```toml
# pyproject.toml
[tool.poetry.dependencies]
mycelium-shared-types = { path = "../../packages/shared-types/python", develop = true }
```

## TypeScript

```ts
import type { MyceliumEvent, AgentTask, HealthCheck } from "@mycelium/shared-types";
```

Install (workspace):

```json
{ "dependencies": { "@mycelium/shared-types": "workspace:*" } }
```

## Versioning

`schema_version` is mandatory on every `MyceliumEvent`. Default `"1.0"`. Bump it when fields are added/changed. Consumers must handle unknown versions gracefully (log + best-effort parse). All changes are recorded in `docs/contracts.md`.
