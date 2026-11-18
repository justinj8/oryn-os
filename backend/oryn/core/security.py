"""Password hashing, JWTs and API keys."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from oryn.core.config import get_settings

_hasher = PasswordHasher()
API_KEY_PREFIX = "oryn_"


class AuthError(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=s.jwt_ttl_minutes)}
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256")


def decode_access_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise AuthError("invalid token") from e


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, key_hash). Only the hash is stored."""
    prefix = secrets.token_hex(4)
    full = f"{API_KEY_PREFIX}{prefix}_{secrets.token_urlsafe(24)}"
    return full, prefix, hash_api_key(full)


def parse_api_key_prefix(full_key: str) -> str | None:
    if not full_key.startswith(API_KEY_PREFIX):
        return None
    parts = full_key[len(API_KEY_PREFIX) :].split("_", 1)
    return parts[0] if len(parts) == 2 and len(parts[0]) == 8 else None
