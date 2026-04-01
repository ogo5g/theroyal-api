"""Auth business logic — register, OTP, login, JWT, password reset."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.user import OnboardingStep, User
from app.schemas.auth import RegisterRequest, LoginRequest, SetPasswordRequest
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
# {email: {"otp": "123456", "expires_at": float, "attempts": 0}}
_otp_store: dict[str, dict] = {}

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Registration (email only)
# ---------------------------------------------------------------------------
async def register_user(data: RegisterRequest, db: AsyncSession) -> User:
    """Register a new user with email only and send OTP."""
    # Check for existing email
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # Create user (email only — everything else comes later)
    user = User(
        email=data.email,
        is_verified=False,
        onboarding_step=OnboardingStep.REGISTERED,
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
    if not settings.is_production:
        print(f"[DEV] OTP for {data.email}: {otp}")

    return user


# ---------------------------------------------------------------------------
# OTP Verification
# ---------------------------------------------------------------------------
async def verify_otp(email: str, otp: str, db: AsyncSession) -> dict:
    """Verify OTP, mark user as verified, and return a setup token."""
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
        remaining = OTP_MAX_ATTEMPTS - stored["attempts"]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
        )

    # Mark verified
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_verified = True
    user.onboarding_step = OnboardingStep.EMAIL_VERIFIED
    del _otp_store[email]

    # Issue a short-lived setup token so user can proceed to set password
    setup_token = create_access_token(
        {"sub": str(user.id), "type": "setup"},
    )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "setup_token": setup_token,
    }


# ---------------------------------------------------------------------------
# Set Password (after OTP verification)
# ---------------------------------------------------------------------------
async def set_password(data: SetPasswordRequest, db: AsyncSession) -> dict:
    """Set password for a newly verified user and issue login tokens."""
    payload = decode_token(data.token)
    if not payload or payload.get("type") != "setup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired setup token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.hashed_password is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password has already been set",
        )

    user.hashed_password = hash_password(data.password)
    user.onboarding_step = OnboardingStep.PASSWORD_SET

    # Issue full login tokens so the user can proceed to onboarding
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

    if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
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
        "onboarding_step": user.onboarding_step.value,
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
