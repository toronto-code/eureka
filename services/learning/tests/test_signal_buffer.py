import pytest

from mycelium_learning.signals.buffer import SignalBuffer
from mycelium_learning.signals.types import Outcome, Signal, SignalKind


def _signal(task_id: str) -> Signal:
    return Signal(
        kind=SignalKind.TASK_RESULT,
        outcome=Outcome.SUCCESS,
        task_id=task_id,
    )


@pytest.mark.asyncio
async def test_failed_flush_requeues_signals_for_retry() -> None:
    calls: list[list[Signal]] = []

    async def on_flush(signals: list[Signal]) -> None:
        calls.append(signals)
        if len(calls) == 1:
            raise RuntimeError("temporary trainer failure")

    buffer = SignalBuffer(batch_size=2, interval_seconds=60, on_flush=on_flush)

    await buffer.add(_signal("task-1"))
    await buffer.add(_signal("task-2"))

    assert buffer.stats["buffered"] == 2
    assert buffer.stats["total_flushes"] == 0

    await buffer.flush(reason="retry")

    assert buffer.stats["buffered"] == 0
    assert buffer.stats["total_flushes"] == 1
    assert [[s.task_id for s in batch] for batch in calls] == [
        ["task-1", "task-2"],
        ["task-1", "task-2"],
    ]
