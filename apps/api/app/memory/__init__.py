"""Memory abstraction.

Default backend is Postgres + pgvector. The interface is intentionally generic so
Graphiti, Neo4j, FalkorDB, Qdrant, Pinecone, or Weaviate can drop in later.
"""

from app.memory.base import MemoryBackend, PostgresMemoryBackend, get_memory

__all__ = ["MemoryBackend", "PostgresMemoryBackend", "get_memory"]
