"""AgentTask lifecycle transitions. The single source of truth."""

from __future__ import annotations

from mycelium_shared_types.agent import AgentTaskStatus

VALID_AGENT_TASK_TRANSITIONS: dict[AgentTaskStatus, set[AgentTaskStatus]] = {
    AgentTaskStatus.QUEUED: {
        AgentTaskStatus.RUNNING,
        AgentTaskStatus.PENDING_APPROVAL,
        AgentTaskStatus.CANCELLED,
    },
    AgentTaskStatus.PENDING_APPROVAL: {
        AgentTaskStatus.RUNNING,
        AgentTaskStatus.FAILED,
        AgentTaskStatus.CANCELLED,
    },
    AgentTaskStatus.RUNNING: {
        AgentTaskStatus.SUCCEEDED,
        AgentTaskStatus.FAILED,
        AgentTaskStatus.PENDING_APPROVAL,
    },
    AgentTaskStatus.FAILED: {AgentTaskStatus.RETRIED, AgentTaskStatus.CANCELLED},
    AgentTaskStatus.RETRIED: {AgentTaskStatus.SUCCEEDED, AgentTaskStatus.CANCELLED},
    AgentTaskStatus.SUCCEEDED: set(),
    AgentTaskStatus.CANCELLED: set(),
}


def is_valid_agent_task_transition(
    current: AgentTaskStatus, next_status: AgentTaskStatus
) -> bool:
    """Return True if ``current → next_status`` is a permitted lifecycle transition."""
    return next_status in VALID_AGENT_TASK_TRANSITIONS.get(current, set())
