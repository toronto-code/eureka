"""POST /onboarding/brief — produce a human-readable briefing for a service."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class BriefRequest(BaseModel):
    service: str
    audience: str = "engineer"


@router.post("/brief")
async def brief(req: BriefRequest):
    return {
        "service": req.service,
        "audience": req.audience,
        "summary": f"(stub) {req.service} is a service. Owners: ... Dependencies: ...",
        "next_steps": [
            "read the README",
            "skim recent PRs",
            "shadow the on-call rotation",
        ],
        "stub": True,
    }
