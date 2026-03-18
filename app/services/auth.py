"""Auth business logic — register, OTP, login, JWT, password reset."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest
from app.utils.codes import generate_otp
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

# ---------------------------------------------------------------------------
# In-memory OTP store (replace with Redis in production)
# ---------------------------------------------------------------------------
# {email: {"otp": "123456", "expires_at": datetime, "attempts": 0}}
_otp_store: dict[str, dict] = {}

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
async def register_user(data: RegisterRequest, db: AsyncSession) -> User:
    """Register a new user and send OTP."""
    # Check for existing email
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # Check for existing phone
    existing_phone = await db.execute(
        select(User).where(User.phone_number == data.phone_number)
    )
    if existing_phone.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this phone number already exists",
        )

    # Create user
    user = User(
        email=data.email,
        phone_number=data.phone_number,
        hashed_password=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        is_verified=False,
    )
    db.add(user)
    await db.flush()

    # Create associated account
    account = Account(user_id=user.id)
    db.add(account)

    # Generate and store OTP
    otp = generate_otp()
    _otp_store[data.email] = {
        "otp": otp,
        "expires_at": datetime.now(timezone.utc).timestamp() + (OTP_EXPIRY_MINUTES * 60),
        "attempts": 0,
    }

    # TODO: Enqueue OTP email via RQ (send_otp_email job)
    # For now, log in development
    if not settings.is_production:
        print(f"[DEV] OTP for {data.email}: {otp}")

    return user


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------
async def verify_otp(email: str, otp: str, db: AsyncSession) -> User:
    """Verify OTP and mark user as verified."""
    stored = _otp_store.get(email)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found for this email. Please request a new one.",
        )

    # Check expiry
    if datetime.now(timezone.utc).timestamp() > stored["expires_at"]:
        del _otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one.",
        )

    # Check attempts
    stored["attempts"] += 1
    if stored["attempts"] > OTP_MAX_ATTEMPTS:
        del _otp_store[email]
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please request a new OTP.",
        )

    # Validate
    if stored["otp"] != otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {OTP_MAX_ATTEMPTS - stored['attempts']} attempts remaining.",
        )

    # Mark verified
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_verified = True
    del _otp_store[email]

    return user


# ---------------------------------------------------------------------------
# Resend OTP
# ---------------------------------------------------------------------------
async def resend_otp(email: str, db: AsyncSession) -> None:
    """Resend OTP to a user's email."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already verified",
        )

    otp = generate_otp()
    _otp_store[email] = {
        "otp": otp,
        "expires_at": datetime.now(timezone.utc).timestamp() + (OTP_EXPIRY_MINUTES * 60),
        "attempts": 0,
    }

    if not settings.is_production:
        print(f"[DEV] OTP for {email}: {otp}")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
async def login_user(data: LoginRequest, db: AsyncSession) -> dict:
    """Authenticate user and return token pair."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )

    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact support.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated",
        )

    token_data = {"sub": str(user.id), "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------
async def refresh_tokens(refresh_token: str, db: AsyncSession) -> dict:
    """Rotate refresh token and issue new token pair."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # TODO: Check Redis blacklist for old refresh token
    # TODO: Blacklist the old refresh token in Redis

    token_data = {"sub": str(user.id), "role": user.role.value}
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
async def logout_user(token: str) -> None:
    """Blacklist the current access token."""
    # TODO: Add token to Redis blacklist with TTL matching token expiry
    pass


# ---------------------------------------------------------------------------
# Forgot / Reset Password
# ---------------------------------------------------------------------------
async def forgot_password(email: str, db: AsyncSession) -> None:
    """Send password reset token via email."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if not user:
        return

    # Generate a short-lived reset token (reusing JWT with custom type)
    reset_token = create_access_token({"sub": str(user.id), "type": "reset"})

    # TODO: Enqueue reset email via RQ
    if not settings.is_production:
        print(f"[DEV] Password reset token for {email}: {reset_token}")


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
    """Reset password using a valid reset token."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(new_password)
