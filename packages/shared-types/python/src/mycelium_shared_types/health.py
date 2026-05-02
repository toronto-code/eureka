"""HealthCheck — identical shape across every Mycelium service."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class HealthCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthStatus
    service: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def ok(service: str) -> HealthCheck:
    """Convenience constructor used by every service's ``GET /health``."""
    return HealthCheck(status=HealthStatus.OK, service=service)
