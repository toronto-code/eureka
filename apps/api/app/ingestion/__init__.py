"""Ingestion services: parse uploaded docs/transcripts and push them into memory."""

from app.ingestion.parsers import parse_text_or_markdown
from app.ingestion.service import (
    IngestionService,
    ingest_local_document,
    ingest_local_transcript,
)
from app.ingestion.session_processor import ProcessedSession, SessionProcessor

__all__ = [
    "IngestionService",
    "ProcessedSession",
    "SessionProcessor",
    "ingest_local_document",
    "ingest_local_transcript",
    "parse_text_or_markdown",
]
