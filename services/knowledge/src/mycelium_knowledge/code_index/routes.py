"""Code index endpoints (stubs).

Real implementation: walks a repo with Tree-sitter, builds a structural code
graph, and stores it in Neo4j alongside the temporal graph.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class IndexRequest(BaseModel):
    repo_url: str
    ref: str = "HEAD"


@router.post("/index")
async def index_repo(req: IndexRequest):
    return {"repo_url": req.repo_url, "ref": req.ref, "status": "queued", "stub": True}


@router.get("/owners")
async def owners(path: str | None = None):
    return {
        "path": path,
        "owners": [
            {"user_id": "u_alice", "ownership": 0.6, "stub": True},
            {"user_id": "u_bob", "ownership": 0.3, "stub": True},
        ],
        "stub": True,
    }


@router.get("/blast")
async def blast_radius(path: str):
    return {
        "path": path,
        "affected_services": ["svc-checkout", "svc-payments"],
        "affected_owners": ["u_alice", "u_bob"],
        "stub": True,
    }


@router.get("/deps")
async def dep_graph(repo: str | None = None):
    return {
        "repo": repo,
        "dependencies": [
            {"from": "svc-checkout", "to": "svc-payments"},
            {"from": "svc-checkout", "to": "svc-search"},
        ],
        "stub": True,
    }
