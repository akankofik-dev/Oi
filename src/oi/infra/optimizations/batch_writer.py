"""L1: queue-based batched DB writes for the streaming history tracker.

The stock pipeline calls ``flush_tracker(history_tracker)`` after *every*
stream chunk, which issues a DB write per token. :class:`BatchHistoryWriter`
throttles those flushes: a flush happens at most once per ``interval_seconds``
or every ``max_chunks`` observed chunks, whichever comes first.

``TurnHistoryTracker.observe()`` only accumulates state in memory — nothing is
durable until ``flush()`` runs — so delaying flushes is safe as long as callers
force a final :meth:`flush` when the stream ends or disconnects.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

#: Signature of the wrapped per-chunk persist call
#: (normally ``oi.infra.history.recorder.flush_tracker``).
FlushFn = Callable[[Any], Awaitable[None]]


@dataclass
class _PendingState:
    chunks_since_flush: int = 0
    last_flush_at: float = 0.0


class BatchHistoryWriter:
    """Throttle per-chunk history flushes into time/count-based batches.

    One instance is shared across concurrent turns; bookkeeping is keyed by
    ``id(tracker)`` so interleaved streams never flush each other's data.

    Memory-safe: at most ``max_trackers`` trackers are kept (the oldest is
    evicted when the cap is hit) and entries idle longer than
    ``stale_seconds`` are purged, so abandoned trackers (client disconnect
    without a final flush) can never grow the maps without bound. Callers
    must still call :meth:`flush` at stream end; eviction only drops
    *bookkeeping*, never unflushed chunks (chunks live in the tracker).
    """

    def __init__(
        self,
        *,
        interval_seconds: float = 0.2,
        max_chunks: int = 5,
        max_trackers: int = 512,
        stale_seconds: float = 3600.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if max_chunks < 1:
            raise ValueError("max_chunks must be >= 1")
        if max_trackers < 1:
            raise ValueError("max_trackers must be >= 1")
        self._interval = interval_seconds
        self._max_chunks = max_chunks
        self._max_trackers = max_trackers
        self._stale_seconds = stale_seconds
        self._states: dict[int, _PendingState] = {}
        self._trackers: dict[int, Any] = {}
        self._lock = asyncio.Lock()

    def _purge_stale_locked(self) -> None:
        """Drop bookkeeping idle longer than ``stale_seconds`` (lock held)."""
        now = time.monotonic()
        stale = [
            key
            for key, state in self._states.items()
            if now - state.last_flush_at > self._stale_seconds
            and state.chunks_since_flush == 0
        ]
        for key in stale:
            self._states.pop(key, None)
            self._trackers.pop(key, None)

    def _state_for(self, tracker: Any) -> tuple[int, _PendingState]:
        key = id(tracker)
        state = self._states.get(key)
        if state is None:
            self._purge_stale_locked()
            if len(self._states) >= self._max_trackers:
                # Evict the oldest-idle tracker (bookkeeping only).
                oldest = min(
                    self._states.items(), key=lambda kv: kv[1].last_flush_at
                )[0]
                self._states.pop(oldest, None)
                self._trackers.pop(oldest, None)
            state = _PendingState(last_flush_at=time.monotonic())
            self._states[key] = state
            self._trackers[key] = tracker
        return key, state

    async def maybe_flush(self, tracker: Any, flush_fn: FlushFn) -> None:
        """Record one observed chunk; flush when a batch threshold is reached.

        Drop-in replacement for ``await flush_tracker(history_tracker)`` in the
        per-chunk hot path. The caller must still call :meth:`flush` when the
        stream finishes so tail chunks are never lost.
        """
        async with self._lock:
            _, state = self._state_for(tracker)
            state.chunks_since_flush += 1
            now = time.monotonic()
            due = state.chunks_since_flush >= self._max_chunks or (
                now - state.last_flush_at
            ) >= self._interval
            if not due:
                return
            state.chunks_since_flush = 0
            state.last_flush_at = now
        # Flush outside the lock: the DB write may be slow and must not block
        # bookkeeping for other concurrent trackers.
        try:
            await flush_fn(tracker)
        except Exception:
            logger.exception("BatchHistoryWriter: batched flush failed")

    async def flush(self, tracker: Any, flush_fn: FlushFn) -> None:
        """Force a flush for one tracker — call on stream end / disconnect.

        Without this, chunks buffered since the last batch threshold would be
        lost. Safe to call when nothing is pending (no-op).
        """
        async with self._lock:
            _, state = self._state_for(tracker)
            if state.chunks_since_flush == 0:
                return
            state.chunks_since_flush = 0
            state.last_flush_at = time.monotonic()
        try:
            await flush_fn(tracker)
        except Exception:
            logger.exception("BatchHistoryWriter: forced flush failed")

    async def flush_all(self, flush_fn: FlushFn) -> None:
        """Force-flush every tracked tracker (e.g. on server shutdown)."""
        async with self._lock:
            items = list(self._trackers.items())
            now = time.monotonic()
            for key in items:
                self._states[key].chunks_since_flush = 0
                self._states[key].last_flush_at = now
        for _, tracker in items:
            try:
                await flush_fn(tracker)
            except Exception:
                logger.exception("BatchHistoryWriter: flush_all failed for a tracker")

    def drop(self, tracker: Any) -> None:
        """Forget bookkeeping for a finished tracker (bounds memory growth)."""
        key = id(tracker)
        self._states.pop(key, None)
        self._trackers.pop(key, None)

    def purge_stale(self) -> int:
        """Drop idle bookkeeping entries (no pending chunks); returns count."""
        now = time.monotonic()
        stale = [
            key
            for key, state in self._states.items()
            if now - state.last_flush_at > self._stale_seconds
            and state.chunks_since_flush == 0
        ]
        for key in stale:
            self._states.pop(key, None)
            self._trackers.pop(key, None)
        return len(stale)

    @property
    def tracked_count(self) -> int:
        """Number of trackers currently holding batch state (introspection)."""
        return len(self._states)
