"""Task HTTP routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AgentRun, Approval, AuditLog, Task
from app.schemas.api import (
    AgentRunOut,
    ApprovalDecisionRequest,
    ApprovalOut,
    AuditLogOut,
    TaskOut,
)
from app.schemas.project_data import JiraTaskData, ProjectData
from app.seed import build_demo_project_data
from app.services.orchestration import OrchestrationService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(session: Session = Depends(get_db)) -> list[TaskOut]:
    rows = (
        session.execute(select(Task).order_by(desc(Task.created_at))).scalars().all()
    )
    return [TaskOut.model_validate(r) for r in rows]


@router.get("/{task_id}")
def get_task(task_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    runs = (
        session.execute(
            select(AgentRun)
            .where(AgentRun.task_id == task_id)
            .order_by(desc(AgentRun.created_at))
        )
        .scalars()
        .all()
    )
    approvals = (
        session.execute(
            select(Approval).where(Approval.task_id == task_id).order_by(desc(Approval.created_at))
        )
        .scalars()
        .all()
    )
    audit = (
        session.execute(
            select(AuditLog).where(AuditLog.task_id == task_id).order_by(AuditLog.created_at.asc())
        )
        .scalars()
        .all()
    )
    return {
        "task": TaskOut.model_validate(task).model_dump(mode="json"),
        "runs": [AgentRunOut.model_validate(r).model_dump(mode="json") for r in runs],
        "approvals": [ApprovalOut.model_validate(a).model_dump(mode="json") for a in approvals],
        "audit_logs": [AuditLogOut.model_validate(a).model_dump(mode="json") for a in audit],
    }


@router.post("/{task_id}/run-agent")
def run_agent_for_task(
    task_id: str,
    execute: bool = False,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run orchestrator for a task. When `execute=true`, forces autonomous
    execution (branch + PR + Jira comment) regardless of assignee. Otherwise,
    behaviour depends on whether the task is assigned to the Mycelium bot.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    project_data = build_demo_project_data()
    project_data.current_task = JiraTaskData(
        id=task.external_id,
        key=task.external_id,
        title=task.title,
        description=task.description,
        status=task.status,
        assignee=task.assignee,
        reporter=task.reporter,
        labels=task.labels,
        priority=task.priority,
        project_key=task.project_key,
    )
    project_data.user_goal = f"Complete task {task.title}"
    service = OrchestrationService()
    return service.run(
        session, project_data, task_id=task.id, force_execute=execute
    )


@router.post("/{task_id}/approve")
def approve_task(
    task_id: str,
    payload: ApprovalDecisionRequest,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    return _decide(session, task_id, "APPROVED", payload)


@router.post("/{task_id}/reject")
def reject_task(
    task_id: str,
    payload: ApprovalDecisionRequest,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    return _decide(session, task_id, "REJECTED", payload)


def _decide(
    session: Session,
    task_id: str,
    decision: str,
    payload: ApprovalDecisionRequest,
) -> dict[str, Any]:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    approval = (
        session.execute(
            select(Approval)
            .where(Approval.task_id == task_id, Approval.status == "REQUIRED")
            .order_by(desc(Approval.created_at))
        )
        .scalars()
        .first()
    )
    if approval is None:
        raise HTTPException(status_code=400, detail="no pending approval for this task")
    approval.status = decision
    approval.approver = payload.approver
    approval.decision_notes = payload.notes
    approval.decided_at = datetime.now(timezone.utc)
    task.approval_status = decision
    session.add(
        AuditLog(
            actor=payload.approver or "human",
            actor_type="human",
            task_id=task_id,
            agent_run_id=approval.agent_run_id,
            action_type=f"approval_{decision.lower()}",
            risk_level=approval.risk_level,
            approval_status=decision,
            input_summary=approval.reason,
            output_summary=payload.notes,
            sources_used=[],
            payload={"action_type": approval.action_type},
        )
    )
    session.commit()
    return {"task_id": task_id, "approval_status": decision, "approval_id": approval.id}
