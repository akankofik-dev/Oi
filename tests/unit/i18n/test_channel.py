"""tests/unit/i18n/test_channel.py"""

from __future__ import annotations

from oi.i18n import channel_tool_hint_end, channel_tool_hint_start




def test_channel_tool_hint_end_en():
    assert channel_tool_hint_end("Read file", "en") == "✅ Read file done"
