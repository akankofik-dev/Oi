"""L2: zero-copy streaming — dual pipeline for stream fan-out.

The stock path sends a chunk to the WebSocket client and *then* persists it,
so DB latency is added to every chunk's delivery time. :class:`StreamPipeline`
fans each chunk out to the socket sink and the persistence sink concurrently
with :func:`asyncio.gather`, so the client never waits on the database.

"Zero-copy" here means the chunk object itself is shared between sinks (no
serialization round-trip per sink); sinks must treat chunks as read-only.

WIRING NOTE (2026-10-14): this module is intentionally NOT hooked into the
hot path. In this codebase persistence happens *inside* the producer
generator (``GlobalProcessor.iter_turn_chunks`` → ``maybe_batch_flush``)
while socket delivery happens in the consumer
(``ws_channel`` → ``hub.push_to_thread``) — there is no single site where a
chunk is sent to the socket and *then* written to DB sequentially, so
``fan_out`` has nothing to parallelize without restructuring the
generator/consumer contract (a large, risky refactor). The batch writer
(``batch_db_writes`` flag) already amortizes the per-chunk DB cost, which was
the dominant term this module targets. The module remains available
standalone via :meth:`OptimizationManager.stream_pipeline` for future use.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

#: ``async def sink(chunk) -> None``. Chunks are shared read-only.
ChunkSink = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class StreamPipeline:
    """Fan each stream chunk out to multiple sinks concurrently."""

    sinks: list[ChunkSink] = field(default_factory=list)
    #: When True, one sink's exception is logged and the others still run.
    isolate_errors: bool = True

    def add_sink(self, sink: ChunkSink) -> None:
        self.sinks.append(sink)

    async def emit(self, chunk: dict[str, Any]) -> None:
        """Deliver ``chunk`` to every sink concurrently."""
        if not self.sinks:
            return
        if len(self.sinks) == 1:
            await self._safe_emit(self.sinks[0], chunk)
            return
        await asyncio.gather(
            *(self._safe_emit(sink, chunk) for sink in self.sinks),
            return_exceptions=False,
        )

    async def _safe_emit(self, sink: ChunkSink, chunk: dict[str, Any]) -> None:
        try:
            await sink(chunk)
        except Exception:
            logger.exception("StreamPipeline: sink failed")
            if not self.isolate_errors:
                raise

    async def run(
        self, chunks: Any, *, on_chunk: ChunkSink | None = None
    ) -> None:
        """Drain an async iterator of chunks through the pipeline.

        ``on_chunk`` is an optional extra per-chunk hook (e.g. usage tracking)
        that runs inline, before the concurrent fan-out.
        """
        async for chunk in chunks:
            if on_chunk is not None:
                await on_chunk(chunk)
            await self.emit(chunk)


async def fan_out(
    chunk: dict[str, Any],
    *sinks: ChunkSink,
    isolate_errors: bool = True,
) -> None:
    """One-shot concurrent fan-out of a single chunk (no pipeline object)."""
    if not sinks:
        return
    if len(sinks) == 1:
        await sinks[0](chunk)
        return

    async def _guarded(sink: ChunkSink) -> None:
        try:
            await sink(chunk)
        except Exception:
            logger.exception("stream_pipeline.fan_out: sink failed")
            if not isolate_errors:
                raise

    await asyncio.gather(*(_guarded(sink) for sink in sinks))
