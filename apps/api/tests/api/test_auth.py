"""Auth dependency behaviour."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from mycelium_api import config
from mycelium_api.auth import get_current_user


@pytest.fixture(autouse=True)
def _clear_dev_mode_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """``is_dev_mode`` is LRU-cached; clear between tests."""
    yield
    config.is_dev_mode.cache_clear()


@pytest.mark.asyncio
async def test_dev_mode_bypasses_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_MODE", "true")
    config.is_dev_mode.cache_clear()
    monkeypatch.setattr("mycelium_api.auth.DEV_USER_ID", "dev-special")
    monkeypatch.setattr("mycelium_api.auth.DEV_USER_EMAIL", "special@example.com")

    user = await get_current_user(authorization=None)
    assert user.id == "dev-special"
    assert user.email == "special@example.com"


@pytest.mark.asyncio
async def test_prod_mode_requires_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_MODE", "false")
    config.is_dev_mode.cache_clear()

    with pytest.raises(HTTPException) as ei:
        await get_current_user(authorization=None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_prod_mode_rejects_bad_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_MODE", "false")
    config.is_dev_mode.cache_clear()

    monkeypatch.setattr(config, "JWT_SECRET", "unit-test-secret")
    monkeypatch.setattr(config, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr("mycelium_api.auth.JWT_SECRET", "unit-test-secret")
    monkeypatch.setattr("mycelium_api.auth.JWT_ALGORITHM", "HS256")

    with pytest.raises(HTTPException) as ei:
        await get_current_user(authorization="Bearer not-a-jwt")
    assert ei.value.status_code == 401
