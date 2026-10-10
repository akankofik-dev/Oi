"""Self-upgrade helpers shared by CLI and HTTP update API."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from oi.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "oi"
# NOTE: _PACKAGE_NAME hanya untuk lookup metadata lokal (importlib.metadata)
# dan nama file wheel. JANGAN PERNAH install/upgrade dari PyPI: paket "oi"
# di PyPI milik pihak lain. Upgrade HANYA dari GitHub Releases akankofik-dev/Oi.
_GITHUB_REPO = "akankofik-dev/Oi"
_GITHUB_RELEASES_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
_GITHUB_UA = {"User-Agent": "oi-updater/1.0", "Accept": "application/vnd.github+json"}


def github_wheel_url(version: str) -> str:
    """Return direct wheel download URL for a GitHub release version."""
    return (
        f"https://github.com/{_GITHUB_REPO}/releases/download/"
        f"v{version}/oi-{version}-py3-none-any.whl"
    )


def _github_release_exists(version: str, timeout: int = 10) -> bool:
    """Check if a GitHub release exists for the given version (HEAD request)."""
    try:
        req = urllib.request.Request(
            github_wheel_url(version), headers=_GITHUB_UA, method="HEAD"
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False
_GREEN_PACKAGES_ENV = "OI_GREEN_PACKAGES"
_STASH_SUFFIX = ".oi-old"
_PROBE_TIMEOUT_S = 8
_INSTALL_TIMEOUT_S = 90
_FPK_INSTALL_TIMEOUT_S = 900



_COMMON_UV_PATHS = [
    os.path.expanduser("~/.local/bin/uv"),
    os.path.expanduser("~/.cargo/bin/uv"),
    "/usr/local/bin/uv",
    "/opt/homebrew/bin/uv",
]


@dataclass
class UpgradeResult:
    success: bool
    message: str | None = None
    error: str | None = None
    installed_version: str | None = None
    mirror_errors: list[str] = field(default_factory=list)


def green_packages_dir() -> Path | None:
    """Return ``--target`` dir for green portable installs, if configured."""
    raw = (os.environ.get(_GREEN_PACKAGES_ENV) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_venv_python() -> str:
    """Return the Python executable for the managed ~/.oi/venv install."""
    # Green portable: always the interpreter that launched launch.py, never ~/.oi/venv.
    if green_packages_dir() is not None:
        return sys.executable

    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    if sys.prefix != base_prefix:
        return sys.executable

    virtual_env = os.environ.get("VIRTUAL_ENV", "").strip()
    if virtual_env:
        for rel in ("bin/python", "Scripts/python.exe"):
            candidate = Path(virtual_env) / rel
            if candidate.is_file():
                return str(candidate)

    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = PathLayout.from_env().root / "venv" / rel
        if candidate.is_file():
            return str(candidate)

    return sys.executable


def detect_installer() -> str:
    if shutil.which("uv"):
        return "uv"
    for candidate in _COMMON_UV_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return "uv"
    return "pip"


def find_uv_executable() -> str:
    if shutil.which("uv"):
        return "uv"
    for candidate in _COMMON_UV_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "uv"


def get_local_version() -> str:
    try:
        from importlib.metadata import version

        # Package lokal namanya "oi" (bukan "oi-agent")
        return version("oi")
    except Exception:
        return "0.0.0"


@dataclass
class PyPIInfo:
    version: str
    """Newest version on the index, including pre-releases (``latest_any``)."""

    description: str | None = None
    """Package long description."""

    source: str | None = None
    """Label of the source that served this payload (e.g. ``github.com``)."""

    latest_stable: str | None = None
    """Newest non-pre-release version, or None if every release is a pre-release."""


def fetch_github_info(timeout: int = 10) -> PyPIInfo | None:
    """Fetch latest release version from GitHub Releases.

    Returns PyPIInfo-compatible object, or None on failure.
    """
    try:
        req = urllib.request.Request(_GITHUB_RELEASES_URL, headers=_GITHUB_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        tag = str(data.get("tag_name", "")).strip()
        # tag bisa "v1.0.3" atau "1.0.3" -> ambil angka versinya
        m = re.search(r"(\d+\.\d+\.\d+)", tag)
        version = m.group(1) if m else tag.lstrip("v")
        if not version:
            return None
        body = data.get("body")
        return PyPIInfo(
            version=version,
            latest_stable=version,
            description=body if isinstance(body, str) else None,
            source="github.com",
        )
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("failed to fetch GitHub release info: %s", exc)
        return None


def fetch_pypi_info(timeout: int = 10) -> PyPIInfo | None:
    """Fetch latest release info from GitHub Releases (akankofik-dev/Oi).

    Returns PyPIInfo-compatible object, or None on failure.

    PENTING: fungsi ini HANYA membaca GitHub Releases. Tidak ada fallback ke
    PyPI — paket "oi" di PyPI milik pihak lain dan tidak boleh dipakai untuk
    cek versi maupun upgrade. Nama fungsi dipertahankan demi kompatibilitas
    pemanggil (router/CLI).
    """
    gh = fetch_github_info(timeout)
    if gh is None:
        logger.warning("could not reach GitHub Releases for update check")
    return gh


def parse_changelog_for_version(description: str | None, version: str) -> str | None:
    """Extract the changelog entry for *version* from a Keep a Changelog string.

    Searches for ``## [<version>]`` and returns everything up to the next
    ``## [`` heading (or end of string). Returns None if not found.
    """
    if not description:
        return None
    pattern = re.compile(
        r"(##\s+\[" + re.escape(version) + r"\][^\n]*\n.*?)(?=\n##\s+\[|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(description)
    if not match:
        return None
    return match.group(1).strip()


# PEP 440 letter ranks: a/alpha < b/beta < rc/c/pre/preview. Final has no pre.
_PRE_RANK = {
    "a": 0,
    "alpha": 0,
    "b": 1,
    "beta": 1,
    "c": 2,
    "rc": 2,
    "pre": 2,
    "preview": 2,
}

_PEP440_RE = re.compile(
    r"""
    ^v?
    (?:(?P<epoch>\d+)!)?
    (?P<release>\d+(?:\.\d+)*)
    (?:
        [-_\.]?
        (?P<pre_l>alpha|a|beta|b|preview|pre|rc|c)
        [-_\.]?
        (?P<pre_n>\d+)?
    )?
    (?:
        (?:[-_\.]?(?P<post_l>post|rev|r)[-_\.]?(?P<post_n>\d+))
        |
        (?:-(?P<post_n1>\d+))
    )?
    (?:
        [-_\.]?
        (?P<dev_l>dev)
        [-_\.]?
        (?P<dev_n>\d+)?
    )?
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _numeric_release_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for segment in value.split("."):
        numeric = ""
        for ch in segment:
            if ch.isdigit():
                numeric += ch
            else:
                break
        parts.append(int(numeric) if numeric else 0)
    return tuple(parts) or (0,)


