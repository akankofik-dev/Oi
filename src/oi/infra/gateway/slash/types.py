"""Gateway slash handler types."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oi_harness.slash import SlashCommand, SlashSink

    from oi.infra.gateway.slash.ctx import SlashCtx
    from oi.infra.gateway.slash.dispatcher import SlashDispatcher

GatewayHandler = Callable[
    ["SlashDispatcher", "SlashCommand", "SlashCtx", "SlashSink"],
    Awaitable[None],
]
