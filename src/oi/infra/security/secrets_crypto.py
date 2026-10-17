"""Secrets at rest — Fernet encryption for API keys and backup secrets.

Security model
--------------
Provider API keys (LLM + voice) are stored **ciphertext** in the database.
Callers always see plaintext (decrypt-on-read / encrypt-on-write inside the
repos), so the rest of the code is unchanged. Backups encrypt ``config.json``
and the ``env`` file inside the archive, and the database snapshot is taken
only *after* a migration pass, so a backup never ships plaintext keys.

Key resolution (in order)
--------------------------
1. ``OI_SECRET_KEY`` env var — a urlsafe-base64 Fernet key. Invalid value:
   :class:`SecretKeyError` (fail loudly, never fall back to plaintext).
2. ``OI_SECRET_KEY_FILE`` env var — path to a file holding the key.
   Missing/unreadable/invalid file: :class:`SecretKeyError`.
3. Default key file ``~/.oi/secret.key`` — loaded if present, otherwise
   generated once (``0600`` permissions) on first use.

If no key can be obtained, :func:`require_secret_crypto` raises
:class:`SecretKeyError`. The server calls it at startup and refuses to boot
the chat path; the backup code calls it before creating an archive.

Migration is idempotent: values already carrying the ``enc:v1:`` prefix are
left alone, so running it twice never double-encrypts.

.. warning::
   If the key is lost, encrypted secrets **cannot** be recovered. Keep the
   key file / ``OI_SECRET_KEY`` backed up separately and securely. Never log
   key material or plaintext secrets.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

if TYPE_CHECKING:
    from oi.infra.db.pool import DatabasePool

logger = logging.getLogger(__name__)

SECRET_KEY_ENV = "OI_SECRET_KEY"
SECRET_KEY_FILE_ENV = "OI_SECRET_KEY_FILE"
DEFAULT_KEY_FILE = Path.home() / ".oi" / "secret.key"

ENC_PREFIX = "enc:v1:"


class SecretKeyError(RuntimeError):
    """No usable encryption key is available, or a value cannot be decrypted.

    Raised loudly instead of silently falling back to plaintext storage.
    The message never contains key material or plaintext secrets.
    """


def _validate_key(raw: bytes) -> bytes:
    """Return *raw* if it is a usable Fernet key, else raise SecretKeyError."""
    try:
        Fernet(raw)
    except Exception as exc:
        raise SecretKeyError(
            "OI_SECRET_KEY is not a valid Fernet key; generate one with "
            "cryptography.fernet.Fernet.generate_key() and set it via the "
            "OI_SECRET_KEY env var or a key file."
        ) from exc
    return raw


def _read_key_file(path: Path) -> bytes:
    try:
        return path.read_bytes().strip()
    except OSError as exc:
        raise SecretKeyError(
            f"Cannot read secret key file {path}: {exc}. Set OI_SECRET_KEY or "
            "OI_SECRET_KEY_FILE to a readable key."
        ) from exc


def _generate_key_file(path: Path) -> bytes:
    """Generate a new key, store it with 0600 permissions, return it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, key + b"\n")
        finally:
            os.close(fd)
    except FileExistsError:
        # Raced with another process: load the key it just wrote.
        return _read_key_file(path)
    except OSError as exc:
        raise SecretKeyError(
            f"Cannot create secret key file {path}: {exc}. Set OI_SECRET_KEY "
            "to an existing key instead."
        ) from exc
    logger.info("Generated new secret key file at %s (0600). Keep it safe: "
                "losing it makes encrypted secrets unrecoverable.", path)
    return key


def resolve_secret_key() -> bytes:
    """Resolve the Fernet key bytes, generating the default file if needed.

    Raises :class:`SecretKeyError` when no usable key can be obtained.
    """
    env_key = os.getenv(SECRET_KEY_ENV)
    if env_key is not None and env_key.strip():
        return _validate_key(env_key.strip().encode("utf-8"))
    env_file = os.getenv(SECRET_KEY_FILE_ENV)
    if env_file:
        return _validate_key(_read_key_file(Path(env_file)))
    if DEFAULT_KEY_FILE.is_file():
        key = _validate_key(_read_key_file(DEFAULT_KEY_FILE))
        try:
            mode = stat.S_IMODE(DEFAULT_KEY_FILE.stat().st_mode)
        except OSError:
            mode = 0o600
        if mode & 0o077:
            logger.warning(
                "Secret key file %s is group/world-readable (mode %o). "
                "Restrict it with: chmod 600 %s",
                DEFAULT_KEY_FILE, mode, DEFAULT_KEY_FILE,
            )
        return key
    return _generate_key_file(DEFAULT_KEY_FILE)