VersionKey = tuple[int, tuple[int, ...], tuple[int, ...], int, tuple[int, ...]]


def parse_version(value: str) -> VersionKey:
    """Return a comparable PEP 440 sort key for *value*."""
    match = _PEP440_RE.match(value.strip())
    if match is None:
        # Unknown shape: keep previous numeric-only behaviour.
        numeric = _numeric_release_key(value)
        return (0, numeric + (0,) * max(0, 8 - len(numeric)), (1,), -1, (1,))
    epoch = int(match.group("epoch") or 0)
    release_parts = tuple(int(part) for part in match.group("release").split("."))
    # Pad so 1.0 and 1.0.0 compare equal under tuple ordering.
    release = release_parts + (0,) * max(0, 8 - len(release_parts))
    pre_l = match.group("pre_l")
    if pre_l:
        pre_key: tuple[int, ...] = (
            0,
            _PRE_RANK[pre_l.lower()],
            int(match.group("pre_n") or 0),
        )
    elif match.group("dev_l"):
        # Bare .devN sorts before a/b/rc of the same release.
        pre_key = (-1,)
    else:
        pre_key = (1,)
    post_raw = match.group("post_n") or match.group("post_n1")
    post_key = int(post_raw) if post_raw is not None else -1
    if match.group("dev_l"):
        dev_key: tuple[int, ...] = (0, int(match.group("dev_n") or 0))
    else:
        dev_key = (1,)
    return (epoch, release, pre_key, post_key, dev_key)


