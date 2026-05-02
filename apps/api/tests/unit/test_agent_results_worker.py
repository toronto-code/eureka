"""Unit tests for the agents.results ingestion handler."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

import mycelium_api.workers.agent_results as ar
from mycelium_db import AuditRow


@dataclass
class FakeTaskRow:
    task_id: str
    agent_id: str
    agent_type: str = "chat"
    input_data: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = "c"
    parent_correlation_id: str | None = None
    status: str = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: dict[str, Any] | None = None
    error: str | None = None


class MagicResult:
    def __init__(self, value: FakeTaskRow | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> FakeTaskRow | None:
        return self._value


def make_get_session(row: FakeTaskRow | None) -> Any:
    audits: list[Any] = []

    @asynccontextmanager
    async def _fake():
        class S:
            async def execute(self, _stmt: object) -> MagicResult:
                return MagicResult(row)

            def add(self, obj: Any) -> None:
                audits.append(obj)

        yield S()

    _fake.audits = audits  # type: ignore[attr-defined]
    return _fake


@pytest.mark.asyncio
async def test_handle_missing_task_id_no_db_session(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = AsyncMock()
    monkeypatch.setattr(ar, "get_event_bus", lambda: bus)

    used = False

    @asynccontextmanager
    async def fail():
        nonlocal used
        used = True
        yield None

    monkeypatch.setattr(ar, "get_session", fail)
    await ar._handle("m1", {"status": "succeeded"})
    assert not used
    bus.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_unknown_task_acks(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = AsyncMock()
    monkeypatch.setattr(ar, "get_event_bus", lambda: bus)
    sess = make_get_session(None)
    monkeypatch.setattr(ar, "get_session", sess)

    await ar._handle("mid", {"task_id": "missing", "status": "succeeded"})
    bus.ack.assert_awaited()
    assert sess.audits == []  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_valid_transition_queued_to_running(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = AsyncMock()
    row = FakeTaskRow(task_id="t1", agent_id="a1", status="queued")
    sess = make_get_session(row)
    monkeypatch.setattr(ar, "get_event_bus", lambda: bus)
    monkeypatch.setattr(ar, "get_session", sess)

    await ar._handle("mid", {"task_id": "t1", "status": "running"})

    assert row.status == "running"
    audits = sess.audits  # type: ignore[attr-defined]
    assert len(audits) == 1
    assert isinstance(audits[0], AuditRow)
    assert audits[0].action == "task.running"
    bus.ack.assert_awaited()


@pytest.mark.asyncio
async def test_forbidden_transition_keeps_status(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = AsyncMock()
    row = FakeTaskRow(task_id="t1", agent_id="a1", status="queued")
    sess = make_get_session(row)
    monkeypatch.setattr(ar, "get_event_bus", lambda: bus)
    monkeypatch.setattr(ar, "get_session", sess)

    await ar._handle("mid", {"task_id": "t1", "status": "succeeded", "result": {"ok": True}})
    assert row.status == "queued"
    assert sess.audits == []  # type: ignore[attr-defined]
    bus.ack.assert_awaited()


@pytest.mark.asyncio
async def test_running_to_succeeded_stores_result(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = AsyncMock()
    row = FakeTaskRow(task_id="t1", agent_id="a1", status="running")
    sess = make_get_session(row)
    monkeypatch.setattr(ar, "get_event_bus", lambda: bus)
    monkeypatch.setattr(ar, "get_session", sess)

    await ar._handle(
        "mid",
        {"task_id": "t1", "status": "succeeded", "result": {"summary": "done"}},
    )
    assert row.status == "succeeded"
    assert row.result == {"summary": "done"}
    bus.ack.assert_awaited()
