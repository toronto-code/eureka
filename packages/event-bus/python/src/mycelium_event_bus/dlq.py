"""Dead-letter queue payload contract."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorCategory(str, Enum):
    CLASSIFICATION_FAILED = "classification_failed"
    SCHEMA_INVALID = "schema_invalid"
    HANDLER_EXCEPTION = "handler_exception"
    DOWNSTREAM_UNAVAILABLE = "downstream_unavailable"
    UNKNOWN = "unknown"


class DLQMessage(BaseModel):
    """Every message published to ``events.dlq`` MUST conform to this shape."""

    model_config = ConfigDict(extra="forbid")

    error_category: ErrorCategory
    retry_count: int = Field(ge=0)
    original_event: dict[str, Any]
    error_message: str = ""
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failed_by: str = Field(description="The service that gave up on this event.")
