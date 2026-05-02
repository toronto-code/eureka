"""Neo4j-backed graph store. The ONLY module in the codebase that imports
mycelium_db.neo4j_client.

If you find yourself wanting to import the Neo4j driver elsewhere, stop and
add an HTTP endpoint here instead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from mycelium_db.neo4j_client import get_neo4j_driver

logger = logging.getLogger(__name__)


async def upsert_node(node: dict[str, Any]) -> None:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        await session.run(
            """
            MERGE (n {id: $id})
            SET n.label = $label,
                n.type  = $type,
                n.source = $source,
                n.updated_at = $ts,
                n += $props
            """,
            id=node["id"],
            label=node.get("label", node["id"]),
            type=node.get("type", "concept"),
            source=node.get("source"),
            ts=datetime.now(timezone.utc).isoformat(),
            props=node.get("properties", {}),
        )


async def upsert_edge(edge: dict[str, Any]) -> None:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        await session.run(
            """
            MATCH (s {id: $source_id})
            MATCH (t {id: $target_id})
            MERGE (s)-[r:REL {id: $id}]->(t)
            SET r.type = $type,
                r.source = $source,
                r.updated_at = $ts,
                r += $props
            """,
            id=edge["id"],
            source_id=edge["source_id"],
            target_id=edge["target_id"],
            type=edge.get("type", "RELATED"),
            source=edge.get("source"),
            ts=datetime.now(timezone.utc).isoformat(),
            props=edge.get("properties", {}),
        )


async def query_subgraph(*, limit: int, depth: int, node_id: str | None) -> dict[str, Any]:
    """Return a small subgraph for the dashboard.

    If ``node_id`` is provided we expand from there to the requested depth.
    Otherwise we return the most recently updated nodes/edges up to ``limit``.
    """
    driver = get_neo4j_driver()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    async with driver.session() as session:
        if node_id:
            cypher = (
                "MATCH (n {id: $id})-[r*1..$depth]-(m) "
                "RETURN n, r, m LIMIT $limit"
            )
            res = await session.run(cypher, id=node_id, depth=depth, limit=limit)
        else:
            res = await session.run(
                "MATCH (n)-[r:REL]->(m) RETURN n, r, m ORDER BY r.updated_at DESC LIMIT $limit",
                limit=limit,
            )
        async for record in res:
            for key in ("n", "m"):
                node = record[key]
                if node is None:
                    continue
                nodes.append(
                    {
                        "id": node.get("id"),
                        "label": node.get("label", node.get("id", "?")),
                        "type": node.get("type", "concept"),
                        "properties": dict(node),
                        "source": node.get("source"),
                        "timestamp": node.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    }
                )
            r = record["r"]
            if r is not None:
                rels = r if isinstance(r, list) else [r]
                for rel in rels:
                    edges.append(
                        {
                            "id": rel.get("id", f"{rel.start_node['id']}->{rel.end_node['id']}"),
                            "source_id": rel.start_node["id"],
                            "target_id": rel.end_node["id"],
                            "type": rel.get("type", rel.type),
                            "properties": dict(rel),
                            "source": rel.get("source"),
                            "timestamp": rel.get(
                                "updated_at", datetime.now(timezone.utc).isoformat()
                            ),
                        }
                    )

    seen: set[str] = set()
    deduped_nodes = [n for n in nodes if n["id"] and not (n["id"] in seen or seen.add(n["id"]))]
    return {"nodes": deduped_nodes, "edges": edges}


# ---- DEV: seed a tiny fake company graph -----------------------------------


async def seed_demo_graph() -> dict[str, Any]:
    people = [
        {"id": "u_alice", "label": "Alice", "type": "person"},
        {"id": "u_bob", "label": "Bob", "type": "person"},
        {"id": "u_carol", "label": "Carol", "type": "person"},
    ]
    services = [
        {"id": "svc-checkout", "label": "checkout", "type": "service"},
        {"id": "svc-payments", "label": "payments", "type": "service"},
        {"id": "svc-search", "label": "search", "type": "service"},
    ]
    repos = [
        {"id": "repo-checkout", "label": "checkout (repo)", "type": "repo"},
        {"id": "repo-payments", "label": "payments (repo)", "type": "repo"},
    ]

    edges = [
        {"id": "e1", "source_id": "u_alice", "target_id": "svc-checkout", "type": "OWNS"},
        {"id": "e2", "source_id": "u_bob", "target_id": "svc-payments", "type": "OWNS"},
        {"id": "e3", "source_id": "u_carol", "target_id": "svc-search", "type": "OWNS"},
        {"id": "e4", "source_id": "svc-checkout", "target_id": "svc-payments", "type": "DEPENDS_ON"},
        {"id": "e5", "source_id": "svc-checkout", "target_id": "repo-checkout", "type": "BACKED_BY"},
        {"id": "e6", "source_id": "svc-payments", "target_id": "repo-payments", "type": "BACKED_BY"},
    ]

    for n in [*people, *services, *repos]:
        n.setdefault("source", "seed")
        await upsert_node(n)
    for e in edges:
        e.setdefault("source", "seed")
        await upsert_edge(e)

    return {"nodes": len(people) + len(services) + len(repos), "edges": len(edges)}
