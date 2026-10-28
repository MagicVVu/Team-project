"""Prototype-safe password hashing + revocable opaque tokens.

UNVERIFIED phone is a login identifier, NOT proof that the user owns the number.
Access limited to loopback/SSH tunnel. Add SMS verification + rate limiting
before opening public registrations.
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

PHONE_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
_password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
# The same Argon2 cost for unknown/disabled accounts closes the fast-miss oracle.
# Random dummy material is not a credential and is never stored in the database.
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(32))


def normalize_phone(raw: str) -> str:
    """Accept mainland China 11-digit mobiles or canonical E.164 worldwide."""
    value = raw.strip()
    if re.fullmatch(r"1[3-9][0-9]{9}", value):
        value = "+86" + value
    if not PHONE_E164.fullmatch(value):
        raise ValueError("Use a mainland 11-digit mobile or an E.164 number such as +8613800138000")
    return value


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(stored_hash: str, candidate: str) -> bool:
    try:
        return _password_hasher.verify(stored_hash, candidate)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False


def verify_login_password(stored_hash: str | None, candidate: str) -> bool:
    valid = verify_password(stored_hash or _dummy_password_hash, candidate)
    return stored_hash is not None and valid


def make_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, digest_token(token)


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def token_expiry(hours: int = 12) -> datetime:
    return now_utc() + timedelta(hours=hours)


def is_expired(expires_at: datetime) -> bool:
    # SQLite dev test returns naive values; PostgreSQL timestamptz returns aware.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= now_utc()
