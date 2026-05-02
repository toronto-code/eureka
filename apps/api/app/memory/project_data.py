"""ProjectDataService: canonical facade over project memory.

Callers never touch `project_chunks` directly — they go through this service.
It owns three responsibilities:

1. **Upsert canonical rows** (Project, Repository, JiraTicket, Commit,
   PullRequest, RepoFile) when events come in or sync runs.
2. **Re-chunk and re-embed** the affected artefact, replacing its old chunks.
3. **Expose retrieval** by delegating to `RetrievalService`.

Everything here is synchronous — async transport (Redis streams, etc.) can
be added later; the service boundaries don't need to change.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.memory.chunking import ChunkDraft, ChunkingService, detect_language, is_binary_like
from app.memory.embeddings import EmbeddingService, get_embedding_service
from app.memory.retrieval import RetrievalQuery, RetrievalService, RetrievedChunk
from app.models import (
    Commit,
    JiraTicket,
    Project,
    ProjectChunk,
    PullRequest,
    RepoFile,
    Repository,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Result shapes
# -----------------------------------------------------------------------------


@dataclass
class UpsertResult:
    created: bool
    row_id: str
    chunks_written: int = 0


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------


class ProjectDataService:
    """Upsert + chunk + embed + retrieve, all in one boundary."""

    def __init__(
        self,
        chunker: ChunkingService | None = None,
        embeddings: EmbeddingService | None = None,
        retrieval: RetrievalService | None = None,
    ) -> None:
        self.chunker = chunker or ChunkingService()
        self.embeddings = embeddings or get_embedding_service()
        self.retrieval = retrieval or RetrievalService(self.embeddings)

    # ------------------------------------------------------------------
    # Project / repo bootstrap
    # ------------------------------------------------------------------

    def ensure_project(
        self,
        session: Session,
        *,
        slug: str,
        name: str,
        description: str | None = None,
        primary_language: str | None = None,
        jira_project_key: str | None = None,
    ) -> Project:
        existing = session.execute(
            select(Project).where(Project.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            changed = False
            if name and existing.name != name:
                existing.name = name
                changed = True
            if description is not None and existing.description != description:
                existing.description = description
                changed = True
            if primary_language and existing.primary_language != primary_language:
                existing.primary_language = primary_language
                changed = True
            if jira_project_key and existing.jira_project_key != jira_project_key:
                existing.jira_project_key = jira_project_key
                changed = True
            if changed:
                session.flush()
            return existing
        project = Project(
            slug=slug,
            name=name,
            description=description,
            primary_language=primary_language,
            jira_project_key=jira_project_key,
        )
        session.add(project)
        session.flush()
        return project

    def ensure_repository(
        self,
        session: Session,
        *,
        project_id: str,
        owner: str,
        name: str,
        default_branch: str = "main",
        html_url: str | None = None,
        installation_id: str | None = None,
    ) -> Repository:
        existing = session.execute(
            select(Repository).where(
                Repository.project_id == project_id,
                Repository.owner == owner,
                Repository.name == name,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if html_url and not existing.html_url:
                existing.html_url = html_url
            if installation_id and existing.installation_id != installation_id:
                existing.installation_id = installation_id
            return existing
        repo = Repository(
            project_id=project_id,
            owner=owner,
            name=name,
            default_branch=default_branch,
            html_url=html_url,
            installation_id=installation_id,
        )
        session.add(repo)
        session.flush()
        return repo

    # ------------------------------------------------------------------
    # Code files
    # ------------------------------------------------------------------

    def upsert_repo_file(
        self,
        session: Session,
        *,
        project_id: str,
        repo_id: str,
        path: str,
        content: str,
        branch: str | None = None,
        commit_sha: str | None = None,
    ) -> UpsertResult:
        """Upsert a RepoFile row + re-chunk + re-embed the file."""
        if is_binary_like(content):
            logger.info("Skipping binary-like file %s", path)
            return UpsertResult(created=False, row_id="", chunks_written=0)

        language = detect_language(path)
        existing = session.execute(
            select(RepoFile).where(
                RepoFile.repo_id == repo_id,
                RepoFile.path == path,
                RepoFile.branch == branch,
            )
        ).scalar_one_or_none()

        if existing is None:
            existing = RepoFile(
                repo_id=repo_id,
                path=path,
                branch=branch,
                language=language,
                commit_sha=commit_sha,
                size_bytes=len(content),
            )
            session.add(existing)
            session.flush()
            created = True
        else:
            existing.commit_sha = commit_sha or existing.commit_sha
            existing.language = language or existing.language
            existing.size_bytes = len(content)
            created = False

        drafts = self.chunker.chunk_code_file(
            project_id=project_id,
            repo_id=repo_id,
            file_path=path,
            content=content,
            branch=branch,
            commit_sha=commit_sha,
            language=language,
            repo_file_id=existing.id,
        )
        written = self._replace_chunks(
            session,
            project_id=project_id,
            source_type="code_file",
            source_id=existing.id,
            drafts=drafts,
        )
        return UpsertResult(created=created, row_id=existing.id, chunks_written=written)

    # ------------------------------------------------------------------
    # Jira tickets
    # ------------------------------------------------------------------

    def upsert_jira_ticket(
        self,
        session: Session,
        *,
        project_id: str,
        key: str,
        title: str,
        description: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        assignee_email: str | None = None,
        assignee_account_id: str | None = None,
        reporter: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
        comments: list[dict[str, Any]] | None = None,
        last_jira_updated_at: datetime | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> UpsertResult:
        existing = session.execute(
            select(JiraTicket).where(
                JiraTicket.project_id == project_id, JiraTicket.key == key
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = JiraTicket(
                project_id=project_id,
                key=key,
                title=title,
                description=description,
                status=status,
                assignee=assignee,
                assignee_email=assignee_email,
                assignee_account_id=assignee_account_id,
                reporter=reporter,
                priority=priority,
                labels=labels or [],
                last_jira_updated_at=last_jira_updated_at,
                raw_payload=raw_payload or {},
            )
            session.add(existing)
            session.flush()
            created = True
        else:
            existing.title = title or existing.title
            existing.description = description if description is not None else existing.description
            existing.status = status or existing.status
            existing.assignee = assignee or existing.assignee
            existing.assignee_email = assignee_email or existing.assignee_email
            existing.assignee_account_id = (
                assignee_account_id or existing.assignee_account_id
            )
            existing.reporter = reporter or existing.reporter
            existing.priority = priority or existing.priority
            if labels is not None:
                existing.labels = labels
            if last_jira_updated_at is not None:
                existing.last_jira_updated_at = last_jira_updated_at
            if raw_payload is not None:
                existing.raw_payload = raw_payload
            created = False

        drafts = self.chunker.chunk_jira_ticket(
            project_id=project_id,
            jira_ticket_id=existing.id,
            key=key,
            title=title,
            description=description,
            comments=comments,
            labels=labels,
            status=status,
        )
        written = self._replace_chunks(
            session,
            project_id=project_id,
            source_type_any=["jira_ticket", "comment"],
            jira_ticket_id=existing.id,
            drafts=drafts,
        )
        return UpsertResult(created=created, row_id=existing.id, chunks_written=written)

    # ------------------------------------------------------------------
    # Pull requests + commits
    # ------------------------------------------------------------------

    def upsert_pull_request(
        self,
        session: Session,
        *,
        project_id: str,
        repo_id: str,
        number: int,
        title: str,
        body: str | None = None,
        state: str = "open",
        author: str | None = None,
        head_branch: str | None = None,
        base_branch: str | None = None,
        html_url: str | None = None,
        opened_at: datetime | None = None,
        merged_at: datetime | None = None,
        closed_at: datetime | None = None,
    ) -> UpsertResult:
        existing = session.execute(
            select(PullRequest).where(
                PullRequest.repo_id == repo_id, PullRequest.number == number
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = PullRequest(
                repo_id=repo_id,
                number=number,
                title=title,
                body=body,
                state=state,
                author=author,
                head_branch=head_branch,
                base_branch=base_branch,
                html_url=html_url,
                opened_at=opened_at,
                merged_at=merged_at,
                closed_at=closed_at,
            )
            session.add(existing)
            session.flush()
            created = True
        else:
            existing.title = title or existing.title
            existing.body = body if body is not None else existing.body
            existing.state = state or existing.state
            existing.author = author or existing.author
            existing.head_branch = head_branch or existing.head_branch
            existing.base_branch = base_branch or existing.base_branch
            existing.html_url = html_url or existing.html_url
            if merged_at is not None:
                existing.merged_at = merged_at
            if closed_at is not None:
                existing.closed_at = closed_at
            created = False

        drafts = self.chunker.chunk_pull_request(
            project_id=project_id,
            repo_id=repo_id,
            pull_request_id=existing.id,
            number=number,
            title=title,
            body=body,
            head_branch=head_branch,
            base_branch=base_branch,
            state=state,
        )
        written = self._replace_chunks(
            session,
            project_id=project_id,
            source_type="pr",
            source_id=existing.id,
            drafts=drafts,
        )
        return UpsertResult(created=created, row_id=existing.id, chunks_written=written)

    def upsert_commit(
        self,
        session: Session,
        *,
        project_id: str,
        repo_id: str,
        sha: str,
        message: str | None,
        author_name: str | None = None,
        author_email: str | None = None,
        branch: str | None = None,
        committed_at: datetime | None = None,
        html_url: str | None = None,
    ) -> UpsertResult:
        existing = session.execute(
            select(Commit).where(Commit.repo_id == repo_id, Commit.sha == sha)
        ).scalar_one_or_none()
        if existing is None:
            existing = Commit(
                repo_id=repo_id,
                sha=sha,
                short_sha=sha[:8],
                message=message,
                author_name=author_name,
                author_email=author_email,
                branch=branch,
                committed_at=committed_at,
                html_url=html_url,
            )
            session.add(existing)
            session.flush()
            created = True
        else:
            existing.message = message or existing.message
            existing.branch = branch or existing.branch
            existing.html_url = html_url or existing.html_url
            created = False

        drafts = self.chunker.chunk_commit(
            project_id=project_id,
            repo_id=repo_id,
            commit_id=existing.id,
            sha=sha,
            message=message,
            author=author_name,
            branch=branch,
        )
        written = self._replace_chunks(
            session,
            project_id=project_id,
            source_type="commit",
            source_id=existing.id,
            drafts=drafts,
        )
        return UpsertResult(created=created, row_id=existing.id, chunks_written=written)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self, session: Session, query: RetrievalQuery
    ) -> list[RetrievedChunk]:
        return self.retrieval.search(session, query)

    # ------------------------------------------------------------------
    # Chunk write + embed
    # ------------------------------------------------------------------

    def _replace_chunks(
        self,
        session: Session,
        *,
        project_id: str,
        source_type: str | None = None,
        source_type_any: Iterable[str] | None = None,
        source_id: str | None = None,
        jira_ticket_id: str | None = None,
        drafts: list[ChunkDraft],
    ) -> int:
        """Delete old chunks for (project, source_id|jira_ticket_id) then insert new ones."""
        delete_stmt = delete(ProjectChunk).where(ProjectChunk.project_id == project_id)
        if source_type is not None:
            delete_stmt = delete_stmt.where(ProjectChunk.source_type == source_type)
        if source_type_any is not None:
            delete_stmt = delete_stmt.where(
                ProjectChunk.source_type.in_(list(source_type_any))
            )
        if source_id is not None:
            delete_stmt = delete_stmt.where(ProjectChunk.source_id == source_id)
        if jira_ticket_id is not None:
            delete_stmt = delete_stmt.where(ProjectChunk.jira_ticket_id == jira_ticket_id)
        session.execute(delete_stmt)

        if not drafts:
            return 0

        texts = [d.chunk_text for d in drafts]
        vectors = self.embeddings.embed_many(texts)
        now = datetime.now(tz=timezone.utc)
        rows: list[ProjectChunk] = []
        for draft, vec in zip(drafts, vectors):
            kwargs = draft.to_model_kwargs()
            chunk = ProjectChunk(**kwargs)
            if vec:
                try:
                    chunk.embedding = vec  # pgvector or JSON, both accept list[float]
                except Exception:  # noqa: BLE001
                    chunk.embedding = None
            chunk.updated_at = now
            rows.append(chunk)
        session.add_all(rows)
        session.flush()
        return len(rows)
