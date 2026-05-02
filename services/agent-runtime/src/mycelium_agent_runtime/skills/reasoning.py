"""Reasoning skills — plan, reason, summarize.

Each skill attempts a real LLM call first. When no LLM is configured (no
``ANTHROPIC_API_KEY`` or ``OPENAI_API_KEY``), or when the LLM request fails,
the skills transparently fall back to a structured heuristic response so
local dev / CI / hackathon demos keep working without any keys.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.llm import LLMClient
from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


_shared_llm: LLMClient | None = None


def _llm() -> LLMClient:
    """Lazy module-level LLM client (reused across skill invocations)."""
    global _shared_llm
    if _shared_llm is None:
        _shared_llm = LLMClient()
    return _shared_llm


def _format_knowledge(knowledge: Any) -> str:
    if not knowledge:
        return "(no prior context)"
    if isinstance(knowledge, dict):
        nodes = knowledge.get("nodes", [])
        edges = knowledge.get("edges", [])
        if nodes or edges:
            return f"knowledge graph: {len(nodes)} nodes, {len(edges)} edges"
        return "(empty knowledge graph)"
    if isinstance(knowledge, str):
        return knowledge[:1200]
    return str(knowledge)[:800]


def _format_memories(memories: Any) -> str:
    if not memories:
        return ""
    if isinstance(memories, list):
        lines = []
        for mem in memories[:5]:
            if isinstance(mem, dict):
                text = mem.get("summary") or mem.get("content") or str(mem)
            else:
                text = str(mem)
            lines.append(f"- {text[:240]}")
        return "\n".join(lines)
    return str(memories)[:600]


class ReasoningSkill(BaseSkill):
    """Think through problems and plan multi-step tasks.

    Input data:
        - prompt: The question or problem to reason about
        - context / knowledge: Additional context
        - max_steps: Maximum number of steps to plan (default: 10)
        - relevant_memories: Optional long-term memory snippets
        - recent_turns: Optional short-term conversation context

    Returns a dict with ``analysis``, ``plan``, ``considerations``, and a
    ``stub`` flag indicating whether the response came from the LLM or the
    heuristic fallback.
    """

    name = "reasoning"
    description = "Think through problems and plan multi-step tasks"
    required_capabilities = []

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        prompt = input_data.get("prompt", "")
        max_steps = int(input_data.get("max_steps", 10))
        knowledge = input_data.get("knowledge", context)
        memories = input_data.get("relevant_memories", [])
        recent = input_data.get("recent_turns", "")

        llm = _llm()
        if llm.enabled:
            user_msg = (
                f"User prompt: {prompt}\n\n"
                f"Context: {_format_knowledge(knowledge)}\n"
                f"Recent conversation:\n{recent or '(none)'}\n"
                f"Relevant memories:\n{_format_memories(memories) or '(none)'}\n\n"
                f"Analyze the prompt, then produce a plan of at most {max_steps} "
                "concrete steps. Return JSON with keys:\n"
                '  "analysis": {"summary": str, "key_unknowns": [str]},\n'
                '  "plan": [{"step": int, "action": str, "description": str}],\n'
                '  "considerations": [str]'
            )
            system = (
                "You are a careful software engineering planner. Think step "
                "by step, surface risks, and keep steps concrete and testable."
            )
            parsed, resp = await llm.complete_json(user_msg, system=system)
            if parsed:
                plan = parsed.get("plan") or []
                if isinstance(plan, list):
                    plan = plan[:max_steps]
                return {
                    "success": True,
                    "analysis": parsed.get("analysis")
                    or {"summary": resp.text[:400]},
                    "plan": plan,
                    "considerations": parsed.get("considerations", []),
                    "model": resp.model,
                    "provider": resp.provider,
                    "stub": False,
                }
            # LLM was configured but the call or parse failed → fall through.

        return self._heuristic(prompt, knowledge, max_steps)

    def _heuristic(
        self, prompt: str, knowledge: Any, max_steps: int
    ) -> dict[str, Any]:
        has_knowledge = (
            bool(knowledge.get("nodes") or knowledge.get("edges"))
            if isinstance(knowledge, dict)
            else bool(knowledge)
        )
        return {
            "success": True,
            "analysis": {
                "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
                "has_context": has_knowledge,
                "context_summary": _format_knowledge(knowledge),
            },
            "plan": [
                {
                    "step": 1,
                    "action": "analyze",
                    "description": "Analyze the problem and gather requirements",
                },
                {
                    "step": 2,
                    "action": "research",
                    "description": "Search codebase for relevant context",
                },
                {
                    "step": 3,
                    "action": "implement",
                    "description": "Implement the solution",
                },
                {
                    "step": 4,
                    "action": "verify",
                    "description": "Verify the solution works correctly",
                },
            ][:max_steps],
            "considerations": [
                "Check existing code patterns before implementing",
                "Consider edge cases and error handling",
                "Ensure changes don't break existing functionality",
            ],
            "stub": True,
            "provider": "stub",
            "note": "LLM not configured; returning heuristic plan.",
        }


class PlanSkill(BaseSkill):
    """Create a structured plan for a task.

    Input data:
        - task (or prompt): Description of the task
        - constraints: Any constraints or requirements
        - context / knowledge: Additional context

    Returns ``steps`` (list of objects with ``id``, ``name``, ``actions``,
    ``depends_on``), ``estimated_actions``, and ``risks``.
    """

    name = "plan"
    description = "Create a structured plan for a task"
    required_capabilities = []

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        task = input_data.get("task") or input_data.get("prompt", "")
        constraints = input_data.get("constraints", [])
        knowledge = input_data.get("knowledge", context)

        if not task:
            return {"error": "No task provided", "success": False}

        llm = _llm()
        if llm.enabled:
            constraint_str = (
                ", ".join(constraints)
                if isinstance(constraints, list) and constraints
                else "(none)"
            )
            user_msg = (
                f"Task: {task}\n"
                f"Constraints: {constraint_str}\n"
                f"Context: {_format_knowledge(knowledge)}\n\n"
                "Produce a dependency-ordered plan. Return JSON with keys:\n"
                '  "steps": [{"id": int, "name": str, "actions": [str], '
                '"depends_on": [int]}],\n'
                '  "estimated_actions": int,\n'
                '  "risks": [str]'
            )
            system = (
                "You are a senior engineer producing executable work plans. "
                "Keep steps small, list real actions, call out risks."
            )
            parsed, resp = await llm.complete_json(user_msg, system=system)
            if parsed and isinstance(parsed.get("steps"), list):
                return {
                    "success": True,
                    "task": task,
                    "steps": parsed["steps"],
                    "estimated_actions": parsed.get(
                        "estimated_actions", len(parsed["steps"])
                    ),
                    "constraints": constraints,
                    "risks": parsed.get("risks", []),
                    "model": resp.model,
                    "provider": resp.provider,
                    "stub": False,
                }

        return {
            "success": True,
            "task": task,
            "steps": [
                {
                    "id": 1,
                    "name": "Understand requirements",
                    "actions": ["Read relevant files", "Search for patterns"],
                    "depends_on": [],
                },
                {
                    "id": 2,
                    "name": "Implement changes",
                    "actions": ["Modify files", "Add new code"],
                    "depends_on": [1],
                },
                {
                    "id": 3,
                    "name": "Verify changes",
                    "actions": ["Run tests", "Check output"],
                    "depends_on": [2],
                },
            ],
            "estimated_actions": 5,
            "constraints": constraints,
            "risks": [
                "May need to modify existing code",
                "Could affect other parts of the system",
            ],
            "stub": True,
            "provider": "stub",
        }


class SummarizeSkill(BaseSkill):
    """Summarize content or a prompt.

    Input data:
        - prompt: Text to summarize
        - max_length: Maximum summary length (default: 400 chars)

    Returns ``summary``, ``original_length``, ``tokens`` (rough word count).
    """

    name = "summarize"
    description = "Summarize a prompt or document"
    required_capabilities = []

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        prompt = input_data.get("prompt", "")
        max_length = int(input_data.get("max_length", 400))

        if not prompt:
            return {
                "success": True,
                "summary": "(no content to summarize)",
                "original_length": 0,
                "tokens": 0,
                "stub": False,
            }

        llm = _llm()
        if llm.enabled:
            user_msg = (
                f"Summarize the following in at most {max_length} characters. "
                "Preserve facts, names, numbers. No preamble.\n\n"
                f"{prompt}"
            )
            resp = await llm.complete(user_msg, temperature=0.1)
            if not resp.stub and resp.text:
                summary = resp.text.strip()
                if len(summary) > max_length:
                    summary = summary[:max_length].rsplit(" ", 1)[0] + "..."
                return {
                    "success": True,
                    "summary": summary,
                    "original_length": len(prompt),
                    "tokens": len(prompt.split()),
                    "model": resp.model,
                    "provider": resp.provider,
                    "stub": False,
                }

        # Heuristic fallback: truncate at the nearest word boundary.
        summary = prompt[:max_length]
        if len(prompt) > max_length:
            summary = summary.rsplit(" ", 1)[0] + "..."
        return {
            "success": True,
            "summary": summary,
            "original_length": len(prompt),
            "tokens": len(prompt.split()),
            "stub": True,
            "provider": "stub",
        }
