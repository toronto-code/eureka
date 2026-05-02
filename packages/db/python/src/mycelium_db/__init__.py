"""Database clients for Mycelium services.

Two clients live here:

- Postgres (sqlalchemy async) — used by every service that needs the system of
  record. Ownership rules (which service writes which table) are documented
  in the package README and enforced by code review.
- Neo4j — imported ONLY by services/knowledge. Do not import this client from
  any other service.
"""

from mycelium_db.postgres import PostgresClient, get_postgres_engine, get_session
from mycelium_db.models import (
    AgentMemoryRow,
    AgentRow,
    AgentTaskRow,
    AuditRow,
    Base,
    DocumentEmbeddingRow,
    EventRow,
    IntegrationSyncRow,
    LearningSignalRow,
)

__all__ = [
    "AgentMemoryRow",
    "AgentRow",
    "AgentTaskRow",
    "AuditRow",
    "Base",
    "DocumentEmbeddingRow",
    "EventRow",
    "IntegrationSyncRow",
    "LearningSignalRow",
    "PostgresClient",
    "get_postgres_engine",
    "get_session",
]
