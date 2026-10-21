"""Tests for oi.infra.setup.self_update.

The updater was redesigned to install ONLY from GitHub Releases
(akankofik-dev/Oi): the "oi" package on PyPI belongs to a third party and
must never be installed or used for version checks. The previous test file
targeted the removed PyPI/mirror flow (index probing, mirror ranking,
application-only fast path, locale-parametrized verification); those tests
were replaced with coverage of the current GitHub-Releases behaviour.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from oi.infra.setup import self_update
from oi.infra.setup.self_update import (
    UpgradeResult,
    build_upgrade_command,
    fetch_pypi_info,
    get_version_in_dir,
    github_wheel_url,
    is_newer,
    is_prerelease,
    parse_changelog_for_version,
    parse_version,
    restore_console_scripts,
    run_upgrade,
    stash_console_scripts,
)


def test_pep440_order() -> None:
    assert parse_version("0.9.34a1") < parse_version("0.9.34b1")
    assert parse_version("0.9.34b1") < parse_version("0.9.34rc1")
    assert parse_version("0.9.34rc1") < parse_version("0.9.34")
    assert parse_version("0.9.34-beta.1") == parse_version("0.9.34b1")
    assert parse_version("0.7.2") > parse_version("0.7.1")
    assert parse_version("1.0.2b5") > parse_version("1.0.2b4")
    assert parse_version("1.0.2b10") > parse_version("1.0.2b9")
    assert parse_version("1.0.2") > parse_version("1.0.2b5")
    assert parse_version("1.0.2+local.10") == parse_version("1.0.2")


def test_is_prerelease() -> None:
    assert is_prerelease("0.9.34b1")
    assert is_prerelease("0.9.34-beta.1")
    assert is_prerelease("0.9.34rc1")
    assert is_prerelease("0.9.34a1")
    assert is_prerelease("0.9.34.dev1")
    assert not is_prerelease("0.9.34")
    assert not is_prerelease("0.7.1")


def test_is_newer() -> None:
    assert is_newer("0.7.2", "0.7.1")
    assert not is_newer("0.7.1", "0.7.2")
    assert not is_newer("0.7.1", "0.7.1")
    assert is_newer("0.9.34", "0.9.34b1")
    assert is_newer("0.9.34b1", "0.9.33")
    assert not is_newer("0.9.34b1", "0.9.34")


def test_parse_changelog_for_beta_version() -> None:
    description = (
        "## [Unreleased]\n\n"
        "## [1.0.2b5] - 2026-09-29\n\n"
        "### 新增\n- remote bridge\n\n"
        "## [1.0.1] - 2026-09-21\n\n"
        "- stable only\n"
    )
    notes = parse_changelog_for_version(description, "1.0.2b5")
    assert notes is not None
    assert "remote bridge" in notes
    assert "stable only" not in notes


class _JsonResp:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _JsonResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_portable_without_bundled_uv_keeps_pip_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from oi.infra.setup import self_update

    monkeypatch.setenv("OI_GREEN_PACKAGES", str(tmp_path / "packages"))
    monkeypatch.setattr(self_update.shutil, "which", lambda _: None)
    monkeypatch.setattr(self_update, "_COMMON_UV_PATHS", [])
    assert self_update.detect_installer() == "pip"


def _fake_windows_scripts(tmp_path: Path) -> Path:
    script_dir = tmp_path / "Scripts"
    script_dir.mkdir()
    (script_dir / "python.exe").write_text("python")
    (script_dir / "oi.exe").write_text("launcher")
    (script_dir / "oi.exe.oi-old").write_text("leftover")
    (script_dir / "pip.exe").write_text("pip")
    return script_dir


def test_stash_console_scripts_is_noop_off_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("oi.infra.setup.self_update._is_windows", lambda: False)
    script_dir = _fake_windows_scripts(tmp_path)
    assert stash_console_scripts(str(script_dir / "python.exe")) == []
    assert (script_dir / "oi.exe").exists()


def test_stash_console_scripts_moves_launcher_and_purges_leftovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("oi.infra.setup.self_update._is_windows", lambda: True)
    script_dir = _fake_windows_scripts(tmp_path)

    moved = stash_console_scripts(str(script_dir / "python.exe"))

    assert moved == [(script_dir / "oi.exe", script_dir / "oi.exe.oi-old")]
    assert not (script_dir / "oi.exe").exists()
    # The leftover from an earlier upgrade is gone, replaced by the new stash.
    assert (script_dir / "oi.exe.oi-old").read_text() == "launcher"
    assert (script_dir / "pip.exe").exists()


def test_restore_console_scripts_puts_launcher_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("oi.infra.setup.self_update._is_windows", lambda: True)
    script_dir = _fake_windows_scripts(tmp_path)
    moved = stash_console_scripts(str(script_dir / "python.exe"))

    restore_console_scripts(moved)

    assert (script_dir / "oi.exe").read_text() == "launcher"
    assert not (script_dir / "oi.exe.oi-old").exists()


@pytest.mark.parametrize("success", [True, False])
def test_run_upgrade_restores_launcher_only_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    success: bool,
) -> None:
    monkeypatch.setattr("oi.infra.setup.self_update._is_windows", lambda: True)
    monkeypatch.delenv("OI_FPK_SITE_PACKAGES", raising=False)
    script_dir = _fake_windows_scripts(tmp_path)
    monkeypatch.setattr(
        "oi.infra.setup.self_update.resolve_venv_python",
        lambda: str(script_dir / "python.exe"),
    )

    def fake_upgrade(**_kwargs: object) -> UpgradeResult:
        # The installer only succeeds because the locked launcher moved aside.
        assert not (script_dir / "oi.exe").exists()
        if success:
            (script_dir / "oi.exe").write_text("new launcher")
            return UpgradeResult(success=True, installed_version="1.0.1")
        return UpgradeResult(success=False, error="upgrade failed on all mirrors")

    monkeypatch.setattr("oi.infra.setup.self_update._run_managed_upgrade", fake_upgrade)

    result = run_upgrade()

    assert result.success is success
    expected = "new launcher" if success else "launcher"
    assert (script_dir / "oi.exe").read_text() == expected
    assert not (script_dir / "oi.exe.oi-old").exists()


def test_github_wheel_url_format() -> None:
    assert github_wheel_url("1.0.6") == (
        "https://github.com/akankofik-dev/Oi/releases/download/"
        "v1.0.6/oi-1.0.6-py3-none-any.whl"
    )


def test_fetch_pypi_info_reads_github_releases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"tag_name": "v1.0.6", "body": "## [1.0.6]\n- release notes\n"}
    urls: list[str] = []

    def fake_urlopen(req: object, timeout: int = 10) -> _JsonResp:
        urls.append(getattr(req, "full_url", ""))
        return _JsonResp(payload)

    monkeypatch.setattr("oi.infra.setup.self_update.urllib.request.urlopen", fake_urlopen)
    info = fetch_pypi_info()
    assert info is not None
    assert info.version == "1.0.6"
    assert info.latest_stable == "1.0.6"
    assert info.source == "github.com"
    assert info.description is not None and "release notes" in info.description
    assert urls == ["https://api.github.com/repos/akankofik-dev/Oi/releases/latest"]


def test_fetch_pypi_info_returns_none_when_github_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    def fake_urlopen(req: object, timeout: int = 10) -> _JsonResp:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("oi.infra.setup.self_update.urllib.request.urlopen", fake_urlopen)
    assert fetch_pypi_info() is None


def test_build_upgrade_command_requires_wheel_url() -> None:
    with pytest.raises(ValueError):
        build_upgrade_command("uv", "/venv/bin/python", version="1.0.6")


def test_build_upgrade_command_uv_uses_wheel_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(self_update, "find_uv_executable", lambda: "uv")
    monkeypatch.delenv("OI_GREEN_PACKAGES", raising=False)
    wheel = github_wheel_url("1.0.6")
    cmd = build_upgrade_command(
        "uv", "/venv/bin/python", allow_prerelease=True, version="1.0.6", wheel_url=wheel
    )
    assert cmd is not None
    assert cmd[0] == "uv"
    assert wheel in cmd
    assert "oi==1.0.6" not in cmd
    assert cmd[cmd.index("--prerelease") + 1] == "allow"
    cmd_stable = build_upgrade_command("uv", "/venv/bin/python", version="1.0.6", wheel_url=wheel)
    assert cmd_stable is not None
    assert "--prerelease" not in cmd_stable


def test_build_upgrade_command_pip_uses_wheel_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    monkeypatch.delenv("OI_GREEN_PACKAGES", raising=False)
    wheel = github_wheel_url("1.0.6")
    cmd = build_upgrade_command(
        "pip", "/venv/bin/python", allow_prerelease=True, version="1.0.6", wheel_url=wheel
    )
    assert cmd is not None
    assert wheel in cmd
    assert "--pre" in cmd


def test_build_upgrade_command_green_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(self_update, "find_uv_executable", lambda: "uv")
    monkeypatch.setenv("OI_GREEN_PACKAGES", str(tmp_path))
    cmd = build_upgrade_command(
        "uv", sys.executable, version="1.0.6", wheel_url=github_wheel_url("1.0.6")
    )
    assert cmd is not None
    assert cmd[cmd.index("--target") + 1] == str(tmp_path)


def test_get_version_in_dir_reads_only_the_target_package(tmp_path: Path) -> None:
    pkg = tmp_path / "oi"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('__version__ = "1.2.3"\n')
    # The interpreter has its own oi installed; the probe must report the
    # target's package (verified via oi.__file__), not the other install.
    assert get_version_in_dir(sys.executable, str(tmp_path)) == "1.2.3"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert get_version_in_dir(sys.executable, str(empty)) is None


def test_verify_upgrade_success_when_newer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update, "get_installed_version", lambda _: "1.0.7")
    result = self_update._verify_upgrade("1.0.6", "/venv/bin/python", [])
    assert result.success is True
    assert result.installed_version == "1.0.7"


def test_verify_fpk_upgrade_rejects_same_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(self_update, "get_version_in_dir", lambda *_: "1.0.6")
    result = self_update._verify_fpk_upgrade("1.0.6", str(tmp_path), sys.executable, [])
    assert result.success is False
    monkeypatch.setattr(self_update, "get_version_in_dir", lambda *_: "1.0.7")
    result = self_update._verify_fpk_upgrade("1.0.6", str(tmp_path), sys.executable, [])
    assert result.success is True
    assert result.installed_version == "1.0.7"


def test_run_managed_upgrade_requires_version() -> None:
    result = self_update._run_managed_upgrade()
    assert result.success is False
    assert result.error is not None and "tidak diketahui" in result.error


def test_run_managed_upgrade_missing_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update, "_github_release_exists", lambda *_a, **_k: False)
    result = self_update._run_managed_upgrade(version="9.9.9")
    assert result.success is False
    assert result.error is not None and "tidak ditemukan" in result.error


def test_run_managed_upgrade_installs_from_github_wheel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(self_update, "_github_release_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(self_update, "detect_installer", lambda: "pip")
    monkeypatch.setattr(self_update, "resolve_venv_python", lambda: sys.executable)
    monkeypatch.setattr(self_update, "has_pip", lambda _: True)
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.6")
    monkeypatch.delenv("OI_GREEN_PACKAGES", raising=False)
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], label: str, **_kwargs: object) -> tuple[int, str]:
        seen.append(cmd)
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", fake_run)
    monkeypatch.setattr(
        self_update,
        "_verify_upgrade",
        lambda *_a: UpgradeResult(success=True, installed_version="1.0.7"),
    )
    result = self_update._run_managed_upgrade(version="1.0.7")
    assert result.success is True
    assert seen and github_wheel_url("1.0.7") in seen[0]


def test_run_upgrade_fpk_installs_into_site_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OI_FPK_SITE_PACKAGES", str(tmp_path))
    monkeypatch.setattr(self_update, "_github_release_exists", lambda *_a, **_k: True)
    monkeypatch.setattr(self_update, "detect_installer", lambda: "pip")
    monkeypatch.setattr(self_update, "get_local_version", lambda: "1.0.6")
    monkeypatch.setattr(self_update, "get_version_in_dir", lambda *_: "1.0.7")
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], label: str, **_kwargs: object) -> tuple[int, str]:
        seen.append(cmd)
        return 0, ""

    monkeypatch.setattr(self_update, "_run_install_cmd", fake_run)
    result = run_upgrade(version="1.0.7")
    assert result.success is True
    assert result.installed_version == "1.0.7"
    assert seen and github_wheel_url("1.0.7") in seen[0]
    assert seen[0][seen[0].index("--target") + 1] == str(tmp_path)


# The desktop launcher compares versions with its own Go implementation
# (desktop/src/download_test.go, TestCompareVersions) and decides whether to
# replace the portable runtime; the server decides below whether an upgrade is
# newer. The two ends must agree on the same strings, so this table mirrors the
# desktop one, including ignoring PEP 440 local segments on both ends.
_DESKTOP_ORDERING_PARITY = [
    ("0.9.32", "0.9.31", 1),
    ("0.9.32", "0.9.32", 0),
    ("0.9.31", "0.9.32", -1),
    ("0.9.32rc1", "0.9.31", 1),
    ("1.0", "1.0.0", 0),
    ("0.9.34-beta.1", "0.9.34b1", 0),
    ("1.0.2b4", "1.0.2b5", -1),
    ("1.0.2b5", "1.0.2b4", 1),
    ("1.0.2b10", "1.0.2b9", 1),
    ("1.0.2b5", "1.0.2b5", 0),
    ("1.0.2", "1.0.2b5", 1),
    ("1.0.2b5", "1.0.2", -1),
    ("1.0.2a2", "1.0.2b1", -1),
    ("1.0.2b5", "1.0.2rc1", -1),
    ("1.0.2rc1", "1.0.2", -1),
    ("1.0.2.dev1", "1.0.2a1", -1),
    ("1.0.2b5.dev1", "1.0.2b5", -1),
    ("1.0.2.post1", "1.0.2", 1),
    ("1!1.0.0", "2.0.0", 1),
    ("v1.0.2B05", "1.0.2b5", 0),
    ("1.0.2+local.10", "1.0.2+local.9", 0),
    ("1.0.2+local.10", "1.0.2", 0),
    ("1.0.2-custom", "1.0.1", 1),
    ("dev", "dev", 0),
]


@pytest.mark.parametrize(("left", "right", "want"), _DESKTOP_ORDERING_PARITY)
def test_version_ordering_matches_desktop_comparator(left: str, right: str, want: int) -> None:
    left_key, right_key = parse_version(left), parse_version(right)
    sign = (left_key > right_key) - (left_key < right_key)
    assert sign == want, f"{left} vs {right}: server={sign}, desktop={want}"
