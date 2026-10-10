"""Agent connection settings exposed to authenticated clients."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from oi.api.deps import current_user, get_server
from oi.config import AgentConnectionConfig

router = APIRouter()


class AgentConnectionSettingsResponse(BaseModel):
    timeout_seconds: int = Field(
        description="Per-request timeout for agent harness calls (1-3600)."
    )
    reconnect_attempts: int = Field(
        description="Automatic reconnect attempts after a dropped agent session (0-20)."
    )
    reconnect_interval_seconds: int = Field(
        description="Backoff between reconnect attempts in seconds (1-300)."
    )
    keepalive_seconds: int = Field(
        description="WebSocket/keepalive ping interval in seconds (5-600)."
    )
    max_concurrent_sessions: int = Field(
        description="Max concurrent sessions per agent (1-64)."
    )
    idle_disconnect_minutes: int = Field(
        description="Minutes of inactivity before an idle session is disconnected (0-1440; 0 disables)."
    )


def _to_response(cfg: AgentConnectionConfig) -> AgentConnectionSettingsResponse:
    return AgentConnectionSettingsResponse(
        timeout_seconds=cfg.timeout_seconds,
        reconnect_attempts=cfg.reconnect_attempts,
        reconnect_interval_seconds=cfg.reconnect_interval_seconds,
        keepalive_seconds=cfg.keepalive_seconds,
        max_concurrent_sessions=cfg.max_concurrent_sessions,
        idle_disconnect_minutes=cfg.idle_disconnect_minutes,
    )


@router.get(
    "/settings/agent-connections",
    summary="Agent connection settings",
    response_model=AgentConnectionSettingsResponse,
)
async def get_agent_connection_settings(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> AgentConnectionSettingsResponse:
    """Return the server-wide agent connection defaults from config.json
    (``agent_connections`` section, overridable via ``OI_AGENT_CONNECTION``)."""
    _ = user
    return _to_response(server.services.config.agent_connections)
