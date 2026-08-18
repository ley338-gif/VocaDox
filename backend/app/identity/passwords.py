"""Password hashing.

Uses argon2-cffi (Argon2id via `argon2.PasswordHasher`'s default profile),
the OWASP-recommended modern password hashing algorithm, memory-hard and
resistant to GPU/ASIC cracking. License: MIT — see
compliance/dependency-inventory.yml. Actively maintained
(https://github.com/hynek/argon2-cffi).

Passwords are never logged: callers must not pass raw passwords to the
structured logger (see `app/platform/logging.py`'s `_SENSITIVE_KEYS`
redaction, which also catches accidental `password=` log kwargs).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# A generous minimum — real strength policy (dictionary checks, breach
# lists, etc.) is out of scope for Phase 1; this only prevents trivially
# empty/short passwords at the API boundary.
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    """Hash `password` with Argon2id. Raises ValueError if too short."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-safe verification (argon2-cffi handles this internally)."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if `password_hash` was produced with weaker-than-current parameters."""
    return _hasher.check_needs_rehash(password_hash)
