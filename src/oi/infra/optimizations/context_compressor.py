"""L1+L3: context-window management for LLM requests.

Two cooperating passes, both pure functions over the message list:

* **Smart Context Switch** (:func:`smart_context_switch`): when the estimated
  history exceeds 50% of the model's context window (typical on agent switch
  in a long thread), older messages are collapsed into a compact summary
  while the most recent ``keep_last`` messages are preserved verbatim.
* **Semantic Compression** (:func:`summarize_tool_messages`,
  :func:`dedup_system_prompts`): long tool call arguments / tool results are
  truncated to their head+tail, and duplicated system prompts are removed.

All helpers accept the heterogeneous message shapes used across the codebase
(``dict`` with ``role``/``content`` keys, or langchain message objects) and
never mutate their input.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Fallback window when the caller's model window is unknown. Conservative on
#: purpose: compression only kicks in past 50% of this value.
DEFAULT_CONTEXT_WINDOW_TOKENS = 32_768

#: Fraction of the context window that triggers smart context switching.
SWITCH_THRESHOLD = 0.5

#: Long tool payloads are truncated to head+tail of this many characters.
TOOL_PAYLOAD_MAX_CHARS = 2_000

#: Approximate context windows (tokens) by model-name substring, most specific
#: first. Values are approximate and only decide *when* smart context switching
#: kicks in (at 50% of the window); unknown models fall back to
#: :data:`DEFAULT_CONTEXT_WINDOW_TOKENS`.
_MODEL_WINDOW_PATTERNS: tuple[tuple[str, int], ...] = (
    ("gpt-4.1", 1_000_000),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-4", 32_000),
    ("gpt-3.5", 16_000),
    ("o1", 200_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-3-7-sonnet", 200_000),
    ("claude-3-5-sonnet", 200_000),
    ("claude-3-opus", 200_000),
    ("claude-3-sonnet", 200_000),
    ("claude-3-haiku", 200_000),
    ("claude", 200_000),
    ("gemini-2.5", 1_000_000),
    ("gemini-2.0", 1_000_000),
    ("gemini-1.5", 1_000_000),
    ("gemini", 1_000_000),
    ("llama-3.3", 128_000),
    ("llama-3.1", 128_000),
    ("llama-3", 8_192),
    ("mistral-large", 128_000),
    ("mistral-medium", 128_000),
    ("mistral-small", 32_000),
    ("mixtral", 32_000),
    ("qwen2.5", 128_000),
    ("qwen", 32_000),
    ("deepseek-reasoner", 128_000),
    ("deepseek-chat", 64_000),
    ("deepseek", 64_000),
    ("grok-2", 128_000),
    ("grok", 128_000),
    ("command-r", 128_000),
    ("phi-4", 128_000),
    ("phi-3", 128_000),
)


def context_window_for_model(model: str | None) -> int:
    """Best-effort context window (tokens) for a model name.

    Matching is case-insensitive substring on well-known model families;
    unknown or missing names return :data:`DEFAULT_CONTEXT_WINDOW_TOKENS`
    (conservative — compression simply kicks in earlier).
    """
    if not model:
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    name = str(model).lower()
    for pattern, window in _MODEL_WINDOW_PATTERNS:
        if pattern in name:
            return window
    return DEFAULT_CONTEXT_WINDOW_TOKENS


def estimate_tokens(text: str) -> int:
    """Rough token estimate (``~4 chars per token`` for English/Chinese mix)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _message_text(message: Any) -> str:
    """Best-effort plain-text extraction from a dict or langchain message."""
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif hasattr(block, "text"):
                parts.append(str(block.text))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        role = message.get("role", "")
        return str(role).lower() if isinstance(role, str) else ""
    # langchain: type attribute like "human"/"ai"/"system"/"tool".
    msg_type = getattr(message, "type", "")
    mapping = {"human": "user", "ai": "assistant"}
    return mapping.get(str(msg_type).lower(), str(msg_type).lower())


