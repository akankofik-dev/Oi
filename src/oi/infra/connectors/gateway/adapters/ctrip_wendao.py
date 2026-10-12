"""Ctrip Wendao (携程问道) gateway — paste Token from authorize page."""

from __future__ import annotations

import re
from typing import Any

import httpx

QUERY_URL = "https://wendao-skill-prod.ctrip.com/skill/query"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$", re.I)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "ask_wendao",
        "description": (
            "Ask Ctrip Wendao for travel advice: hotels, flights, trains, "
            "attractions, and itinerary planning"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language travel question",
                },
            },
            "required": ["query"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "ask_wendao":
        return ask_wendao(creds, args)
    raise ValueError(f"unknown tool: {name}")


def ask_wendao(creds: dict[str, Any], args: dict[str, Any]) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    token = _token(creds)
    body = {"token": token, "query": query, "source": "oi"}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "oi-connector/0.1",
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(QUERY_URL, headers=headers, json=body)
        r.raise_for_status()
        text = r.text.strip()
    if not text:
        raise ValueError("Ctrip Wendao mengembalikan kosong")
    # Upstream occasionally returns plain JSON errors.
    if text.startswith("{") and ("error" in text.lower() or "invalid" in text.lower()):
        raise ValueError(f"Galat antarmuka Ctrip Wendao: {text[:200]}")
    return text


def probe_credentials(creds: dict[str, Any]) -> None:
    """Format-only check — upstream /skill/query accepts many invalid tokens."""
    _token(creds)


def _token(creds: dict[str, Any]) -> str:
    token = str(creds.get("api_key") or creds.get("token") or "").strip()
    if not token:
        raise ValueError("Isi Token Ctrip Wendao")
    if not _TOKEN_RE.match(token):
        raise ValueError(
            "Format Token Ctrip Wendao salah, buka http://t.ctrip.cn/28J6RhL untuk mengajukan lalu salin Token lengkap"
        )
    return token
