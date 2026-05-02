"""BaseLane + LaneContext.

A lane is one-shot: given a request + classification + retrieved chunks,
produce a structured `LaneResult`. Lanes may perform GitHub/Jira writes;
they never mutate OL state directly — the OL service persists the result.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.ol.schemas import LaneResult, LaneStep, OLClassification, OLRequest
from app.memory.retrieval import RetrievedChunk


@dataclass
class LaneContext:
    session: Session
    request: OLRequest
    classification: OLClassification
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)

    def add_step(self, result: LaneResult, label: str, detail: str | None = None, ok: bool = True) -> None:
        result.steps.append(
            LaneStep(
                at=datetime.now(tz=timezone.utc).isoformat(),
                label=label,
                detail=detail,
                ok=ok,
            )
        )


class BaseLane(ABC):
    """Lane contract. Implementations: Inquiry, SimpleCode, ComplexCode, Planning, Blocked, HumanReview."""

    name: str = "base"

    @abstractmethod
    def run(self, ctx: LaneContext) -> LaneResult: ...

    @staticmethod
    def _empty_result(lane_name: str) -> LaneResult:
        return LaneResult(
            lane=lane_name,
            status="running",
            summary="",
            details=None,
        )

    @staticmethod
    def _citations_from(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
        out: list[dict[str, Any ]] = []
        for c in chunks[:10]:
            label = c.file_path or c.source_type
            if c.start_line and c.end_line:
                label = f"{label}:{c.start_line}-{c.end_line}"
            out.append(
                {
                    "chunk_id": c.id,
                    "source_type": c.source_type,
                    "label": label,
                    "score": c.score,
                }
            )
        return out
