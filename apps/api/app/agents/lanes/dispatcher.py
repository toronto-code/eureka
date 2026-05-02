"""LaneDispatcher: map an OL route to a concrete lane and run it."""
from __future__ import annotations

from typing import Mapping

from app.agents.lanes.base import BaseLane, LaneContext
from app.agents.lanes.blocked import BlockedLane, HumanReviewLane
from app.agents.lanes.complex_code import ComplexCodeLane
from app.agents.lanes.inquiry import InquiryLane
from app.agents.lanes.planning import PlanningLane
from app.agents.lanes.simple_code import SimpleCodeLane
from app.agents.ol.schemas import LaneResult


class LaneDispatcher:
    """Route → lane mapping. Lanes can be swapped for testing."""

    def __init__(self, lanes: Mapping[str, BaseLane] | None = None) -> None:
        self._lanes: dict[str, BaseLane] = dict(lanes or self._default_lanes())

    def run(self, ctx: LaneContext) -> LaneResult:
        route = ctx.classification.route
        lane = self._lanes.get(route)
        if lane is None:
            return self._lanes["needs_human_review"].run(ctx)
        result = lane.run(ctx)
        # SimpleCodeLane can self-report "complex signals detected" — auto
        # redirect to ComplexCodeLane in that case so the run still lands
        # somewhere useful.
        if (
            route == "simple_code"
            and result.status == "blocked"
            and (result.extra or {}).get("should_downgrade_to_complex")
        ):
            ctx.classification.route = "complex_code"
            fallback = self._lanes["complex_code"].run(ctx)
            fallback.extra = {
                **(fallback.extra or {}),
                "downgraded_from_simple_code": True,
                "simple_code_result": result.model_dump(),
            }
            return fallback
        return result

    @staticmethod
    def _default_lanes() -> dict[str, BaseLane]:
        return {
            "inquiry": InquiryLane(),
            "simple_code": SimpleCodeLane(),
            "complex_code": ComplexCodeLane(),
            "planning": PlanningLane(),
            "blocked": BlockedLane(),
            "needs_human_review": HumanReviewLane(),
        }
