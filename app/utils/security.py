"""Security utilities: Fernet encryption, password hashing, JWT, HMAC."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
def create_access_token(data: dict, expire_minutes: int | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expire_minutes if expire_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT. Returns the payload or None on failure."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Fernet encryption (BVN, NIN, account numbers)
# ---------------------------------------------------------------------------
def _get_fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise ValueError("FIELD_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_field(value: str) -> str:
    """Encrypt a sensitive field value. Returns base64-encoded ciphertext."""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_field(encrypted_value: str) -> str:
    """Decrypt a sensitive field value."""
    return _get_fernet().decrypt(encrypted_value.encode()).decode()


# ---------------------------------------------------------------------------
# HMAC verification (webhooks)
# ---------------------------------------------------------------------------
def verify_hmac_signature(
    payload: bytes, signature: str, secret: str, algorithm: str = "sha512"
) -> bool:
    """Verify HMAC signature for webhook payloads."""
    expected = hmac.new(
        secret.encode(), payload, getattr(hashlib, algorithm)
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
