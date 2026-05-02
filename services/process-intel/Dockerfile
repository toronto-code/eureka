FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/services/process-intel/src:/workspace/packages/shared-types/python/src:/workspace/packages/event-bus/python/src:/workspace/packages/db/python/src

COPY packages /workspace/packages
COPY services/process-intel /workspace/services/process-intel

# pm4py pulls in heavy deps (numpy/pandas/graphviz). Keep it optional so the
# container builds quickly in DEV; the discovery code degrades gracefully.
RUN pip install \
    "fastapi>=0.111,<1" \
    "uvicorn[standard]>=0.30,<1" \
    "pydantic>=2.7,<3" \
    "redis>=5.0,<6" \
    "sqlalchemy>=2.0" \
    "asyncpg>=0.29" \
    "psycopg[binary]>=3.1"

EXPOSE 8004

CMD ["uvicorn", "mycelium_process_intel.main:app", "--host", "0.0.0.0", "--port", "8004"]
