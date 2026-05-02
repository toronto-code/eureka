"""Reasoning skill - think through problems and plan multi-step tasks.

This skill doesn't execute actions itself but helps structure and plan work.
In production, this would integrate with an LLM for actual reasoning.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


class ReasoningSkill(BaseSkill):
    """Think through problems and plan multi-step tasks.

    Input data:
        - prompt: The question or problem to reason about
        - context: Additional context from knowledge graph
        - max_steps: Maximum number of steps to plan (default: 10)

    Returns:
        - analysis: Analysis of the problem
        - plan: List of planned steps
        - considerations: Things to keep in mind

    Note: In production, this would call an LLM. For now it returns a structured
    placeholder that shows the expected output format.
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
        max_steps = input_data.get("max_steps", 10)
        knowledge = input_data.get("knowledge", context)

        has_knowledge = bool(
            knowledge.get("nodes") or knowledge.get("edges")
        ) if isinstance(knowledge, dict) else bool(knowledge)

        return {
            "success": True,
            "analysis": {
                "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
                "has_context": has_knowledge,
                "context_summary": self._summarize_context(knowledge),
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
            "note": "Production version would use LLM for actual reasoning",
        }

    def _summarize_context(self, knowledge: Any) -> str:
        if not knowledge:
            return "No context provided"

        if isinstance(knowledge, dict):
            nodes = knowledge.get("nodes", [])
            edges = knowledge.get("edges", [])
            if nodes or edges:
                return f"{len(nodes)} nodes, {len(edges)} edges from knowledge graph"
            return "Empty knowledge graph"

        if isinstance(knowledge, str):
            return f"Text context: {len(knowledge)} chars"

        return f"Context type: {type(knowledge).__name__}"


class PlanSkill(BaseSkill):
    """Create a structured plan for a task.

    Input data:
        - task: Description of the task
        - constraints: Any constraints or requirements
        - context: Additional context

    Returns:
        - steps: List of planned steps with actions
        - estimated_actions: Number of actions this will take
        - risks: Potential risks or issues
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
        task = input_data.get("task", "")
        constraints = input_data.get("constraints", [])

        if not task:
            return {"error": "No task provided", "success": False}

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
        }


class SummarizeSkill(BaseSkill):
    """Summarize content or a prompt.

    Replaces the original stub summarize skill with a more structured version.

    Input data:
        - prompt: Text to summarize
        - max_length: Maximum summary length (default: 200)

    Returns:
        - summary: The summary
        - original_length: Length of original text
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
        max_length = input_data.get("max_length", 200)

        if not prompt:
            return {
                "success": True,
                "summary": "(no content to summarize)",
                "original_length": 0,
            }

        summary = prompt[:max_length]
        if len(prompt) > max_length:
            summary = summary.rsplit(" ", 1)[0] + "..."

        return {
            "success": True,
            "summary": f"(stub) summary of: {summary}",
            "original_length": len(prompt),
            "tokens": len(prompt.split()),
            "stub": True,
        }
