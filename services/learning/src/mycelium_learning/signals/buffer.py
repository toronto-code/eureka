"""In-memory signal buffer with N-signal OR T-time trigger."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from mycelium_learning.signals.types import Signal

logger = logging.getLogger(__name__)

FlushCallback = Callable[[list[Signal]], Awaitable[None]]


class SignalBuffer:
    """Buffers signals until threshold is hit, then flushes to a callback.

    Triggers when:
    - Number of buffered signals reaches batch_size, OR
    - Time since last flush exceeds interval_seconds

    The time-based trigger requires a background ticker to be started.
    """

    def __init__(
        self,
        batch_size: int,
        interval_seconds: int,
        on_flush: FlushCallback,
    ) -> None:
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._on_flush = on_flush
        self._buffer: list[Signal] = []
        self._last_flush = time.monotonic()
        self._lock = asyncio.Lock()
        self._ticker_task: asyncio.Task | None = None
        self._total_signals = 0
        self._total_flushes = 0

    async def add(self, signal: Signal) -> None:
        """Add a signal to the buffer. Triggers flush if batch size reached."""
        async with self._lock:
            self._buffer.append(signal)
            self._total_signals += 1

            if len(self._buffer) >= self._batch_size:
                await self._flush_locked(reason="batch_size")

    async def flush(self, reason: str = "manual") -> None:
        """Manually trigger a flush."""
        async with self._lock:
            await self._flush_locked(reason=reason)

    async def _flush_locked(self, reason: str) -> None:
        """Flush internal. Caller must hold lock."""
        if not self._buffer:
            return

        signals = self._buffer
        self._buffer = []
        self._last_flush = time.monotonic()
        self._total_flushes += 1

        logger.info(
            "Flushing %d signals (reason=%s, total_flushes=%d)",
            len(signals),
            reason,
            self._total_flushes,
        )

        try:
            await self._on_flush(signals)
        except Exception as e:
            logger.exception("Flush callback failed: %s", e)

    def start_ticker(self) -> None:
        """Start the background ticker for time-based flushes."""
        if self._ticker_task is not None:
            return
        self._ticker_task = asyncio.create_task(
            self._run_ticker(), name="signal-buffer-ticker"
        )

    async def stop_ticker(self) -> None:
        """Stop the background ticker."""
        if self._ticker_task is None:
            return
        self._ticker_task.cancel()
        try:
            await self._ticker_task
        except asyncio.CancelledError:
            pass
        self._ticker_task = None

    async def _run_ticker(self) -> None:
        """Periodically check if interval has elapsed and flush if needed."""
        check_interval = max(1, self._interval_seconds // 4)

        while True:
            try:
                await asyncio.sleep(check_interval)
                async with self._lock:
                    elapsed = time.monotonic() - self._last_flush
                    if elapsed >= self._interval_seconds and self._buffer:
                        await self._flush_locked(reason="interval")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ticker error")

    @property
    def stats(self) -> dict:
        return {
            "buffered": len(self._buffer),
            "batch_size": self._batch_size,
            "interval_seconds": self._interval_seconds,
            "total_signals": self._total_signals,
            "total_flushes": self._total_flushes,
            "seconds_since_flush": int(time.monotonic() - self._last_flush),
        }
