"""tests/unit/test_paths.py"""

from __future__ import annotations

from pathlib import Path

from oi.infra.utils.paths import PathLayout


def test_root_paths(tmp_path: Path):
    p = PathLayout(tmp_path / ".oi")
    assert p.root == tmp_path / ".oi"
    assert p.db == tmp_path / ".oi" / "oi.db"
    assert p.logs_dir == tmp_path / ".oi" / "logs"
    assert p.log == tmp_path / ".oi" / "logs" / "oi.log"
    assert p.config == tmp_path / ".oi" / "config.json"


def test_log_dir_creation(tmp_path: Path):
    p = PathLayout(tmp_path / ".oi")
    assert not (tmp_path / ".oi" / "logs").exists()
    assert p.ensure_log() == tmp_path / ".oi" / "logs" / "oi.log"
    assert (tmp_path / ".oi" / "logs").is_dir()
    assert p.log == tmp_path / ".oi" / "logs" / "oi.log"


def test_user_dir_uses_username(tmp_path: Path):
    p = PathLayout(tmp_path / ".oi")
    assert p.user_dir("alice") == tmp_path / ".oi" / "users" / "alice"


def test_agent_workspace(tmp_path: Path):
    p = PathLayout(tmp_path / ".oi")
    ws = p.agent_workspace("agent01")
    assert ws == tmp_path / ".oi" / "agents" / "agent01"


def test_ensure_root_creates_dir(tmp_path: Path):
    p = PathLayout(tmp_path / ".oi")
    p.ensure_root()
    assert (tmp_path / ".oi").is_dir()


def test_ensure_agent_workspace(tmp_path: Path):
    p = PathLayout(tmp_path / ".oi")
    # New global path
    out = p.ensure_agent_workspace("a1")
    assert out.is_dir()
    assert out == tmp_path / ".oi" / "agents" / "a1"


def test_backups_dir(tmp_path: Path) -> None:
    p = PathLayout(tmp_path / ".oi")
    assert p.backups_dir == tmp_path / ".oi" / "backups"
    assert p.ensure_backups_dir().is_dir()


def test_knowledge_dir(tmp_path: Path) -> None:
    p = PathLayout(tmp_path / ".oi")
    assert p.knowledge_dir == tmp_path / ".oi" / "knowledge"


def test_path_layout_from_env_defaults_to_dot_oi(monkeypatch) -> None:
    monkeypatch.delenv("OI_HOME", raising=False)
    assert PathLayout.from_env().root == Path.home() / ".oi"


def test_path_layout_from_env_honors_oi_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OI_HOME", str(tmp_path))
    assert PathLayout.from_env().root == tmp_path
