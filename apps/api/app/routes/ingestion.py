"""Ingestion HTTP routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion import IngestionService, SessionProcessor
from app.schemas.api import DocumentChunkOut, DocumentDetailOut, DocumentOut

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

ALLOWED_SOURCE_TYPES = {"doc", "transcript", "web_session"}


@router.post("/upload")
async def upload_document(
    file: UploadFile | None = File(None),
    title: str | None = Form(None),
    source_type: str = Form("doc"),
    project_key: str | None = Form(None),
    raw_text: str | None = Form(None),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    if file is None and not raw_text:
        raise HTTPException(status_code=400, detail="Provide either a file or raw_text.")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "source_type must be one of: "
                + ", ".join(sorted(ALLOWED_SOURCE_TYPES))
            ),
        )

    service = IngestionService()

    if source_type == "web_session":
        if not raw_text:
            raise HTTPException(
                status_code=400,
                detail="web_session ingestion requires raw_text (JSON payload).",
            )
        try:
            payload = SessionProcessor().parse_payload(raw_text)
            processed = SessionProcessor().process(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        doc_id = service.ingest_document(
            session=session,
            source_type="web_session",
            title=title or processed.title,
            content=processed.summary_markdown,
            project_key=project_key,
            source_id=payload.get("session_id"),
            metadata={
                "session_id": payload.get("session_id"),
                "duration_seconds": processed.duration_seconds,
                "event_count": processed.event_count,
                "pages_visited": processed.pages_visited,
                "workflows": [wf.__dict__ for wf in processed.workflows],
                "insights": processed.insights,
                "started_at": payload.get("started_at"),
                "ended_at": payload.get("ended_at"),
                "description": processed.description,
            },
        )
        return {
            "document_id": doc_id,
            "source_type": "web_session",
            "workflows": [wf.name for wf in processed.workflows],
            "event_count": processed.event_count,
        }

    if file is not None:
        content_bytes = await file.read()
        doc_id = service.ingest_document(
            session=session,
            source_type=source_type,
            title=title or file.filename or "untitled",
            content=content_bytes,
            project_key=project_key,
        )
    else:
        assert raw_text is not None
        doc_id = service.ingest_document(
            session=session,
            source_type=source_type,
            title=title or "manual upload",
            content=raw_text,
            project_key=project_key,
        )
    return {"document_id": doc_id, "source_type": source_type}


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(session: Session = Depends(get_db)) -> list[DocumentOut]:
    service = IngestionService()
    docs = service.list_documents(session)
    out: list[DocumentOut] = []
    for d in docs:
        out.append(
            DocumentOut(
                id=d.id,
                source_type=d.source_type,
                source_id=d.source_id,
                title=d.title,
                project_key=d.project_key,
                related_task_id=d.related_task_id,
                chunk_count=len(d.chunks or []),
                created_at=d.created_at,
            )
        )
    return out


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
def get_document(doc_id: str, session: Session = Depends(get_db)) -> DocumentDetailOut:
    service = IngestionService()
    doc = service.get_document(session, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentDetailOut(
        id=doc.id,
        source_type=doc.source_type,
        source_id=doc.source_id,
        title=doc.title,
        project_key=doc.project_key,
        related_task_id=doc.related_task_id,
        chunk_count=len(doc.chunks or []),
        content=doc.content,
        created_at=doc.created_at,
        chunks=[
            DocumentChunkOut(
                id=c.id,
                chunk_index=c.chunk_index,
                content=c.content,
                token_count=c.token_count,
            )
            for c in (doc.chunks or [])
        ],
    )
