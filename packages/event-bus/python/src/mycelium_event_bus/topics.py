"""Canonical Redis Stream topic names. Single source of truth."""

from __future__ import annotations

from enum import Enum


class Topic(str, Enum):
    EVENTS_RAW = "events.raw"
    EVENTS_PROCESSED = "events.processed"
    EVENTS_DLQ = "events.dlq"
    AGENTS_TASKS = "agents.tasks"
    AGENTS_RESULTS = "agents.results"
    WORKFLOWS_APPROVALS = "workflows.approvals"
    GRAPH_UPDATES = "graph.updates"
