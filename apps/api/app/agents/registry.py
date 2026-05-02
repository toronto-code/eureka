"""AgentRegistry: register, look up, and run agent classes by AgentType.

Designed so adding a new agent type is a one-line registration.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING

from app.agents.base import AgentInput, AgentOutput, AgentType

if TYPE_CHECKING:
    from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Holds factories for every agent class."""

    def __init__(self) -> None:
        self._factories: dict[AgentType, Callable[[], "BaseAgent"]] = {}

    def register(self, agent_type: AgentType, factory: Callable[[], "BaseAgent"]) -> None:
        if agent_type in self._factories:
            logger.warning("Re-registering agent factory for %s", agent_type)
        self._factories[agent_type] = factory

    def get(self, agent_type: AgentType) -> "BaseAgent":
        if agent_type not in self._factories:
            raise KeyError(f"No agent registered for type {agent_type}")
        return self._factories[agent_type]()

    def has(self, agent_type: AgentType) -> bool:
        return agent_type in self._factories

    def available_types(self) -> list[AgentType]:
        return list(self._factories.keys())

    def run_agent(self, agent_type: AgentType, agent_input: AgentInput) -> AgentOutput:
        agent = self.get(agent_type)
        return agent.run(agent_input)


def _build_default_registry() -> AgentRegistry:
    """Wire up every concrete agent class.

    Imports happen here (not at module load) to avoid circular imports between
    the registry, base, and worker modules.
    """
    from app.agents.orchestrator import OrchestratorAgent
    from app.agents.workers.codebase_analyst import CodebaseAnalystAgent
    from app.agents.workers.docs_analyst import DocsAnalystAgent
    from app.agents.workers.executor import ExecutorAgent
    from app.agents.workers.jira_analyst import JiraAnalystAgent
    from app.agents.workers.planner import PlannerAgent
    from app.agents.workers.reviewer import ReviewerAgent
    from app.agents.workers.risk_safety import RiskSafetyAgent
    from app.agents.workers.transcript_analyst import TranscriptAnalystAgent

    registry = AgentRegistry()
    registry.register(AgentType.ORCHESTRATOR, OrchestratorAgent)
    registry.register(AgentType.JIRA_ANALYST, JiraAnalystAgent)
    registry.register(AgentType.CODEBASE_ANALYST, CodebaseAnalystAgent)
    registry.register(AgentType.TRANSCRIPT_ANALYST, TranscriptAnalystAgent)
    registry.register(AgentType.DOCS_ANALYST, DocsAnalystAgent)
    registry.register(AgentType.PLANNER, PlannerAgent)
    registry.register(AgentType.RISK_SAFETY, RiskSafetyAgent)
    registry.register(AgentType.EXECUTOR, ExecutorAgent)
    registry.register(AgentType.REVIEWER, ReviewerAgent)
    return registry


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    """Process-wide cached registry."""
    return _build_default_registry()
