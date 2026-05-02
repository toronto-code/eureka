FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/services/knowledge/src:/workspace/packages/shared-types/python/src:/workspace/packages/event-bus/python/src:/workspace/packages/db/python/src:/workspace/packages/security-filter/python/src:/workspace/packages/embeddings/python/src

COPY packages /workspace/packages
COPY services/knowledge /workspace/services/knowledge

RUN pip install \
    "fastapi>=0.111,<1" \
    "uvicorn[standard]>=0.30,<1" \
    "httpx>=0.27,<1" \
    "pydantic>=2.7,<3" \
    "redis>=5.0,<6" \
    "sqlalchemy>=2.0" \
    "asyncpg>=0.29" \
    "psycopg[binary]>=3.1" \
    "neo4j>=5.20"

EXPOSE 8001

CMD ["uvicorn", "mycelium_knowledge.main:app", "--host", "0.0.0.0", "--port", "8001"]
