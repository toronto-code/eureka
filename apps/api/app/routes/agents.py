"""Agent + orchestration HTTP routes."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agents.base import AgentInput, AgentType
from app.agents.registry import get_agent_registry
from app.db import get_db
from app.models import AgentRun, AuditLog, ExecutedAction
from app.schemas.api import (
    AgentGraphOut,
    AgentRunOut,
    AuditLogOut,
    ExecutedActionOut,
    GraphEdge,
    GraphNode,
    OrchestrateRequest,
    WatcherRunOut,
    WorkerRunRequest,
)
from app.schemas.project_data import ProjectData
from app.seed import build_demo_project_data
from app.services.orchestration import OrchestrationService
from app.services.watcher import JiraWatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/types")
def list_agent_types() -> dict[str, Any]:
    registry = get_agent_registry()
    types = []
    for agent_type in registry.available_types():
        agent = registry.get(agent_type)
        types.append(
            {
                "agent_type": agent_type.value,
                "agent_name": agent.agent_name,
                "system_prompt": agent.system_prompt[:240],
                "default_model": agent.default_model,
            }
        )
    return {"agent_types": types}


@router.post("/orchestrate")
def orchestrate(
    payload: OrchestrateRequest, session: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        project_data = ProjectData.model_validate(payload.project_data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    service = OrchestrationService()
    return service.run(session, project_data)


@router.post("/run-worker")
def run_worker(
    payload: WorkerRunRequest, session: Session = Depends(get_db)
) -> dict[str, Any]:
    registry = get_agent_registry()
    try:
        agent_type = AgentType(payload.agent_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown agent_type: {payload.agent_type}") from exc
    if not registry.has(agent_type):
        raise HTTPException(status_code=404, detail=f"No registered agent for {payload.agent_type}")
    agent = registry.get(agent_type)
    output = agent.run(
        AgentInput(
            task=payload.task,
            project_data_subset=payload.project_data,
            reason=payload.reason,
        )
    )
    run = AgentRun(
        agent_type=agent_type.value,
        agent_name=agent.agent_name,
        input_summary=payload.reason or "manual run",
        output_summary=output.summary,
        full_prompt=output.full_prompt,
        project_data_subset_json=payload.project_data,
        structured_output_json=output.structured_output,
        status=output.status.value,
        model=output.model,
        started_at=output.started_at,
        completed_at=output.completed_at,
        error_message=output.error,
    )
    session.add(run)
    session.commit()
    return {"agent_run_id": run.id, "output": output.model_dump(mode="json")}


@router.post("/demo")
def run_demo(
    force_execute: bool = False,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run the seeded demo project_data through the full flow.

    `force_execute=true` triggers autonomous execution even when no bot user
    is configured (useful for UI demos). Without it, the flow falls back to
    the draft-only path if the demo task isn't assigned to the bot.
    """
    project_data = build_demo_project_data()
    service = OrchestrationService()
    task_id = _ensure_demo_task(session, project_data)
    return service.run(
        session, project_data, task_id=task_id, force_execute=force_execute
    )


@router.post("/execute")
def execute_demo_style(
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Force autonomous execution of the seeded demo task (UI convenience)."""
    project_data = build_demo_project_data()
    service = OrchestrationService()
    task_id = _ensure_demo_task(session, project_data)
    return service.run(
        session, project_data, task_id=task_id, force_execute=True
    )


@router.post("/watch", response_model=WatcherRunOut)
def watch_jira(session: Session = Depends(get_db)) -> WatcherRunOut:
    """Poll Jira once for bot-assigned tasks and run orchestration for each."""
    watcher = JiraWatcher()
    result = watcher.run_once(session)
    session.commit()
    return WatcherRunOut(**result.to_dict())


@router.get("/executions", response_model=list[ExecutedActionOut])
def list_executions(
    limit: int = 50,
    task_id: str | None = None,
    session: Session = Depends(get_db),
) -> list[ExecutedActionOut]:
    stmt = select(ExecutedAction).order_by(desc(ExecutedAction.created_at)).limit(limit)
    if task_id:
        stmt = (
            select(ExecutedAction)
            .where(ExecutedAction.task_id == task_id)
            .order_by(desc(ExecutedAction.created_at))
            .limit(limit)
        )
    rows = session.execute(stmt).scalars().all()
    return [ExecutedActionOut.model_validate(r) for r in rows]


@router.get("/runs", response_model=list[AgentRunOut])
def list_runs(
    limit: int = 50,
    session: Session = Depends(get_db),
) -> list[AgentRunOut]:
    rows = (
        session.execute(
            select(AgentRun).order_by(desc(AgentRun.created_at)).limit(limit)
        )
        .scalars()
        .all()
    )
    return [AgentRunOut.model_validate(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_db)) -> dict[str, Any]:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    children = (
        session.execute(
            select(AgentRun)
            .where(AgentRun.orchestrator_run_id == run_id)
            .order_by(AgentRun.created_at.asc())
        )
        .scalars()
        .all()
    )
    audit = (
        session.execute(
            select(AuditLog)
            .where(AuditLog.agent_run_id.in_([run_id, *[c.id for c in children]]))
            .order_by(AuditLog.created_at.asc())
        )
        .scalars()
        .all()
    )
    return {
        "run": AgentRunOut.model_validate(run).model_dump(mode="json"),
        "children": [AgentRunOut.model_validate(c).model_dump(mode="json") for c in children],
        "audit_logs": [AuditLogOut.model_validate(a).model_dump(mode="json") for a in audit],
    }


@router.get("/runs/{run_id}/graph", response_model=AgentGraphOut)
def get_run_graph(run_id: str, session: Session = Depends(get_db)) -> AgentGraphOut:
    run = session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    children = (
        session.execute(
            select(AgentRun)
            .where(AgentRun.orchestrator_run_id == run_id)
            .order_by(AgentRun.created_at.asc())
        )
        .scalars()
        .all()
    )
    nodes: list[GraphNode] = [
        GraphNode(
            id=run.id,
            type="orchestrator",
            label=run.agent_name,
            status=run.status,
            agent_type=run.agent_type,
            summary=run.output_summary or "",
        )
    ]
    edges: list[GraphEdge] = []
    for child in children:
        nodes.append(
            GraphNode(
                id=child.id,
                type="worker",
                label=child.agent_name,
                status=child.status,
                agent_type=child.agent_type,
                summary=child.output_summary or "",
            )
        )
        edges.append(GraphEdge(**{"from": run.id, "to": child.id, "label": "spawned"}))
    return AgentGraphOut(nodes=nodes, edges=edges)


def _ensure_demo_task(session: Session, project_data: ProjectData) -> str | None:
    if not project_data.current_task:
        return None
    from app.models import Task

    existing = (
        session.execute(
            select(Task).where(Task.external_id == (project_data.current_task.key or project_data.current_task.id))
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing.id
    task = Task(
        external_id=project_data.current_task.key or project_data.current_task.id,
        source="jira",
        project_key=project_data.current_task.project_key,
        title=project_data.current_task.title or "Demo task",
        description=project_data.current_task.description,
        status=project_data.current_task.status or "To Do",
        assignee=project_data.current_task.assignee,
        reporter=project_data.current_task.reporter,
        labels=project_data.current_task.labels,
        priority=project_data.current_task.priority,
    )
    session.add(task)
    session.flush()
    return task.id