def _replace_content(message: Any, new_content: str) -> Any:
    """Return a copy of ``message`` with its content replaced."""
    if isinstance(message, dict):
        out = dict(message)
        out["content"] = new_content
        return out
    try:
        # langchain messages are pydantic models — model_copy is cheapest.
        return message.model_copy(update={"content": new_content})
    except Exception:
        logger.debug("context_compressor: cannot copy message, keeping original")
        return message


def _make_summary_message(text: str) -> dict[str, Any]:
    return {"role": "system", "content": f"[history summary] {text}"}


def smart_context_switch(
    messages: list[Any],
    *,
    context_window_tokens: int | None = None,
    keep_last: int = 10,
) -> list[Any]:
    """Collapse old history when it exceeds 50% of the context window.

    The newest ``keep_last`` messages are preserved verbatim; everything older
    is replaced by a single extractive summary message. Returns the input
    unchanged when under threshold or when there is nothing worth collapsing.
    """
    if not messages:
        return messages
    window = context_window_tokens or DEFAULT_CONTEXT_WINDOW_TOKENS
    if window <= 0:
        return messages

    total = sum(estimate_tokens(_message_text(m)) for m in messages)
    if total <= window * SWITCH_THRESHOLD:
        return messages
    if len(messages) <= keep_last:
        return messages

    head = messages[:-keep_last]
    tail = messages[-keep_last:]

    # Extractive summary: keep first user intent + per-role line counts.
    first_user = next(
        (m for m in head if _message_role(m) == "user"),
        None,
    )
    summary_lines: list[str] = []
    if first_user is not None:
        snippet = _message_text(first_user)[:300].replace("\n", " ")
        summary_lines.append(f"Conversation started with: {snippet}")
    roles: dict[str, int] = {}
    for m in head:
        role = _message_role(m) or "unknown"
        roles[role] = roles.get(role, 0) + 1
    role_bits = ", ".join(f"{count}x {role}" for role, count in sorted(roles.items()))
    summary_lines.append(
        f"Condensed {len(head)} earlier messages ({role_bits}, "
        f"~{total - sum(estimate_tokens(_message_text(m)) for m in tail)} tokens) "
        "to fit the context window; recent messages below are intact."
    )
    return [_make_summary_message(" ".join(summary_lines)), *tail]


def summarize_tool_messages(
    messages: list[Any],
    *,
    max_chars: int = TOOL_PAYLOAD_MAX_CHARS,
) -> list[Any]:
    """Truncate oversized tool call/result payloads (head+tail, lossless ends)."""
    if not messages:
        return messages
    out: list[Any] = []
    changed = False
    for message in messages:
        role = _message_role(message)
        text = _message_text(message)
        is_toolish = role in ("tool", "function") or (
            isinstance(message, dict) and message.get("tool_call_id") is not None
        )
        if is_toolish and len(text) > max_chars:
            head_len = max_chars * 3 // 4
            tail_len = max_chars - head_len
            truncated = (
                f"{text[:head_len]}\n…[truncated {len(text) - max_chars} chars]…\n"
                f"{text[-tail_len:]}"
            )
            out.append(_replace_content(message, truncated))
            changed = True
        else:
            out.append(message)
    return out if changed else messages


def dedup_system_prompts(messages: list[Any]) -> list[Any]:
    """Drop system messages whose text duplicates an earlier system message."""
    if not messages:
        return messages
    seen: set[str] = set()
    out: list[Any] = []
    changed = False
    for message in messages:
        if _message_role(message) == "system":
            text = _message_text(message)
            if text in seen:
                changed = True
                continue
            seen.add(text)
        out.append(message)
    return out if changed else messages


def compress_request_messages(
    messages: list[Any],
    *,
    context_window_tokens: int | None = None,
    smart_switch: bool = True,
    semantic: bool = True,
) -> list[Any]:
    """Run the enabled compression passes over an LLM request's messages."""
    result = messages
    if smart_switch:
        result = smart_context_switch(
            result, context_window_tokens=context_window_tokens
        )
    if semantic:
        result = dedup_system_prompts(result)
        result = summarize_tool_messages(result)
    return result
