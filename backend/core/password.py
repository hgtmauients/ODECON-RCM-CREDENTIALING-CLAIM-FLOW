"""
Password hashing helpers for User table login.

Argon2id via argon2-cffi.

This module owns hashing policy so the rest of the codebase stays insulated
from implementation details and future algorithm migrations.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Explicit policy values (argon2-cffi defaults) kept here for visibility and
# to allow controlled future tuning.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
)


def hash_password(plain: str) -> str:
    """Return an Argon2id hash for the supplied plaintext password."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison; returns False if the hash is malformed."""
    if not hashed:
        return False
    try:
        return bool(_hasher.verify(hashed, plain))
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the hash uses outdated parameters and should be re-hashed on next login."""
    if not hashed:
        return False
    try:
        return bool(_hasher.check_needs_rehash(hashed))
    except (InvalidHashError, VerificationError):
        return False
