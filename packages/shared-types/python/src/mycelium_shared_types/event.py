"""MyceliumEvent — the canonical event schema across every service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SCHEMA_VERSION = "1.0"


class MyceliumEventActor(BaseModel):
    """Who did the thing. Could be a human or another agent/service."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = Field(description="user | agent | service | bot")
    display_name: Optional[str] = None


class MyceliumEventObject(BaseModel):
    """What was acted on. A PR, a file, a Slack message, a ticket, etc."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = Field(description="pull_request | commit | message | ticket | file | service | ...")
    url: Optional[str] = None


class MyceliumEvent(BaseModel):
    """A normalized fact about something that happened.

    Contract:
      - `correlation_id` is mandatory; never null.
      - `parent_correlation_id` is set when this event modifies/extends an earlier event
        (e.g. Slack edit, GitHub force-push, Jira merge, threaded reply).
      - `schema_version` is mandatory; default "1.0". Bump when fields change.
        Consumers handle unknown versions gracefully.

    correlation_id generation (priority order):
      1. Natural ID if one exists (PR number, Slack thread ID).
      2. hash(source + object.id + time_window) + uuid suffix.
      3. API assigns a fallback if the producer omits it.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Globally unique event id (uuid4 recommended).")
    type: str = Field(description="e.g. github.pr.opened, slack.message.posted, observer.command.run")
    source: str = Field(description="github | slack | jira | observer | agent | api | ...")
    actor: MyceliumEventActor
    object: MyceliumEventObject
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION)

    metadata: dict[str, Any] = Field(default_factory=dict)

    correlation_id: str = Field(
        description="Mandatory. Groups related events into a stream partition.",
    )
    parent_correlation_id: Optional[str] = Field(
        default=None,
        description="Set when this event modifies/extends a prior event.",
    )
