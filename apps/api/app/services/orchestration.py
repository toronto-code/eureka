"""OrchestrationService: persist orchestrator + worker runs and audit log entries.

Routes call this service to:
- run the orchestrator,
- write `agent_runs` rows for the orchestrator and each spawned worker,
- write `audit_logs` rows for meaningful decisions,
- create an `approvals` row when the recommended next action requires approval.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import AgentType
from app.agents.orchestrator import OrchestratorAgent, OrchestratorResult
from app.config import get_settings
from app.integrations.jira import get_jira_client
from app.models import AgentRun, Approval, AuditLog, Task
from app.schemas.project_data import ProjectData
from app.services.execution import ExecutionResult, ExecutionService

logger = logging.getLogger(__name__)


class OrchestrationService:
    def __init__(
        self,
        orchestrator: OrchestratorAgent | None = None,
        execution_service: ExecutionService | None = None,
    ) -> None:
        self.orchestrator = orchestrator or OrchestratorAgent()
        self.execution_service = execution_service or ExecutionService()

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def run(
        self,
        session: Session,
        project_data: ProjectData,
        *,
        task_id: str | None = None,
        force_execute: bool = False,
    ) -> dict[str, Any]:
        """Run orchestration. Auto-executes when the bot is the Jira assignee.

        `force_execute=True` bypasses the assignment check (used by explicit
        `/agents/execute` calls from the UI).
        """
        result = self.orchestrator.run_with_project_data(project_data)
        orchestrator_run = self._persist_orchestrator_run(session, result, task_id, project_data)
        worker_run_ids = self._persist_worker_runs(session, result, orchestrator_run, task_id)
        self._persist_audit_logs(session, result, orchestrator_run, task_id)

        # Decide whether to auto-execute.
        auto_execute = force_execute or self._should_auto_execute(project_data)
        execution: ExecutionResult | None = None
        if auto_execute:
            execution = self._run_execution(
                session,
                result,
                worker_run_ids,
                project_data=project_data,
                orchestrator_run_id=orchestrator_run.id,
                task_id=task_id,
            )
            self._mark_task_in_progress(session, task_id, execution)
        else:
            # Classic flow: if the plan would write, require human approval.
            self._maybe_create_approval(session, result, orchestrator_run, task_id)

        session.commit()

        # Inject persisted run IDs into the agents_spawned section for clarity.
        agents_with_ids: list[dict[str, Any]] = []
        for entry in result.final_payload.get("agents_spawned", []):
            entry = dict(entry)
            agent_type = entry.get("agent_type")
            if agent_type and agent_type in worker_run_ids:
                entry["agent_run_id"] = worker_run_ids[agent_type]
            agents_with_ids.append(entry)
        result.final_payload["agents_spawned"] = agents_with_ids

        if execution is not None:
            result.final_payload["execution"] = execution.to_dict()
            # Reflect autonomous execution in the audit entry.
            result.final_payload.setdefault("audit_log_entry", {})[
                "approval_status"
            ] = "APPROVED"

        return {
            "orchestrator_run_id": orchestrator_run.id,
            "output": result.final_payload,
            "spawned_run_ids": worker_run_ids,
            "execution": execution.to_dict() if execution else None,
            "auto_executed": execution is not None,
        }

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_orchestrator_run(
        self,
        session: Session,
        result: OrchestratorResult,
        task_id: str | None,
        project_data: ProjectData,
    ) -> AgentRun:
        run = AgentRun(
            id=result.orchestrator_run_id,
            agent_type="orchestrator",
            agent_name="OrchestratorAgent",
            task_id=task_id,
            input_summary=f"Orchestrator received project_data with task_id={task_id}",
            output_summary=result.output.summary,
            full_prompt=result.output.full_prompt,
            project_data_subset_json=_safe_json(
                {
                    "user_goal": project_data.user_goal,
                    "current_task": (
                        project_data.current_task.model_dump()
                        if project_data.current_task
                        else None
                    ),
                    "available_tools": project_data.available_tools,
                    "constraints": project_data.constraints,
                }
            ),
            structured_output_json=_safe_json(result.final_payload),
            status="completed",
            model=result.output.model,
            started_at=result.output.started_at,
            completed_at=result.output.completed_at,
            error_message=result.output.error,
        )
        session.add(run)
        session.flush()
        return run

    def _persist_worker_runs(
        self,
        session: Session,
        result: OrchestratorResult,
        orchestrator_run: AgentRun,
        task_id: str | None,
    ) -> dict[str, str]:
        run_ids: dict[str, str] = {}
        for worker in result.spawned_workers:
            output = worker.output
            run = AgentRun(
                agent_type=worker.agent_type,
                agent_name=worker.agent_name,
                task_id=task_id,
                orchestrator_run_id=orchestrator_run.id,
                parent_agent_run_id=orchestrator_run.id,
                spawned_by_agent_run_id=orchestrator_run.id,
                input_summary=worker.input_summary,
                output_summary=output.summary if output else None,
                full_prompt=output.full_prompt if output else None,
                project_data_subset_json=_safe_json({"reason": worker.reason}),
                structured_output_json=_safe_json(
                    output.structured_output if output else {}
                ),
                status=output.status.value if output else "failed",
                model=output.model if output else "gpt-4o",
                started_at=output.started_at if output else None,
                completed_at=output.completed_at if output else None,
                error_message=output.error if output else None,
            )
            session.add(run)
            session.flush()
            run_ids[worker.agent_type] = run.id
            worker.agent_run_id = run.id
        return run_ids

    def _persist_audit_logs(
        self,
        session: Session,
        result: OrchestratorResult,
        orchestrator_run: AgentRun,
        task_id: str | None,
    ) -> None:
        payload = result.final_payload
        risk = payload.get("risk_classification", {}) or {}
        approval_required = bool(risk.get("approval_required"))
        sources = payload.get("audit_log_entry", {}).get("sources_used", [])
        decisions = payload.get("audit_log_entry", {}).get("decisions", [])

        log = AuditLog(
            actor=orchestrator_run.agent_name,
            actor_type="agent",
            task_id=task_id,
            agent_run_id=orchestrator_run.id,
            action_type="orchestrator_run",
            risk_level=risk.get("overall_risk", "READ_ONLY"),
            approval_status="REQUIRED" if approval_required else "NOT_REQUIRED",
            input_summary=orchestrator_run.input_summary,
            output_summary=orchestrator_run.output_summary,
            sources_used=sources,
            payload=_safe_json({"decisions": decisions}),
        )
        session.add(log)

        for worker in result.spawned_workers:
            session.add(
                AuditLog(
                    actor=worker.agent_name,
                    actor_type="agent",
                    task_id=task_id,
                    agent_run_id=worker.agent_run_id,
                    action_type=f"{worker.agent_type}_run",
                    risk_level=(
                        worker.output.risk_level.value
                        if worker.output and worker.output.risk_level
                        else "READ_ONLY"
                    ),
                    approval_status="NOT_REQUIRED",
                    input_summary=worker.input_summary,
                    output_summary=worker.output.summary if worker.output else None,
                    sources_used=[],
                    payload={},
                )
            )

    def _maybe_create_approval(
        self,
        session: Session,
        result: OrchestratorResult,
        orchestrator_run: AgentRun,
        task_id: str | None,
    ) -> None:
        risk = result.final_payload.get("risk_classification", {}) or {}
        if not risk.get("approval_required"):
            return
        recommended = result.final_payload.get("recommended_next_action", {}) or {}
        approval = Approval(
            task_id=task_id,
            agent_run_id=orchestrator_run.id,
            action_type=recommended.get("action_type") or "unknown_action",
            risk_level=risk.get("overall_risk", "HIGH_RISK_WRITE"),
            status="REQUIRED",
            reason=risk.get("reasoning") or "Write action requires human approval.",
            payload=_safe_json(recommended),
        )
        session.add(approval)
        if task_id:
            task = session.get(Task, task_id)
            if task is not None:
                task.approval_status = "REQUIRED"
                task.risk_level = risk.get("overall_risk", task.risk_level)


    # ------------------------------------------------------------------
    # Autonomous execution
    # ------------------------------------------------------------------

    def _should_auto_execute(self, project_data: ProjectData) -> bool:
        settings = get_settings()
        if not settings.bot_auto_execute_enabled:
            return False
        task = project_data.current_task
        if task is None:
            return False
        jira = get_jira_client()
        return jira.is_assigned_to_bot(task.model_dump())

    def _run_execution(
        self,
        session: Session,
        result: "OrchestratorResult",
        worker_run_ids: dict[str, str],
        *,
        project_data: ProjectData,
        orchestrator_run_id: str,
        task_id: str | None,
    ) -> ExecutionResult:
        executor_output: dict[str, Any] = {}
        for worker in result.spawned_workers:
            if worker.agent_type == AgentType.EXECUTOR.value and worker.output:
                executor_output = worker.output.structured_output or {}
                break
        executor_run_id = worker_run_ids.get(AgentType.EXECUTOR.value)
        task_snapshot = self._build_task_snapshot(project_data, result)
        return self.execution_service.execute(
            session,
            task=task_snapshot,
            executor_output=executor_output,
            task_id=task_id,
            orchestrator_run_id=orchestrator_run_id,
            executor_run_id=executor_run_id,
        )

    @staticmethod
    def _build_task_snapshot(
        project_data: ProjectData, result: "OrchestratorResult"
    ) -> dict[str, Any]:
        if project_data.current_task is not None:
            return project_data.current_task.model_dump()
        understanding = result.final_payload.get("task_understanding") or {}
        return {
            "key": understanding.get("task_id"),
            "id": understanding.get("task_id"),
            "title": understanding.get("plain_english_goal"),
            "description": understanding.get("technical_goal"),
        }

    def _mark_task_in_progress(
        self,
        session: Session,
        task_id: str | None,
        execution: ExecutionResult,
    ) -> None:
        if task_id is None:
            return
        task = session.get(Task, task_id)
        if task is None:
            return
        task.approval_status = "APPROVED"  # assignment == approval
        if execution.executed and execution.pr_url:
            task.status = "In Review"


def _safe_json(value: Any) -> Any:
    """Round-trip through JSON to drop datetimes/non-serialisable bits."""
    return json.loads(json.dumps(value, default=str))
