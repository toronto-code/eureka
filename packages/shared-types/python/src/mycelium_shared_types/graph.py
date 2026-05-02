"""Knowledge graph primitives shared across services for graph queries.

These are *transport* shapes used at API boundaries (e.g. ``GET /graph``).
The Neo4j-backed canonical model lives inside services/knowledge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str = Field(description="person | service | repo | document | concept | ...")
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    source_id: str
    target_id: str
    type: str = Field(description="OWNS | CONTRIBUTES_TO | DEPENDS_ON | MENTIONED_IN | ...")
    properties: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
