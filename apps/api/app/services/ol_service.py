"""OLService: end-to-end OL run.

Flow:
1. Persist an `OrchestratorRun` row with status=pending.
2. Classify via `OLClassifier` (may trigger shallow retrieval internally).
3. Execute the classifier's `retrieval_plan` to fetch the real chunk set.
4. Build a `LaneContext` and dispatch via `LaneDispatcher`.
5. Patch the run row with results and return the fully-populated row.

Every side effect is recorded:
- classifier output → columns on `orchestrator_runs`
- retrieval_plan → column, retrieved_chunk_ids → column
- lane result (summary, details, PR URL, Jira URL, steps) → columns + JSON
- errors → `errors` array
- `audit_logs` entries for classify + run
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agents.lanes.base import LaneContext
from app.agents.lanes.dispatcher import LaneDispatcher
from app.agents.ol.classifier import OLClassifier
from app.agents.ol.schemas import (
    LaneResult,
    OLClassification,
    OLRequest,
    ProjectSummary,
    RetrievalPlan,
)
from app.memory.project_data import ProjectDataService
from app.memory.retrieval import RetrievalQuery, RetrievedChunk
from app.models import AuditLog, OrchestratorRun, Project, ProjectEvent

logger = logging.getLogger(__name__)


@dataclass
class OLRunOutcome:
    run: OrchestratorRun
    classification: OLClassification
    retrieved_chunks: list[RetrievedChunk]
    lane_result: LaneResult


class OLService:
    """End-to-end OL orchestrator."""

    def __init__(
        self,
        classifier: OLClassifier | None = None,
        dispatcher: LaneDispatcher | None = None,
        project_data: ProjectDataService | None = None,
    ) -> None:
        self.classifier = classifier or OLClassifier()
        self.dispatcher = dispatcher or LaneDispatcher()
        self.project_data = project_data or ProjectDataService()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(
        self,
        session: Session,
        *,
        project_id: str,
        user_request: str,
        origin: str = "manual",
        origin_reference: str | None = None,
        jira_ticket_key: str | None = None,
        jira_ticket_id: str | None = None,
        repo_id: str | None = None,
        triggering_event_id: str | None = None,
        acceptance_criteria: list[str] | None = None,
        extra_hints: dict[str, Any] | None = None,
    ) -> OLRunOutcome:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        run = self._create_run_row(
            session,
            project=project,
            user_request=user_request,
            origin=origin,
            origin_reference=origin_reference,
            jira_ticket_id=jira_ticket_id,
            repo_id=repo_id,
            triggering_event_id=triggering_event_id,
        )

        try:
            ol_request = self._build_request(
                session,
                project=project,
                user_request=user_request,
                origin=origin,
                origin_reference=origin_reference,
                jira_ticket_id=jira_ticket_id,
                jira_ticket_key=jira_ticket_key,
                repo_id=repo_id,
                acceptance_criteria=acceptance_criteria or [],
                extra_hints=extra_hints or {},
            )

            classification_outcome = self.classifier.classify(session, ol_request)
            classification = classification_outcome.classification
            run.route = classification.route
            run.confidence = classification.confidence
            run.reasoning_summary = classification.reasoning_summary
            run.risk_level = classification.risk_level
            run.retrieval_plan = classification.retrieval_plan.model_dump()
            run.worker_directives = [
                wd.model_dump() for wd in classification.worker_directives
            ]
            run.run_metadata = {
                **(run.run_metadata or {}),
                "model": classification.model,
                "used_shallow_retrieval": classification.used_shallow_retrieval,
                "shallow_chunks_preview": classification_outcome.shallow_chunks,
            }
            session.flush()
            self._audit(
                session,
                project_id=project.id,
                event_type="ol.classify",
                actor="OL",
                payload={
                    "route": classification.route,
                    "confidence": classification.confidence,
                    "risk": classification.risk_level,
                    "run_id": run.id,
                },
            )

            retrieved = self._execute_retrieval_plan(
                session, project.id, classification.retrieval_plan
            )
            run.retrieved_chunk_ids = [c.id for c in retrieved]
            session.flush()

            lane_result = self._dispatch_lane(
                session, ol_request, classification, retrieved
            )

            run.lane_used = lane_result.lane
            run.lane_status = lane_result.status
            run.lane_result = lane_result.model_dump()
            run.pr_url = lane_result.pr_url
            run.jira_comment_url = lane_result.jira_comment_url
            run.blocked_reason = lane_result.blocked_reason
            run.status = _run_status_from(lane_result.status)
            run.finished_at = datetime.now(tz=timezone.utc)
            session.flush()

            self._audit(
                session,
                project_id=project.id,
                event_type="ol.lane_completed",
                actor="OL",
                payload={
                    "lane": lane_result.lane,
                    "status": lane_result.status,
                    "pr_url": lane_result.pr_url,
                    "jira_comment_url": lane_result.jira_comment_url,
                    "blocked_reason": lane_result.blocked_reason,
                    "run_id": run.id,
                },
            )
            return OLRunOutcome(
                run=run,
                classification=classification,
                retrieved_chunks=retrieved,
                lane_result=lane_result,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("OLService run failed: %s", exc)
            run.status = "error"
            run.finished_at = datetime.now(tz=timezone.utc)
            errors = list(run.errors or [])
            errors.append({"type": type(exc).__name__, "message": str(exc)[:400]})
            run.errors = errors
            session.flush()
            raise

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_runs(
        self,
        session: Session,
        *,
        project_id: str,
        limit: int = 50,
    ) -> list[OrchestratorRun]:
        stmt = (
            select(OrchestratorRun)
            .where(OrchestratorRun.project_id == project_id)
            .order_by(desc(OrchestratorRun.created_at))
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())

    def get_run(self, session: Session, run_id: str) -> OrchestratorRun | None:
        return session.get(OrchestratorRun, run_id)

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def _build_request(
        self,
        session: Session,
        *,
        project: Project,
        user_request: str,
        origin: str,
        origin_reference: str | None,
        jira_ticket_id: str | None,
        jira_ticket_key: str | None,
        repo_id: str | None,
        acceptance_criteria: list[str],
        extra_hints: dict[str, Any],
    ) -> OLRequest:
        summary = ProjectSummary(
            id=project.id,
            slug=project.slug,
            name=project.name,
            description=project.description,
            primary_language=project.primary_language,
            jira_project_key=project.jira_project_key,
            recent_events_summary=self._recent_events_summary(session, project.id),
        )
        return OLRequest(
            project=summary,
            user_request=user_request,
            origin=origin,  # type: ignore[arg-type]
            origin_reference=origin_reference,
            jira_ticket_id=jira_ticket_id,
            jira_ticket_key=jira_ticket_key,
            repo_id=repo_id,
            acceptance_criteria=acceptance_criteria,
            extra_hints=extra_hints,
        )

    def _recent_events_summary(
        self, session: Session, project_id: str, limit: int = 10
    ) -> list[str]:
        stmt = (
            select(ProjectEvent)
            .where(ProjectEvent.project_id == project_id)
            .order_by(desc(ProjectEvent.ingested_at), desc(ProjectEvent.created_at))
            .limit(limit)
        )
        out: list[str] = []
        for ev in session.execute(stmt).scalars().all():
            label = f"{ev.source}:{ev.event_type}"
            if ev.entity_id:
                label += f" ({ev.entity_id})"
            out.append(label)
        return out

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _execute_retrieval_plan(
        self, session: Session, project_id: str, plan: RetrievalPlan
    ) -> list[RetrievedChunk]:
        if not plan or plan.max_chunks <= 0:
            return []
        # One retrieval per query text, or a single pass if no queries.
        queries = plan.queries or [""]
        seen_ids: set[str] = set()
        collected: list[RetrievedChunk] = []
        per_query_cap = max(1, plan.max_chunks // len(queries))
        for qtext in queries:
            q = RetrievalQuery(
                project_id=project_id,
                text=qtext,
                source_types=list(plan.source_types),
                file_paths=list(plan.file_paths),
                repo_ids=list(plan.repo_ids),
                jira_ticket_ids=list(plan.jira_ticket_ids),
                max_chunks=per_query_cap,
                per_source_cap=max(1, per_query_cap // 2) or 1,
                recency_bias=plan.recency_bias,
            )
            for c in self.project_data.search(session, q):
                if c.id in seen_ids:
                    continue
                seen_ids.add(c.id)
                collected.append(c)
                if len(collected) >= plan.max_chunks:
                    return collected
        return collected

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch_lane(
        self,
        session: Session,
        request: OLRequest,
        classification: OLClassification,
        retrieved: list[RetrievedChunk],
    ) -> LaneResult:
        ctx = LaneContext(
            session=session,
            request=request,
            classification=classification,
            retrieved_chunks=retrieved,
        )
        return self.dispatcher.run(ctx)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _create_run_row(
        self,
        session: Session,
        *,
        project: Project,
        user_request: str,
        origin: str,
        origin_reference: str | None,
        jira_ticket_id: str | None,
        repo_id: str | None,
        triggering_event_id: str | None,
    ) -> OrchestratorRun:
        row = OrchestratorRun(
            project_id=project.id,
            origin=origin,
            origin_reference=origin_reference,
            user_request=user_request,
            jira_ticket_id=jira_ticket_id,
            repo_id=repo_id,
            triggering_event_id=triggering_event_id,
            status="running",
            started_at=datetime.now(tz=timezone.utc),
        )
        session.add(row)
        session.flush()
        return row

    def _audit(
        self,
        session: Session,
        *,
        project_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            AuditLog(
                actor=actor,
                actor_type="agent",
                action_type=event_type,
                input_summary=payload.get("route") or payload.get("lane") or event_type,
                output_summary=payload.get("blocked_reason") or payload.get("pr_url"),
                payload={**payload, "project_id": project_id},
            )
        )
        session.flush()


def _run_status_from(lane_status: str) -> str:
    return {
        "completed": "completed",
        "blocked": "blocked",
        "error": "error",
        "running": "running",
        "pending": "pending",
    }.get(lane_status, "completed")