def is_prerelease(value: str) -> bool:
    """True when *value* is a PEP 440 pre-release (a/b/rc/dev)."""
    match = _PEP440_RE.match(value.strip())
    if match is None:
        return False
    return match.group("pre_l") is not None or match.group("dev_l") is not None


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def get_editable_path() -> str | None:
    try:
        import importlib.metadata as meta

        dist = meta.distribution(_PACKAGE_NAME)
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            info = json.loads(direct_url)
            if info.get("dir_info", {}).get("editable", False):
                return info.get("url", "").replace("file://", "") or None
    except Exception:
        pass
    return None


def has_pip(python_exe: str) -> bool:
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def find_pip_in_venv(python_exe: str) -> str | None:
    bin_dir = os.path.dirname(os.path.abspath(python_exe))
    for name in ("pip", "pip3"):
        candidate = os.path.join(bin_dir, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def append_prerelease_flags(
    cmd: list[str],
    installer: str,
    *,
    allow_prerelease: bool,
) -> None:
    if not allow_prerelease:
        return
    if installer == "uv":
        cmd.extend(["--prerelease", "allow"])
    else:
        cmd.append("--pre")


def build_upgrade_command(
    installer: str,
    venv_python: str,
    *,
    allow_prerelease: bool = False,
    version: str | None = None,
    wheel_url: str | None = None,
) -> list[str] | None:
    """Build installer command for upgrading Oi.

    Upgrade HANYA dari wheel_url GitHub Releases. Parameter wheel_url WAJIB —
    tidak ada fallback ke ``pip install oi==X`` dari PyPI karena paket "oi"
    di PyPI milik pihak lain.
    """
    if not wheel_url:
        raise ValueError(
            "wheel_url wajib diisi (URL wheel GitHub Releases); "
            "upgrade dari PyPI tidak diizinkan"
        )
    target = green_packages_dir()
    target_args: list[str] = []
    if target is not None:
        target_args = ["--target", str(target)]
    requirement = wheel_url

    if installer == "uv":
        uv_exe = find_uv_executable()
        cmd = [
            uv_exe,
            "pip",
            "install",
            "--python",
            venv_python,
            *target_args,
            "--upgrade-package",
            _PACKAGE_NAME,
        ]
        append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
        cmd.append(requirement)
        return cmd

    upgrade_flags = ["--upgrade", "--upgrade-strategy", "only-if-needed"]
    if has_pip(venv_python):
        cmd = [venv_python, "-m", "pip", "install", *upgrade_flags, *target_args]
    else:
        venv_pip = find_pip_in_venv(venv_python)
        if venv_pip:
            cmd = [venv_pip, "install", *upgrade_flags, *target_args]
        else:
            standalone = shutil.which("pip3") or shutil.which("pip")
            if not standalone:
                return None
            cmd = [standalone, "install", *upgrade_flags, *target_args]
    append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
    cmd.append(requirement)
    return cmd


def _is_windows() -> bool:
    return os.name == "nt"


def stash_console_scripts(python_exe: str) -> list[tuple[Path, Path]]:
    """Rename the ``oi`` launchers next to *python_exe* out of the way.

    Windows refuses to delete or overwrite the executable backing a running
    process (``os error 32``), which makes pip and uv fail while rewriting
    ``Scripts/oi.exe`` during ``oi update``. Renaming the file is still
    permitted, so the installer gets a free path and the running process keeps
    its handle. Returns the ``(original, stash)`` pairs that were moved.
    """
    if not _is_windows():
        return []
    script_dir = Path(python_exe).parent
    _purge_stale_stashes(script_dir)
    moved: list[tuple[Path, Path]] = []
    for script in sorted(script_dir.glob(f"{_PACKAGE_NAME}*.exe")):
        stash = script.with_name(script.name + _STASH_SUFFIX)
        try:
            script.replace(stash)
        except OSError as exc:
            logger.warning("could not move %s aside: %s", script, exc)
            continue
        moved.append((script, stash))
    return moved


def restore_console_scripts(moved: list[tuple[Path, Path]]) -> None:
    """Put stashed launchers back after a failed upgrade."""
    for original, stash in moved:
        if original.exists() or not stash.exists():
            continue
        try:
            stash.replace(original)
        except OSError as exc:
            logger.warning("could not restore %s: %s", original, exc)


def discard_console_script_stashes(moved: list[tuple[Path, Path]]) -> None:
    """Drop stashes after a successful upgrade, ignoring still-locked files."""
    for _original, stash in moved:
        _unlink_quietly(stash)


def _purge_stale_stashes(script_dir: Path) -> None:
    for stale in script_dir.glob(f"*{_STASH_SUFFIX}"):
        _unlink_quietly(stale)


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        # Still held by the running process — the next upgrade purges it.
        logger.debug("could not remove %s: %s", path, exc)


def get_installed_version(python_exe: str) -> str | None:
    try:
        result = subprocess.run(
            [
                python_exe,
                "-c",
                f"from importlib.metadata import version; print(version({_PACKAGE_NAME!r}))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def get_version_in_dir(python_exe: str, target: str) -> str | None:
    """Return the oi version installed in *target* (a ``pip --target`` dir)."""
    try:
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from importlib.metadata import version; print(version('oi'))"
        )
        result = subprocess.run(
            [python_exe, "-c", code, target],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _run_install_cmd(
    cmd: list[str],
    label: str,
    *,
    verbose: bool,
    timeout: float,
) -> tuple[int | None, str]:
    logger.debug("running %s: %s", label, " ".join(cmd))
    try:
        # NOCA:DangerousSubprocessUseAudit(argv list with shell=False; installer paths and mirrors are trusted)
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=not verbose,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"timed out after {int(timeout)}s"
    if result.returncode == 0:
        return 0, ""
    snippet = (result.stderr or result.stdout or "")[:300]
    return result.returncode, snippet


def _verify_fpk_upgrade(
    local_ver: str,
    site_packages: str,
    python_exe: str,
    mirror_errors: list[str],
) -> UpgradeResult:
    actual_ver: str | None = None
    for attempt in range(3):
        actual_ver = get_version_in_dir(python_exe, site_packages)
        if actual_ver and actual_ver != local_ver:
            break
        if attempt < 2:
            time.sleep(0.5)

    if actual_ver and is_newer(actual_ver, local_ver):
        return UpgradeResult(
            success=True,
            message=f"Sudah upgrade ke {actual_ver}, silakan restart layanan agar berlaku.",
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    if actual_ver == local_ver:
        return UpgradeResult(
            success=False,
            error=(
                f"Install selesai tapi versi masih {actual_ver}; "
                "pastikan versi baru sudah dirilis di GitHub Releases."
            ),
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    return UpgradeResult(
        success=True,
        message="upgrade completed",
        installed_version=actual_ver,
        mirror_errors=mirror_errors,
    )


def _run_fpk_upgrade(
    site_packages: str,
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
) -> UpgradeResult:
    """Upgrade pada deployment FnOS FPK: install versi baru ke direktori
    site-packages yang sebenarnya dimuat launcher.

    Upgrade HANYA dari wheel GitHub Releases (akankofik-dev/Oi) — tidak
    pernah dari PyPI (paket "oi" di PyPI milik pihak lain).
    """
    if not os.path.isdir(site_packages):
        return UpgradeResult(
            success=False,
            error=f"Direktori site-packages FPK tidak ada: {site_packages}",
        )
    if not version:
        return UpgradeResult(
            success=False,
            error="Versi target tidak diketahui; jalankan cek update dulu.",
        )
    wheel_url = github_wheel_url(version)
    if not _github_release_exists(version):
        return UpgradeResult(
            success=False,
            error=f"Release GitHub v{version} tidak ditemukan.",
        )
    local_ver = get_local_version()
    python_exe = sys.executable
    installer = detect_installer()  # uv prioritas: pip bisa hang saat resolve dep oi-harness[all]
    mirror_errors: list[str] = []

    if installer == "uv":
        cmd = [
            find_uv_executable(),
            "pip",
            "install",
            "--python",
            python_exe,
            "--target",
            site_packages,
            "--upgrade-package",
            _PACKAGE_NAME,
            wheel_url,
        ]
    else:
        cmd = [
            python_exe,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--upgrade-strategy",
            "only-if-needed",
            "--target",
            site_packages,
            wheel_url,
        ]
    append_prerelease_flags(cmd, installer, allow_prerelease=allow_prerelease)
    rc, err_snippet = _run_install_cmd(
        cmd,
        "github.com",
        verbose=verbose,
        timeout=_FPK_INSTALL_TIMEOUT_S,
    )
    if rc != 0:
        return UpgradeResult(
            success=False,
            error=f"upgrade dari GitHub Releases gagal: {err_snippet or 'unknown error'}",
            mirror_errors=mirror_errors,
        )
    return _verify_fpk_upgrade(local_ver, site_packages, python_exe, mirror_errors)


def run_upgrade(
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
) -> UpgradeResult:
    # [FPK] FnOS FPK 部署：launcher 通过 PYTHONPATH 从应用中心托管的打包
    # site-packages 加载 oi，在线安装到系统 Python 永远不会被加载（重启
    # 无效）。launcher 导出 OI_FPK_SITE_PACKAGES 指向该打包目录，升级即
    # 安装到此目录并提示重启服务生效——升级真正可用，而非禁止升级。
    _fpk_site = os.environ.get("OI_FPK_SITE_PACKAGES", "").strip()
    if _fpk_site:
        return _run_fpk_upgrade(
            _fpk_site,
            verbose=verbose,
            allow_prerelease=allow_prerelease,
            version=version,
        )

    # Windows keeps the running oi.exe locked (os error 32), so pip / uv
    # cannot rewrite the console script. Renaming it is still allowed, so move
    # the launchers aside first and restore them if the upgrade fails.
    stashed = stash_console_scripts(resolve_venv_python())
    try:
        result = _run_managed_upgrade(
            verbose=verbose,
            allow_prerelease=allow_prerelease,
            version=version,
        )
    except BaseException:
        restore_console_scripts(stashed)
        raise
    if result.success:
        discard_console_script_stashes(stashed)
    else:
        restore_console_scripts(stashed)
    return result


def _run_managed_upgrade(
    *,
    verbose: bool = False,
    allow_prerelease: bool = False,
    version: str | None = None,
) -> UpgradeResult:
    """Upgrade Oi HANYA dari wheel GitHub Releases (akankofik-dev/Oi).

    Tidak ada fallback ke PyPI/mirror: paket "oi" di PyPI milik pihak lain.
    """
    installer = detect_installer()
    venv_python = resolve_venv_python()
    local_ver = get_local_version()
    mirror_errors: list[str] = []

    if not version:
        return UpgradeResult(
            success=False,
            error="Versi target tidak diketahui; jalankan cek update dulu.",
            mirror_errors=mirror_errors,
        )
    gh_url = github_wheel_url(version)
    if not _github_release_exists(version):
        return UpgradeResult(
            success=False,
            error=f"Release GitHub v{version} tidak ditemukan.",
            mirror_errors=mirror_errors,
        )
    cmd = build_upgrade_command(
        installer,
        venv_python,
        allow_prerelease=allow_prerelease,
        version=version,
        wheel_url=gh_url,
    )
    if cmd is None:
        return UpgradeResult(
            success=False,
            error="pip is not available for the Oi virtual environment.",
            mirror_errors=mirror_errors,
        )
    rc, err_snippet = _run_install_cmd(
        cmd,
        "github.com",
        verbose=verbose,
        timeout=_INSTALL_TIMEOUT_S,
    )
    if rc == 0:
        return _verify_upgrade(local_ver, venv_python, mirror_errors)
    return UpgradeResult(
        success=False,
        error=f"upgrade dari GitHub Releases gagal: {err_snippet or 'unknown error'}",
        mirror_errors=mirror_errors,
    )


def _verify_upgrade(
    local_ver: str,
    venv_python: str,
    mirror_errors: list[str],
) -> UpgradeResult:
    actual_ver: str | None = None
    for attempt in range(3):
        actual_ver = get_installed_version(venv_python)
        if actual_ver and actual_ver != local_ver:
            break
        if attempt < 2:
            time.sleep(0.5)

    if actual_ver and is_newer(actual_ver, local_ver):
        return UpgradeResult(
            success=True,
            message=f"upgraded to {actual_ver}",
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    if actual_ver == local_ver:
        return UpgradeResult(
            success=True,
            message=f"installer finished but version is still {actual_ver}",
            installed_version=actual_ver,
            mirror_errors=mirror_errors,
        )
    return UpgradeResult(
        success=True,
        message="upgrade completed",
        installed_version=actual_ver,
        mirror_errors=mirror_errors,
    )
