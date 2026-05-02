"""AgentTask lifecycle transition matrix."""

from __future__ import annotations

import pytest

from mycelium_shared_types.agent import AgentTaskStatus
from mycelium_shared_types.transitions import (
    VALID_AGENT_TASK_TRANSITIONS,
    is_valid_agent_task_transition,
)


@pytest.mark.parametrize(
    "current,nxt,expected",
    [
        (AgentTaskStatus.QUEUED, AgentTaskStatus.RUNNING, True),
        (AgentTaskStatus.QUEUED, AgentTaskStatus.SUCCEEDED, False),
        (AgentTaskStatus.QUEUED, AgentTaskStatus.CANCELLED, True),
        (AgentTaskStatus.RUNNING, AgentTaskStatus.SUCCEEDED, True),
        (AgentTaskStatus.RUNNING, AgentTaskStatus.FAILED, True),
        (AgentTaskStatus.RUNNING, AgentTaskStatus.QUEUED, False),
        (AgentTaskStatus.FAILED, AgentTaskStatus.RETRIED, True),
        (AgentTaskStatus.FAILED, AgentTaskStatus.RUNNING, False),
        (AgentTaskStatus.SUCCEEDED, AgentTaskStatus.RUNNING, False),
    ],
)
def test_transition_matrix(
    current: AgentTaskStatus, nxt: AgentTaskStatus, expected: bool
) -> None:
    assert is_valid_agent_task_transition(current, nxt) is expected
    if expected:
        assert nxt in VALID_AGENT_TASK_TRANSITIONS[current]
