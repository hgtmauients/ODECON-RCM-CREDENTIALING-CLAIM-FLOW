"""
Password hashing helpers for User table login.

Argon2id via passlib. Wrapped here so the rest of the codebase doesn\'t
import passlib directly — keeps the swap path open if we later move to
e.g. bcrypt or hand the auth off to OIDC entirely.
"""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return an Argon2id hash for the supplied plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison; returns False if the hash is malformed."""
    if not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the hash uses outdated parameters and should be re-hashed on next login."""
    try:
        return _pwd_context.needs_update(hashed)
    except Exception:
        return False
