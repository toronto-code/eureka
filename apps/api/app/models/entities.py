"""Lightweight entity + relationship tables.

Designed so a graph backend (Neo4j, FalkorDB, Graphiti) can later mirror the
same data without changing the application code.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._mixins import TimestampMixin, UUIDPKMixin


class Entity(Base, UUIDPKMixin, TimestampMixin):
    """A typed entity (person, service, repo, ticket, doc, etc.)."""

    __tablename__ = "entities"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Relationship(Base, UUIDPKMixin, TimestampMixin):
    """A directed relation between two entities."""

    __tablename__ = "relationships"

    source_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation: Mapped[str] = mapped_column(String(128), nullable=False)
    relation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
