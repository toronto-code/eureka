#!/usr/bin/env bash
# Runs the repository test suite inside Docker images so results match CI
# regardless of host Python version (requires Python >=3.11 for asyncpg/sqlalchemy stacks).
set -eo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

docker run --rm \
  -v "${ROOT}:/workspace" \
  -w /workspace \
  python:3.11-slim bash -eo pipefail -c '
pip install -q pytest pytest-asyncio \
  fastapi "uvicorn[standard]" httpx "python-jose[cryptography]" redis sqlalchemy asyncpg \
  "psycopg[binary]" neo4j pgvector pydantic prometheus-client cryptography
export PYTHONPATH=/workspace/apps/api/src:/workspace/services/agent-runtime/src:/workspace/services/learning/src:/workspace/packages/shared-types/python/src:/workspace/packages/event-bus/python/src:/workspace/packages/db/python/src:/workspace/packages/security-filter/python/src:/workspace/packages/embeddings/python/src
pytest apps/api/tests services/agent-runtime/tests services/learning/tests packages/db/python/tests packages/event-bus/python/tests packages/security-filter/python/tests -q --tb=short
'

docker run --rm \
  -v "${ROOT}:/repo" \
  -w /repo \
  node:20-bookworm-slim bash -eo pipefail -c '
corepack enable && corepack prepare pnpm@9.0.0 --activate
pnpm install --frozen-lockfile
pnpm --filter @mycelium/frontend test
'

echo "OK — Python + frontend tests passed."
