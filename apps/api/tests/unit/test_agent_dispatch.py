"""Tests for agent task persistence + Redis publish ordering."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from mycelium_api.agent_dispatch import ensure_agent_owned, persist_and_publish_task
from mycelium_db import AgentRow, AgentTaskRow
from mycelium_event_bus import Topic


@pytest.mark.asyncio
async def test_ensure_agent_owned_creates_agent() -> None:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    await ensure_agent_owned(
        session,
        agent_id="agent-u1",
        owner_user_id="u1",
        default_capabilities=["chat"],
    )

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert isinstance(added, AgentRow)
    assert added.id == "agent-u1"
    assert added.owner_user_id == "u1"
    assert added.capabilities == ["chat"]


@pytest.mark.asyncio
async def test_ensure_agent_owned_forbidden_wrong_owner() -> None:
    session = MagicMock()
    existing = MagicMock(spec=AgentRow)
    existing.owner_user_id = "other"
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(HTTPException) as ei:
        await ensure_agent_owned(
            session,
            agent_id="agent-x",
            owner_user_id="u1",
            default_capabilities=["chat"],
        )
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_persist_and_publish_task_commits_before_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    order: list[str] = []

    @asynccontextmanager
    async def fake_get_session():
        order.append("session_enter")
        try:
            yield session
        finally:
            order.append("session_exit_commit")

    monkeypatch.setattr(
        "mycelium_api.agent_dispatch.get_session",
        fake_get_session,
    )

    bus = AsyncMock()

    await persist_and_publish_task(
        bus=bus,
        task_id="task-abc",
        agent_id="agent-u1",
        agent_type="chat",
        input_data={"prompt": "hi"},
        correlation_id="api.chat:digest:suffix",
        parent_correlation_id=None,
        owner_user_id="u1",
        agent_capabilities_when_created=["chat", "summarize"],
    )

    assert order == ["session_enter", "session_exit_commit"]
    bus.publish.assert_awaited_once()
    args, kwargs = bus.publish.await_args
    assert args[0] is Topic.AGENTS_TASKS
    payload = args[1]
    assert payload["task_id"] == "task-abc"
    assert payload["agent_id"] == "agent-u1"
    assert payload["agent_type"] == "chat"
    assert payload["input_data"] == {"prompt": "hi"}
    assert payload["correlation_id"] == "api.chat:digest:suffix"
    assert kwargs.get("correlation_id") == "api.chat:digest:suffix"

    adds = [c[0][0] for c in session.add.call_args_list]
    assert any(isinstance(a, AgentTaskRow) and a.status == "queued" for a in adds)

