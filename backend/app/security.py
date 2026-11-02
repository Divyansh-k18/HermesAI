"""Password hashing, opaque token generation, and token hashing."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256

_hasher = PasswordHasher()
# Used to keep login timing constant when the email does not exist.
_DUMMY_HASH = _hasher.hash("hermes-timing-equalisation-only")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def burn_password_check(password: str) -> None:
    """Perform a hash verification so unknown-email logins take as long as known-email logins."""
    verify_password(_DUMMY_HASH, password)


def password_policy_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if password.lower() == password or password.upper() == password:
        errors.append("Password must mix upper and lower case letters.")
    if not any(ch.isdigit() for ch in password):
        errors.append("Password must contain at least one digit.")
    return errors


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
