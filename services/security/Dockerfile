FROM python:3.11-slim

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/services/security/src:/workspace/packages/shared-types/python/src:/workspace/packages/event-bus/python/src:/workspace/packages/security-filter/python/src

COPY packages /workspace/packages
COPY services/security /workspace/services/security

RUN pip install \
    "fastapi>=0.111,<1" \
    "uvicorn[standard]>=0.30,<1" \
    "pydantic>=2.7,<3" \
    "redis>=5.0,<6"

EXPOSE 8006

CMD ["uvicorn", "mycelium_security.main:app", "--host", "0.0.0.0", "--port", "8006"]
