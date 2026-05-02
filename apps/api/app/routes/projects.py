"""Project-scoped endpoints: list projects, run OL, list runs, search, sync."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.memory.project_data import ProjectDataService
from app.memory.retrieval import RetrievalQuery
from app.models import OrchestratorRun, Project
from app.schemas.api import (
    OLRunDetailOut,
    OLRunRequest,
    OLSearchRequest,
    OLSearchResponse,
    OrchestratorRunOut,
    ProjectOut,
    RetrievedChunkOut,
    SyncResultOut,
)
from app.services.local_user_data_store import (
    list_orchestrator_run_snapshots,
    save_orchestrator_run_snapshot,
)
from app.services.ol_service import OLService
from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    rows = db.execute(select(Project).order_by(desc(Project.created_at))).scalars().all()
    if not rows and get_settings().enable_demo_seed:
        # Self-heal when startup seeding was skipped (e.g. DB not ready at boot).
        from app.seed import seed_database

        seed_database(db)
        rows = db.execute(select(Project).order_by(desc(Project.created_at))).scalars().all()
    return [ProjectOut.model_validate(p) for p in rows]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    return ProjectOut.model_validate(p)


# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------


@router.post("/{project_id}/orchestrator/run", response_model=OLRunDetailOut)
def run_orchestrator(
    project_id: str,
    body: OLRunRequest,
    db: Session = Depends(get_db),
) -> OLRunDetailOut:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    service = OLService()
    try:
        outcome = service.run(
            db,
            project_id=project_id,
            user_request=body.user_request,
            origin=body.origin,
            origin_reference=body.origin_reference,
            jira_ticket_key=body.jira_ticket_key,
            jira_ticket_id=body.jira_ticket_id,
            repo_id=body.repo_id,
            acceptance_criteria=body.acceptance_criteria,
            extra_hints=body.extra_hints,
        )
        db.commit()
        run_out = OrchestratorRunOut.model_validate(outcome.run)
        save_orchestrator_run_snapshot(
            run_out.model_dump(mode="json"),
            project_slug=project.slug,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("OL run failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"ol_run_failed: {exc}") from exc

    return OLRunDetailOut(
        run=run_out,
        retrieved_chunks=[
            RetrievedChunkOut(**c.to_dict()) for c in outcome.retrieved_chunks
        ],
    )


@router.get(
    "/{project_id}/orchestrator/runs", response_model=list[OrchestratorRunOut]
)
def list_orchestrator_runs(
    project_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[OrchestratorRunOut]:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    service = OLService()
    runs = service.list_runs(db, project_id=project_id, limit=limit)
    db_rows = [OrchestratorRunOut.model_validate(r).model_dump(mode="json") for r in runs]
    local_rows = list_orchestrator_run_snapshots(
        project_id=project_id,
        project_slug=project.slug,
        limit=limit,
    )
    by_id: dict[str, dict[str, Any]] = {}
    for row in local_rows:
        row_id = str(row.get("id") or "")
        if row_id:
            by_id[row_id] = row
    for row in db_rows:
        row_id = str(row.get("id") or "")
        if row_id:
            by_id[row_id] = row
    merged = sorted(by_id.values(), key=lambda x: str(x.get("created_at") or ""), reverse=True)[:limit]
    return [OrchestratorRunOut.model_validate(r) for r in merged]


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------


@router.post("/{project_id}/search", response_model=OLSearchResponse)
def search_project(
    project_id: str,
    body: OLSearchRequest,
    db: Session = Depends(get_db),
) -> OLSearchResponse:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    pd = ProjectDataService()
    query = RetrievalQuery(
        project_id=project_id,
        text=body.text,
        source_types=body.source_types,
        file_paths=body.file_paths,
        repo_ids=body.repo_ids,
        jira_ticket_ids=body.jira_ticket_ids,
        max_chunks=body.max_chunks,
        recency_bias=body.recency_bias,
    )
    hits = pd.search(db, query)
    return OLSearchResponse(
        project_id=project_id,
        chunks=[RetrievedChunkOut(**h.to_dict()) for h in hits],
        backend=pd.embeddings.backend_name,
    )


# -----------------------------------------------------------------------------
# Sync (dev-mode polling / manual backfill)
# -----------------------------------------------------------------------------


@router.post("/{project_id}/sync/github", response_model=SyncResultOut)
def sync_github(project_id: str, db: Session = Depends(get_db)) -> SyncResultOut:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    result = SyncService().sync_github(db, project_id)
    db.commit()
    return SyncResultOut(**result.to_dict())


@router.post("/{project_id}/sync/jira", response_model=SyncResultOut)
def sync_jira(project_id: str, db: Session = Depends(get_db)) -> SyncResultOut:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    result = SyncService().sync_jira(db, project_id)
    db.commit()
    return SyncResultOut(**result.to_dict())


@router.post("/{project_id}/sync/all")
def sync_all(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found")
    result = SyncService().sync_all(db, project_id)
    db.commit()
    return result
