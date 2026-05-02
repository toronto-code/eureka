FROM python:3.11-slim

WORKDIR /workspace

ENV POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONPATH=/workspace/packages/shared-types/python/src:/workspace/packages/db/python/src

RUN pip install --no-cache-dir poetry==${POETRY_VERSION}

COPY packages/shared-types /workspace/packages/shared-types
COPY packages/db /workspace/packages/db
COPY scripts/seed /workspace/scripts/seed

RUN pip install --no-cache-dir \
    "pydantic>=2.7,<3" \
    "sqlalchemy>=2.0" \
    "asyncpg>=0.29" \
    "psycopg[binary]>=3.1" \
    "httpx>=0.27" \
    "python-dotenv>=1.0"

CMD ["python", "/workspace/scripts/seed/seed.py"]
