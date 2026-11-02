"""Encryption for secrets the server must be able to read back, such as webhook signing secrets.

Secrets are encrypted with Fernet (AES-128-CBC plus HMAC-SHA256) using `HERMES_CREDENTIAL_ENCRYPTION_KEY`.
Production refuses to start without that key. In development a key is generated once and kept in
`backend/.dev-encryption-key`, which is git-ignored, so local data stays readable across restarts.
"""

import logging
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

logger = logging.getLogger("hermes.crypto")
_DEV_KEY_FILE = Path(__file__).resolve().parent.parent / ".dev-encryption-key"


class SecretDecryptionError(RuntimeError):
    """The ciphertext could not be decrypted, usually because the encryption key changed."""


def _load_dev_key() -> str:
    if _DEV_KEY_FILE.exists():
        return _DEV_KEY_FILE.read_text(encoding="ascii").strip()
    key = Fernet.generate_key().decode("ascii")
    _DEV_KEY_FILE.write_text(key, encoding="ascii")
    logger.warning("Generated a development encryption key at %s. Never use it in production.", _DEV_KEY_FILE)
    return key


def resolve_key(settings: Settings) -> str:
    if settings.credential_encryption_key:
        return settings.credential_encryption_key
    if settings.is_production:
        raise RuntimeError("HERMES_CREDENTIAL_ENCRYPTION_KEY must be set in production.")
    return _load_dev_key()


@lru_cache(maxsize=4)
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode("ascii"))


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    return _fernet(resolve_key(settings)).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(settings: Settings, ciphertext: str) -> str:
    try:
        return _fernet(resolve_key(settings)).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise SecretDecryptionError("Stored secret could not be decrypted.") from error
