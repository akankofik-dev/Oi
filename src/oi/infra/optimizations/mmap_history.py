"""L3: memory-mapped history reader.

Reading recent thread history from SQLite on every turn costs a disk round
trip; :class:`MmapHistoryReader` keeps a per-thread JSON snapshot in a
memory-mapped file so hot reads are served from RAM. On cache miss (no file,
corrupt file, or explicit invalidation after a write) callers fall back to
the normal SQLite path — the reader never raises for missing data, it just
returns ``None``.

Cache layout: ``<cache_dir>/<safe_thread_id>.json`` written atomically
(write-temp + rename) and read via :mod:`mmap`. Files are advisory only;
SQLite remains the source of truth.
"""

from __future__ import annotations

import json
import logging
import mmap
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SAFE_THREAD_RE = re.compile(r"[^A-Za-z0-9_.-]+")

#: Environment override for the mmap cache location.
_MMAP_CACHE_DIR_ENV = "OI_MMAP_CACHE_DIR"


def default_cache_dir() -> Path:
    """Cache directory for :class:`MmapHistoryReader`.

    Defaults to ``<tmpdir>/oi-mmap-history``; override with the
    ``OI_MMAP_CACHE_DIR`` environment variable.
    """
    override = os.environ.get(_MMAP_CACHE_DIR_ENV)
    if override and override.strip():
        return Path(override.strip())
    return Path(tempfile.gettempdir()) / "oi-mmap-history"


def _safe_thread_id(thread_id: str) -> str:
    return _SAFE_THREAD_RE.sub("_", thread_id)[:128] or "unknown"


class MmapHistoryReader:
    """RAM-speed thread-history cache with transparent SQLite fallback."""

    def __init__(self, cache_dir: str | Path) -> None:
        self._dir = Path(cache_dir)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("mmap_history: cannot create cache dir %s", self._dir)
        self._available = self._dir.is_dir()

    @property
    def available(self) -> bool:
        return self._available

    def _path_for(self, thread_id: str) -> Path:
        return self._dir / f"{_safe_thread_id(thread_id)}.json"

    def store(self, thread_id: str, messages: list[Any]) -> bool:
        """Write/refresh the cached snapshot (atomic replace)."""
        if not self._available:
            return False
        try:
            payload = json.dumps(
                {"thread_id": thread_id, "messages": messages},
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
            target = self._path_for(thread_id)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self._dir), prefix=target.name + ".", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(payload)
                os.replace(tmp_name, target)
            finally:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            return True
        except (OSError, TypeError, ValueError):
            logger.exception("mmap_history: store failed for thread %s", thread_id)
            return False

    def read(self, thread_id: str) -> list[Any] | None:
        """Return cached messages, or ``None`` on miss (caller falls back)."""
        if not self._available:
            return None
        path = self._path_for(thread_id)
        try:
            with path.open("rb") as fh:
                with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    data = json.loads(mm.read().decode("utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeDecodeError):
            logger.warning("mmap_history: corrupt cache for thread %s", thread_id)
            return None
        messages = data.get("messages") if isinstance(data, dict) else None
        return messages if isinstance(messages, list) else None

    def invalidate(self, thread_id: str) -> None:
        """Drop the cached snapshot — call after any history write."""
        if not self._available:
            return
        try:
            self._path_for(thread_id).unlink(missing_ok=True)
        except OSError:
            logger.warning("mmap_history: invalidate failed for thread %s", thread_id)

    def clear(self) -> int:
        """Remove all cached snapshots; returns the number removed."""
        if not self._available:
            return 0
        removed = 0
        for path in self._dir.glob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed


def invalidate_thread(thread_id: str, cache_dir: str | Path | None = None) -> None:
    """Drop the cached snapshot for ``thread_id`` (best-effort, never raises).

    Call after any history write so later reads fall back to SQLite instead
    of serving a stale snapshot.
    """
    try:
        target = default_cache_dir() if cache_dir is None else Path(cache_dir)
        MmapHistoryReader(target).invalidate(thread_id)
    except Exception:
        logger.exception("mmap_history: invalidate failed for thread %s", thread_id)
