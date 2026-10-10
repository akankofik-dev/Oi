"""Slash command parsing and dispatch."""

from oi_harness.slash import BufferSink, SlashCommand, SlashSink

from oi.infra.gateway.slash.ctx import SlashCtx, build_slash_ctx
from oi.infra.gateway.slash.dispatcher import SlashDispatcher, build_default_dispatcher
from oi.infra.gateway.slash.parser import parse_slash

__all__ = [
    "BufferSink",
    "SlashCommand",
    "SlashCtx",
    "SlashDispatcher",
    "SlashSink",
    "build_default_dispatcher",
    "build_slash_ctx",
    "parse_slash",
]
