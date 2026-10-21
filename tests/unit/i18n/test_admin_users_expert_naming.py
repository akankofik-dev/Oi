"""Admin Users UI must call agents Experts (issue #155)."""

from __future__ import annotations

import json
from pathlib import Path


def test_admin_users_agent_column_uses_expert_terminology() -> None:
    repo = Path(__file__).resolve().parents[3]
    id_ = json.loads((repo / "dashboard/src/locales/id.json").read_text(encoding="utf-8"))
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    assert id_["adminUsers"]["colAgents"] == "Expert"
    assert id_["adminUsers"]["agentsDrawerTitle"] == "Expert milik {{username}}"
    assert id_["adminUsers"]["noAgents"] == "Pengguna ini belum memiliki expert"
    assert en["adminUsers"]["colAgents"] == "Experts"
    assert en["adminUsers"]["agentsDrawerTitle"] == "{{username}}'s experts"
    assert en["adminUsers"]["noAgents"] == "This user has no experts yet"
