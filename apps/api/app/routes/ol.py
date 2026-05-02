"""OL-level lookups.

Separate from project-scoped routes because the UI sometimes knows the
run_id (from a notification, audit log, or deep-link) but not the project.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.memory.retrieval import RetrievedChunk
from app.models import OrchestratorRun, ProjectChunk
from app.schemas.api import (
    OLRunDetailOut,
    OrchestratorRunOut,
    RetrievedChunkOut,
)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/runs/{run_id}", response_model=OLRunDetailOut)
def get_orchestrator_run(run_id: str, db: Session = Depends(get_db)) -> OLRunDetailOut:
    run = db.get(OrchestratorRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

    chunks: list[RetrievedChunkOut] = []
    for chunk_id in run.retrieved_chunk_ids or []:
        row = db.get(ProjectChunk, chunk_id)
        if not row:
            continue
        chunks.append(
            RetrievedChunkOut(
                id=row.id,
                source_type=row.source_type,
                source_id=row.source_id,
                repo_id=row.repo_id,
                jira_ticket_id=row.jira_ticket_id,
                file_path=row.file_path,
                language=row.language,
                start_line=row.start_line,
                end_line=row.end_line,
                branch=row.branch,
                commit_sha=row.commit_sha,
                chunk_text=row.chunk_text,
                score=row.score or 0.0,
                semantic_score=0.0,
                keyword_score=0.0,
                recency_score=0.0,
                chunk_metadata=row.chunk_metadata or {},
            )
        )
    return OLRunDetailOut(
        run=OrchestratorRunOut.model_validate(run),
        retrieved_chunks=chunks,
    )
