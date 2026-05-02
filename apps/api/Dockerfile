FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/apps/api/src:/workspace/packages/shared-types/python/src:/workspace/packages/event-bus/python/src:/workspace/packages/db/python/src:/workspace/packages/security-filter/python/src

COPY packages /workspace/packages
COPY apps/api /workspace/apps/api

RUN pip install \
    "fastapi>=0.111,<1" \
    "uvicorn[standard]>=0.30,<1" \
    "httpx>=0.27,<1" \
    "pydantic>=2.7,<3" \
    "python-jose[cryptography]>=3.3,<4" \
    "redis>=5.0,<6" \
    "sqlalchemy>=2.0" \
    "asyncpg>=0.29" \
    "psycopg[binary]>=3.1" \
    "alembic>=1.13" \
    "neo4j>=5.20" \
    "pgvector>=0.2.5" \
    "prometheus-client>=0.20" \
    "openai>=1.50" \
    "docker>=7.0" \
    "supabase>=2.5,<3" \
    "PyJWT>=2.8"

EXPOSE 8000

# Run migrations on startup, then the API + ingestion worker.
CMD ["bash", "-lc", "cd /workspace/packages/db/python && alembic upgrade head && cd /workspace && uvicorn mycelium_api.main:app --host 0.0.0.0 --port 8000"]
