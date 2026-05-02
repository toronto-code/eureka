"""Permission preference queries.

Used by agent-runtime to ask: "Given this user and this action, should I
auto-approve, require approval, or block?"
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from mycelium_learning.models.base import ModelKind

router = APIRouter(prefix="/preferences", tags=["preferences"])


def get_trainer():
    """Trainer dependency - injected by main.py via app.state."""
    from mycelium_learning.main import trainer
    if trainer is None:
        raise HTTPException(status_code=503, detail="trainer not initialized")
    return trainer


@router.get("/users/{user_id}")
async def get_user_preferences(user_id: str) -> dict[str, Any]:
    """Get all permission preferences learned for a user."""
    trainer = get_trainer()
    model = await trainer.get_user_model(user_id, ModelKind.PERMISSIONS)
    return {
        "user_id": user_id,
        "preferences": model.summary(),
    }


@router.get("/users/{user_id}/actions/{action_type}")
async def get_user_action_preference(
    user_id: str,
    action_type: str,
) -> dict[str, Any]:
    """Get preference suggestion for a specific user + action type."""
    trainer = get_trainer()
    model = await trainer.get_user_model(user_id, ModelKind.PERMISSIONS)
    return {
        "user_id": user_id,
        **model.get_suggestion(action_type),
    }


@router.get("/global")
async def get_global_preferences() -> dict[str, Any]:
    """Get org-wide permission preferences."""
    trainer = get_trainer()
    model = trainer.get_global_model(ModelKind.PERMISSIONS)
    return {
        "scope": "global",
        "preferences": model.summary(),
    }


@router.get("/global/actions/{action_type}")
async def get_global_action_preference(
    action_type: str,
) -> dict[str, Any]:
    """Get org-wide preference for an action type."""
    trainer = get_trainer()
    model = trainer.get_global_model(ModelKind.PERMISSIONS)
    return {
        "scope": "global",
        **model.get_suggestion(action_type),
    }
