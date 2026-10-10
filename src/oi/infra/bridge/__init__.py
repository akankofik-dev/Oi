"""Oi↔Oi instance bridge — remote agents, HTTP tunnel, chat relay."""

from __future__ import annotations

from oi.infra.bridge.ids import (
    BRIDGE_AGENT_PREFIX,
    BridgeAgentRef,
    format_bridge_agent_id,
    parse_bridge_agent_id,
)
from oi.infra.bridge.manager import BridgeManager

__all__ = [
    "BRIDGE_AGENT_PREFIX",
    "BridgeAgentRef",
    "BridgeManager",
    "format_bridge_agent_id",
    "parse_bridge_agent_id",
]
