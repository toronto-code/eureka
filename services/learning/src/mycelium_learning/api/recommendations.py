"""Skill and action recommendations.

Used by agent-runtime to ask: "For this task, which skills are most likely
to succeed?"
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from mycelium_learning.models.base import ModelKind

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def get_trainer():
    from mycelium_learning.main import trainer
    if trainer is None:
        raise HTTPException(status_code=503, detail="trainer not initialized")
    return trainer


@router.get("/skills")
async def recommend_skills(
    user_id: str | None = Query(None),
    candidates: list[str] | None = Query(None),
    top_n: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    """Get ranked skill recommendations.

    Query params:
        user_id: If provided, use user-specific model (fallback to global).
        candidates: Limit rankings to these skill names (comma-separated in URL).
        top_n: Max number of skills to return.
    """
    trainer = get_trainer()

    if user_id:
        model = await trainer.get_user_model(user_id, ModelKind.SKILLS)
    else:
        model = trainer.get_global_model(ModelKind.SKILLS)

    recommendations = model.recommend(candidates=candidates, top_n=top_n)
    return {
        "user_id": user_id,
        "scope": "user" if user_id else "global",
        "recommendations": recommendations,
    }


@router.get("/patterns")
async def recommend_patterns(
    top_n: int = Query(10, ge=1, le=50),
    min_total: int = Query(3, ge=1),
) -> dict[str, Any]:
    """Get top action patterns that lead to success."""
    trainer = get_trainer()
    model = trainer.get_global_model(ModelKind.PATTERNS)
    return {
        "scope": "global",
        "patterns": model.top_patterns(top_n=top_n, min_total=min_total),
    }


@router.get("/models/{kind}")
async def get_model_summary(kind: str) -> dict[str, Any]:
    """Get a summary of a specific model's learned state."""
    try:
        model_kind = ModelKind(kind)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind: {kind}. Must be one of {[k.value for k in ModelKind]}",
        )

    trainer = get_trainer()
    model = trainer.get_global_model(model_kind)
    return model.summary()