class SecretCrypto:
    """Fernet wrapper with an ``enc:v1:`` prefix for stored values."""

    def __init__(self, key: bytes | None = None) -> None:
        self._fernet = Fernet(_validate_key(key) if key is not None else resolve_secret_key())

    @staticmethod
    def is_encrypted(value: str | None) -> bool:
        return bool(value) and value.startswith(ENC_PREFIX)

    def encrypt_text(self, plaintext: str) -> str:
        return ENC_PREFIX + self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt_text(self, value: str) -> str:
        if not value.startswith(ENC_PREFIX):
            raise SecretKeyError(
                "Value is not encrypted with the expected prefix; refusing to "
                "treat it as ciphertext."
            )
        try:
            return self._fernet.decrypt(value[len(ENC_PREFIX):].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretKeyError(
                "Cannot decrypt value: wrong key or corrupted ciphertext. "
                "The backup/DB was encrypted with a different OI_SECRET_KEY."
            ) from exc

    def encrypt_value(self, value: str | None) -> str | None:
        """Encrypt *value* for storage; None/empty/already-encrypted pass through."""
        if not value:
            return value
        if self.is_encrypted(value):
            return value
        return self.encrypt_text(value)

    def decrypt_value(self, value: str | None) -> str | None:
        """Decrypt a stored value; None/empty pass through.

        Non-encrypted (legacy plaintext) values are returned as-is so reads
        keep working until the one-time migration encrypts them.
        """
        if not value:
            return value
        if not self.is_encrypted(value):
            return value
        return self.decrypt_text(value)

    def encrypt_bytes(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt_bytes(self, data: bytes) -> bytes:
        try:
            return self._fernet.decrypt(data)
        except InvalidToken as exc:
            raise SecretKeyError(
                "Cannot decrypt backup secret: wrong key or corrupted data. "
                "The backup was encrypted with a different OI_SECRET_KEY."
            ) from exc


_CACHED: SecretCrypto | None = None


def get_secret_crypto() -> SecretCrypto:
    """Return the process-wide :class:`SecretCrypto` (fail loudly if unavailable)."""
    global _CACHED
    if _CACHED is None:
        _CACHED = SecretCrypto()
    return _CACHED


def require_secret_crypto() -> SecretCrypto:
    """Resolve the key or raise :class:`SecretKeyError`; never silent plaintext."""
    return get_secret_crypto()


def reset_secret_crypto_cache() -> None:
    """Drop the cached instance (tests only)."""
    global _CACHED
    _CACHED = None


def migrate_table_api_keys(
    pool: DatabasePool, table: str, *, crypto: SecretCrypto | None = None
) -> int:
    """Encrypt plaintext ``api_key`` values in *table* in place.

    Idempotent: already-encrypted values are left alone. Returns the number
    of rows migrated. Uses raw SQL so the repo's encrypt-on-write path cannot
    double-encrypt.
    """
    if table not in ("providers", "voice_providers"):
        raise ValueError(f"refusing to migrate unexpected table {table!r}")
    crypto = crypto or get_secret_crypto()
    migrated = 0
    with pool.transaction() as conn:
        rows = conn.execute(
            f"SELECT id, api_key FROM {table}"  # noqa: S608 - table allow-listed above
        ).fetchall()
        for row in rows:
            value = row["api_key"]
            if not value or SecretCrypto.is_encrypted(value):
                continue
            conn.execute(
                f"UPDATE {table} SET api_key = ? WHERE id = ?",  # noqa: S608
                (crypto.encrypt_text(value), row["id"]),
            )
            migrated += 1
    if migrated:
        logger.info("Migrated %d plaintext api_key(s) in %s to ciphertext.", migrated, table)
    return migrated


def migrate_all_provider_keys(
    pool: DatabasePool, *, crypto: SecretCrypto | None = None
) -> dict[str, int]:
    """Migrate LLM + voice provider keys. Returns ``{table: migrated}``."""
    crypto = crypto or get_secret_crypto()
    return {
        "providers": migrate_table_api_keys(pool, "providers", crypto=crypto),
        "voice_providers": migrate_table_api_keys(pool, "voice_providers", crypto=crypto),
    }
