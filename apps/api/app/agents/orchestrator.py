"""OrchestratorAgent: the wide central GPT-4o agent that coordinates workers.

Flow:
  1. Receive `project_data` + current_task.
  2. Form task understanding (LLM, with deterministic fallback).
  3. Decide which worker agents to spawn + a focused subset for each.
  4. Run each worker through the AgentRegistry.
  5. Merge findings, classify risk via RiskSafetyAgent, recommend next action.
  6. Persist agent_runs + audit_logs through `OrchestratorService` in routes.

The orchestrator does NOT itself open a database session — that is the
responsibility of the calling route/service. It returns a fully-typed
`OrchestratorResult` that the route layer translates into DB writes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agents.base import (
    AgentInput,
    AgentOutput,
    AgentRunStatus,
    AgentType,
    BaseAgent,
    RiskLevel,
    coerce_risk,
)
from app.agents.registry import AgentRegistry, get_agent_registry
from app.prompts import ORCHESTRATOR_PROMPT, ORCHESTRATOR_SCHEMA
from app.schemas.project_data import ProjectData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


class SpawnedWorker(BaseModel):
    agent_type: str
    agent_name: str
    reason: str
    input_summary: str
    agent_run_id: str | None = None
    output: AgentOutput | None = None


class OrchestratorResult(BaseModel):
    """Everything the route layer needs to persist + return to the caller."""

    orchestrator_run_id: str
    output: AgentOutput
    spawned_workers: list[SpawnedWorker] = Field(default_factory=list)
    final_payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Orchestrator agent
# ---------------------------------------------------------------------------


# Default plan: which workers to spawn. The LLM may override this.
DEFAULT_WORKER_PLAN: list[dict[str, Any]] = [
    {
        "agent_type": AgentType.JIRA_ANALYST.value,
        "reason": "Analyse the Jira ticket itself for clarity, ambiguities, and acceptance criteria.",
        "subset_keys": ["current_task", "jira_tasks"],
    },
    {
        "agent_type": AgentType.CODEBASE_ANALYST.value,
        "reason": "Identify relevant code/services for the task.",
        "subset_keys": ["current_task", "github_repositories", "code_files"],
    },
    {
        "agent_type": AgentType.DOCS_ANALYST.value,
        "reason": "Surface relevant facts, constraints, and procedures from internal docs.",
        "subset_keys": ["current_task", "docs"],
    },
    {
        "agent_type": AgentType.TRANSCRIPT_ANALYST.value,
        "reason": "Pull decisions and unresolved questions from working-session transcripts.",
        "subset_keys": ["current_task", "transcripts"],
    },
    {
        "agent_type": AgentType.PLANNER.value,
        "reason": "Build a concrete implementation plan from gathered findings.",
        "subset_keys": ["current_task"],  # supplemented with merged findings at runtime
    },
    {
        "agent_type": AgentType.RISK_SAFETY.value,
        "reason": "Classify risk and decide if approval is required.",
        "subset_keys": ["current_task"],
    },
    {
        "agent_type": AgentType.EXECUTOR.value,
        "reason": "Produce a simulated draft of the recommended action.",
        "subset_keys": ["current_task"],
    },
    {
        "agent_type": AgentType.REVIEWER.value,
        "reason": "Review the merged outputs for accuracy and missing context.",
        "subset_keys": ["current_task"],
    },
]


class OrchestratorAgent(BaseAgent):
    agent_type = AgentType.ORCHESTRATOR
    agent_name = "OrchestratorAgent"
    system_prompt = ORCHESTRATOR_PROMPT
    output_schema_hint = ORCHESTRATOR_SCHEMA

    def __init__(self, registry: AgentRegistry | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.registry = registry or get_agent_registry()

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def run_with_project_data(self, project_data: ProjectData) -> OrchestratorResult:
        """Run the full orchestration flow for a given project_data context."""
        orchestrator_run_id = str(uuid4())
        started = datetime.now(timezone.utc)

        current_task = (
            project_data.current_task.model_dump()
            if project_data.current_task
            else self._infer_current_task(project_data)
        )

        # --- Step 1: task understanding --------------------------------
        understanding = self._build_task_understanding(project_data, current_task)

        # --- Step 2: spawn workers -------------------------------------
        spawned: list[SpawnedWorker] = []
        worker_outputs: dict[str, dict[str, Any]] = {}

        plan = self._select_worker_plan(project_data, current_task)
        # Run the analyst-type workers first.
        early_types = {
            AgentType.JIRA_ANALYST.value,
            AgentType.CODEBASE_ANALYST.value,
            AgentType.DOCS_ANALYST.value,
            AgentType.TRANSCRIPT_ANALYST.value,
        }
        for plan_entry in [p for p in plan if p["agent_type"] in early_types]:
            worker = self._run_worker(
                plan_entry,
                project_data,
                current_task,
                orchestrator_run_id,
                worker_outputs,
            )
            if worker is not None:
                spawned.append(worker)
                if worker.output:
                    worker_outputs[worker.agent_type] = worker.output.structured_output

        # Merge analyst findings.
        merged_findings = self._merge_findings(worker_outputs)

        # Planner uses merged findings as its focused subset.
        planner_entry = next(
            (p for p in plan if p["agent_type"] == AgentType.PLANNER.value), None
        )
        if planner_entry:
            worker = self._run_worker(
                planner_entry,
                project_data,
                current_task,
                orchestrator_run_id,
                worker_outputs,
                extra_subset={"merged_findings": merged_findings},
            )
            if worker is not None:
                spawned.append(worker)
                if worker.output:
                    worker_outputs[worker.agent_type] = worker.output.structured_output

        plan_steps = (
            worker_outputs.get(AgentType.PLANNER.value, {}).get("steps", []) or []
        )

        # Risk safety considers plan + current task.
        risk_entry = next(
            (p for p in plan if p["agent_type"] == AgentType.RISK_SAFETY.value), None
        )
        if risk_entry:
            worker = self._run_worker(
                risk_entry,
                project_data,
                current_task,
                orchestrator_run_id,
                worker_outputs,
                extra_subset={"implementation_plan": plan_steps},
            )
            if worker is not None:
                spawned.append(worker)
                if worker.output:
                    worker_outputs[worker.agent_type] = worker.output.structured_output

        risk_payload = worker_outputs.get(AgentType.RISK_SAFETY.value, {}) or {}
        overall_risk = coerce_risk(risk_payload.get("risk_level"))
        approval_required = bool(risk_payload.get("approval_required")) or (
            overall_risk == RiskLevel.HIGH_RISK_WRITE
        )

        # Executor produces a draft scoped to the recommended action.
        executor_entry = next(
            (p for p in plan if p["agent_type"] == AgentType.EXECUTOR.value), None
        )
        if executor_entry:
            worker = self._run_worker(
                executor_entry,
                project_data,
                current_task,
                orchestrator_run_id,
                worker_outputs,
                extra_subset={
                    "implementation_plan": plan_steps,
                    "merged_findings": merged_findings,
                    "target": (current_task or {}).get("project_key")
                    or (current_task or {}).get("title")
                    or "payments-service",
                },
            )
            if worker is not None:
                spawned.append(worker)
                if worker.output:
                    worker_outputs[worker.agent_type] = worker.output.structured_output

        # Reviewer sees all worker outputs.
        reviewer_entry = next(
            (p for p in plan if p["agent_type"] == AgentType.REVIEWER.value), None
        )
        if reviewer_entry:
            worker = self._run_worker(
                reviewer_entry,
                project_data,
                current_task,
                orchestrator_run_id,
                worker_outputs,
                extra_subset={"worker_outputs": worker_outputs},
            )
            if worker is not None:
                spawned.append(worker)
                if worker.output:
                    worker_outputs[worker.agent_type] = worker.output.structured_output

        # --- Step 3: assemble final payload ----------------------------
        recommended_action = self._derive_recommended_action(
            worker_outputs, overall_risk, approval_required
        )

        final_payload: dict[str, Any] = {
            "orchestrator_summary": (
                f"Coordinated {len(spawned)} worker agents for task "
                f"'{(current_task or {}).get('title', 'unknown')}'."
            ),
            "task_understanding": understanding,
            "agents_spawned": [
                {
                    "agent_type": s.agent_type,
                    "agent_name": s.agent_name,
                    "reason": s.reason,
                    "input_summary": s.input_summary,
                    "agent_run_id": s.agent_run_id,
                }
                for s in spawned
            ],
            "merged_findings": merged_findings,
            "implementation_plan": plan_steps,
            "risk_classification": {
                "overall_risk": overall_risk.value,
                "reasoning": (risk_payload.get("reasons") or [
                    "Default risk reasoning."
                ])[0]
                if isinstance(risk_payload.get("reasons"), list) and risk_payload.get("reasons")
                else "Risk inferred from plan content.",
                "approval_required": approval_required,
                "blocked_actions": risk_payload.get("blocked_actions", []) or [],
            },
            "recommended_next_action": recommended_action,
            "audit_log_entry": {
                "agents_spawned": [s.agent_name for s in spawned],
                "sources_used": self._sources_used(project_data),
                "decisions": [
                    "Task understood and decomposed.",
                    "Worker agents spawned in dependency order.",
                    "Findings merged and risk classified.",
                ],
                "approval_status": "REQUIRED" if approval_required else "NOT_REQUIRED",
            },
        }

        completed = datetime.now(timezone.utc)
        output = AgentOutput(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            status=AgentRunStatus.COMPLETED,
            summary=final_payload["orchestrator_summary"],
            structured_output=final_payload,
            risk_level=overall_risk,
            started_at=started,
            completed_at=completed,
            model=self.model,
            full_prompt=self._render_full_prompt(project_data, current_task),
        )
        return OrchestratorResult(
            orchestrator_run_id=orchestrator_run_id,
            output=output,
            spawned_workers=spawned,
            final_payload=final_payload,
        )

    # ------------------------------------------------------------------
    # BaseAgent overrides (so the orchestrator can be invoked uniformly)
    # ------------------------------------------------------------------

    def run(self, agent_input: AgentInput) -> AgentOutput:
        project_data_dict = agent_input.project_data_subset or {}
        try:
            project_data = ProjectData.model_validate(project_data_dict)
        except Exception:  # noqa: BLE001
            project_data = ProjectData()
        result = self.run_with_project_data(project_data)
        return result.output

    def fallback_output(self, agent_input: AgentInput) -> dict[str, Any]:
        return {"orchestrator_summary": "fallback orchestration"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer_current_task(self, project_data: ProjectData) -> dict[str, Any]:
        if project_data.jira_tasks:
            return project_data.jira_tasks[0].model_dump()
        return {}

    def _build_task_understanding(
        self, project_data: ProjectData, current_task: dict[str, Any]
    ) -> dict[str, Any]:
        title = current_task.get("title") or project_data.user_goal or "Unknown task"
        description = current_task.get("description") or ""
        understanding_prompt = (
            "Summarise this task into a JSON object with keys: task_id, plain_english_goal, "
            "technical_goal, known_constraints (string[]), missing_information (string[]). "
            "Stay grounded; do not invent details."
        )
        user_prompt = (
            f"Task title: {title}\n"
            f"Task description: {description}\n"
            f"User goal: {project_data.user_goal or 'not provided'}\n"
            f"Constraints: {project_data.constraints}\n"
        )
        fallback = {
            "task_id": current_task.get("id") or current_task.get("key"),
            "plain_english_goal": title,
            "technical_goal": description[:300] if description else title,
            "known_constraints": project_data.constraints or [],
            "missing_information": [
                k
                for k, v in {
                    "current_task": project_data.current_task,
                    "github_repositories": project_data.github_repositories,
                    "docs": project_data.docs,
                    "transcripts": project_data.transcripts,
                }.items()
                if not v
            ],
        }
        try:
            payload = self.llm.generate_json(
                system_prompt=understanding_prompt,
                user_prompt=user_prompt,
                model=self.model,
                fallback=fallback,
            )
            return payload or fallback
        except Exception as exc:  # noqa: BLE001
            logger.warning("Task understanding LLM call failed: %s", exc)
            return fallback

    def _select_worker_plan(
        self, project_data: ProjectData, current_task: dict[str, Any]
    ) -> list[dict[str, Any]]:
        # MVP: deterministic plan, but skip workers that have no data to chew on.
        plan: list[dict[str, Any]] = []
        for entry in DEFAULT_WORKER_PLAN:
            atype = entry["agent_type"]
            if atype == AgentType.TRANSCRIPT_ANALYST.value and not project_data.transcripts:
                continue
            if atype == AgentType.DOCS_ANALYST.value and not project_data.docs:
                continue
            if atype == AgentType.CODEBASE_ANALYST.value and not (
                project_data.code_files or project_data.github_repositories
            ):
                continue
            plan.append(entry)
        return plan

    def _build_subset(
        self,
        project_data: ProjectData,
        current_task: dict[str, Any],
        keys: list[str],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        subset: dict[str, Any] = {}
        full = project_data.model_dump()
        for key in keys:
            if key == "current_task":
                subset["current_task"] = current_task
                continue
            value = full.get(key)
            if value is not None:
                subset[key] = value
        if extra:
            subset.update(extra)
        return subset

    def _run_worker(
        self,
        plan_entry: dict[str, Any],
        project_data: ProjectData,
        current_task: dict[str, Any],
        orchestrator_run_id: str,
        worker_outputs: dict[str, Any],
        extra_subset: dict[str, Any] | None = None,
    ) -> SpawnedWorker | None:
        agent_type_value = plan_entry["agent_type"]
        try:
            agent_type = AgentType(agent_type_value)
        except ValueError:
            logger.warning("Unknown agent_type in plan: %s", agent_type_value)
            return None
        if not self.registry.has(agent_type):
            logger.warning("Registry missing agent_type: %s", agent_type)
            return None

        subset = self._build_subset(
            project_data, current_task, plan_entry.get("subset_keys", []), extra_subset
        )
        agent_input = AgentInput(
            task=current_task,
            project_data_subset=subset,
            reason=plan_entry.get("reason"),
            orchestrator_run_id=orchestrator_run_id,
        )
        output = self.registry.run_agent(agent_type, agent_input)
        return SpawnedWorker(
            agent_type=agent_type.value,
            agent_name=output.agent_name,
            reason=plan_entry.get("reason", ""),
            input_summary=self._summarise_subset(subset),
            output=output,
        )

    @staticmethod
    def _summarise_subset(subset: dict[str, Any]) -> str:
        keys = list(subset.keys())
        if not keys:
            return "No focused subset provided."
        return "Focused on: " + ", ".join(keys)

    @staticmethod
    def _merge_findings(worker_outputs: dict[str, Any]) -> dict[str, str]:
        def _text(payload: dict[str, Any], key: str, fallback: str = "") -> str:
            value = payload.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "; ".join(str(v) for v in value[:5])
            return fallback

        jira = worker_outputs.get(AgentType.JIRA_ANALYST.value, {}) or {}
        code = worker_outputs.get(AgentType.CODEBASE_ANALYST.value, {}) or {}
        docs = worker_outputs.get(AgentType.DOCS_ANALYST.value, {}) or {}
        transcripts = worker_outputs.get(AgentType.TRANSCRIPT_ANALYST.value, {}) or {}
        return {
            "jira_summary": _text(jira, "task_summary"),
            "code_context": _text(code, "suggested_code_approach")
            or _text(code, "architecture_notes"),
            "doc_context": _text(docs, "useful_context_for_task"),
            "transcript_context": _text(transcripts, "useful_context_for_task"),
            "previous_run_context": "",
        }

    @staticmethod
    def _derive_recommended_action(
        worker_outputs: dict[str, Any],
        overall_risk: RiskLevel,
        approval_required: bool,
    ) -> dict[str, Any]:
        executor = worker_outputs.get(AgentType.EXECUTOR.value, {}) or {}
        action_type = executor.get("action_taken") or "draft_doc_update"
        draft = executor.get("draft_output") or ""
        description = (
            "Publish the drafted onboarding guide and link it from the Jira ticket."
            if approval_required
            else "Share the draft with the assignee for feedback before publishing."
        )
        return {
            "action_type": action_type,
            "description": description,
            "requires_human_approval": approval_required,
            "draft_output": draft,
        }

    @staticmethod
    def _sources_used(project_data: ProjectData) -> list[str]:
        sources: list[str] = []
        for d in project_data.docs:
            if d.title:
                sources.append(f"doc:{d.title}")
        for t in project_data.transcripts:
            if t.title:
                sources.append(f"transcript:{t.title}")
        for r in project_data.github_repositories:
            sources.append(f"repo:{r.name}")
        for f in project_data.code_files:
            if f.path:
                sources.append(f"code:{f.path}")
        return sources

    def _render_full_prompt(
        self, project_data: ProjectData, current_task: dict[str, Any]
    ) -> str:
        return (
            f"SYSTEM:\n{self.system_prompt}\n\n"
            f"CURRENT TASK:\n{json.dumps(current_task, indent=2, default=str)}\n\n"
            f"USER GOAL: {project_data.user_goal or 'not provided'}\n"
            f"CONSTRAINTS: {project_data.constraints}\n"
        )
