"""Neo4j client.

IMPORTANT: This module must only be imported by services/knowledge.
Other services must query the knowledge service via HTTP — they must not
touch Neo4j directly.
"""

from __future__ import annotations

import os

from neo4j import AsyncDriver, AsyncGraphDatabase


_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "mycelium-neo4j")
        _driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return _driver


async def close_neo4j_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
