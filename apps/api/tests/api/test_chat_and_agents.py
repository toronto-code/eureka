"""FastAPI router smoke tests (mocked persistence + bus)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycelium_api.auth import CurrentUser, get_current_user
from mycelium_api.routers import agents as agents_router
from mycelium_api.routers import chat as chat_router


@pytest.fixture()
def dev_user() -> CurrentUser:
    return CurrentUser(id="dev-user-1", email="dev@mycelium.local", role="employee")


@pytest.fixture()
def captured_tasks() -> list[dict[str, Any]]:
    return []


@pytest.fixture()
def chat_app(dev_user: CurrentUser, captured_tasks: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    async def fake_persist(**kwargs: Any) -> None:
        captured_tasks.append(kwargs)

    monkeypatch.setattr(
        "mycelium_api.routers.chat.persist_and_publish_task",
        fake_persist,
    )

    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_current_user] = lambda: dev_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture()
def agents_app(dev_user: CurrentUser, captured_tasks: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch):
    async def fake_persist(**kwargs: Any) -> None:
        captured_tasks.append(kwargs)

    monkeypatch.setattr(
        "mycelium_api.routers.agents.persist_and_publish_task",
        fake_persist,
    )

    app = FastAPI()
    app.include_router(agents_router.router)
    app.dependency_overrides[get_current_user] = lambda: dev_user
    yield app
    app.dependency_overrides.clear()


def test_chat_dispatches_with_default_agent(chat_app: FastAPI, captured_tasks: list) -> None:
    client = TestClient(chat_app)
    r = client.post("/chat", json={"prompt": "hello world"})
    assert r.status_code == 200
    body = r.json()
    assert body["agent_id"] == "agent-dev-user-1"
    assert body["task_id"].startswith("task-")
    assert body["correlation_id"].startswith("api.chat:")
    assert len(captured_tasks) == 1
    kw = captured_tasks[0]
    assert kw["agent_id"] == body["agent_id"]
    assert kw["task_id"] == body["task_id"]
    assert kw["agent_type"] == "project_orchestrator"
    assert kw["input_data"]["prompt"] == "hello world"


def test_chat_accepts_custom_agent_id(chat_app: FastAPI, captured_tasks: list) -> None:
    client = TestClient(chat_app)
    r = client.post("/chat", json={"prompt": "x", "agent_id": "custom-agent"})
    assert r.status_code == 200
    assert r.json()["agent_id"] == "custom-agent"


def test_chat_passes_project_data_and_legacy_agent_type(
    chat_app: FastAPI, captured_tasks: list
) -> None:
    client = TestClient(chat_app)
    r = client.post(
        "/chat",
        json={
            "prompt": "hi",
            "agent_type": "chat",
            "project_data": {"repos": ["a/b"], "phase": "discovery"},
        },
    )
    assert r.status_code == 200
    kw = captured_tasks[0]
    assert kw["agent_type"] == "chat"
    assert kw["input_data"]["project_data"] == {"repos": ["a/b"], "phase": "discovery"}


def test_create_agent_task_under_path(agents_app: FastAPI, captured_tasks: list) -> None:
    client = TestClient(agents_app)
    r = client.post(
        "/agents/my-agent/tasks",
        json={"agent_type": "triage", "input_data": {"k": 1}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert len(captured_tasks) == 1
    kw = captured_tasks[0]
    assert kw["agent_id"] == "my-agent"
    assert kw["agent_type"] == "triage"


def test_list_tasks_uses_db_session(monkeypatch: pytest.MonkeyPatch, dev_user: CurrentUser) -> None:
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    agent_row = MagicMock()
    agent_row.owner_user_id = dev_user.id

    task_row = MagicMock()
    task_row.task_id = "task-1"
    task_row.agent_id = "agent-dev-user-1"
    task_row.agent_type = "chat"
    task_row.status = "succeeded"
    task_row.correlation_id = "cid"
    task_row.parent_correlation_id = None
    task_row.created_at = datetime.now(timezone.utc)
    task_row.updated_at = task_row.created_at
    task_row.result = {"summary": "ok"}
    task_row.error = None

    r_agent = MagicMock()
    r_agent.scalar_one_or_none.return_value = agent_row
    r_tasks = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [task_row]
    r_tasks.scalars.return_value = mock_scalars

    exec_iter = iter([r_agent, r_tasks])

    @asynccontextmanager
    async def fake_session():
        class S:
            async def execute(self, _stmt: object) -> MagicMock:
                return next(exec_iter)

        yield S()

    monkeypatch.setattr("mycelium_api.routers.agents.get_session", fake_session)

    app = FastAPI()
    app.include_router(agents_router.router)
    app.dependency_overrides[get_current_user] = lambda: dev_user

    client = TestClient(app)
    r = client.get("/agents/agent-dev-user-1/tasks")
    assert r.status_code == 200
    payload = r.json()
    assert len(payload) == 1
    assert payload[0]["task_id"] == "task-1"
    assert payload[0]["status"] == "succeeded"


def test_get_single_task_not_found(monkeypatch: pytest.MonkeyPatch, dev_user: CurrentUser) -> None:
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock

    agent_row = MagicMock()
    agent_row.owner_user_id = dev_user.id

    @asynccontextmanager
    async def fake_session():
        class S:
            def __init__(self) -> None:
                self._n = 0

            async def execute(self, _stmt: object) -> MagicMock:
                self._n += 1
                if self._n == 1:
                    return MagicMock(scalar_one_or_none=MagicMock(return_value=agent_row))
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        yield S()

    monkeypatch.setattr("mycelium_api.routers.agents.get_session", fake_session)

    app = FastAPI()
    app.include_router(agents_router.router)
    app.dependency_overrides[get_current_user] = lambda: dev_user
    client = TestClient(app)

    r = client.get("/agents/agent-dev-user-1/tasks/task-missing")
    assert r.status_code == 404
