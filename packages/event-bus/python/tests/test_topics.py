"""Topic name contract."""

from __future__ import annotations

from mycelium_event_bus import Topic


def test_topic_values_are_stream_names() -> None:
    assert Topic.AGENTS_TASKS.value == "agents.tasks"
    assert Topic.AGENTS_RESULTS.value == "agents.results"
    assert Topic.EVENTS_RAW.value == "events.raw"
    assert Topic.EVENTS_PROCESSED.value == "events.processed"
