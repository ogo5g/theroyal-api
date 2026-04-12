"""Auth business logic — register (email-first), OTP, login, JWT, password reset."""

from datetime import datetime, timezone
import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.user import OnboardingStep, User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SetPasswordRequest,
    SubmitPhoneRequest,
    normalize_phone,
)
from app.utils.codes import generate_otp
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.queue import WorkerPool
from app.services.security import verify_turnstile_token

# ---------------------------------------------------------------------------
# In-memory OTP store (replace with Redis in production)
# {identifier: {"otp": "123456", "expires_at": float, "attempts": 0, "user_id": str|None}}
# ---------------------------------------------------------------------------
_otp_store: dict[str, dict] = {}

OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

_EMAIL_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")


def _is_email(identifier: str) -> bool:
    return bool(_EMAIL_RE.match(identifier))


def _store_otp(identifier: str, otp: str, user_id: str | None = None) -> None:
    _otp_store[identifier] = {
        "otp": otp,
        "expires_at": datetime.now(timezone.utc).timestamp() + (OTP_EXPIRY_MINUTES * 60),
        "attempts": 0,
        "user_id": user_id,
    }


def _validate_otp(identifier: str, otp: str) -> dict:
    """Validate OTP from store. Returns the store entry on success."""
    entry = _otp_store.get(identifier)
    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not found or expired")

    entry["attempts"] += 1
    if entry["attempts"] > OTP_MAX_ATTEMPTS:
        _otp_store.pop(identifier, None)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many OTP attempts")

    if datetime.now(timezone.utc).timestamp() > entry["expires_at"]:
        _otp_store.pop(identifier, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired")

    if entry["otp"] != otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    _otp_store.pop(identifier, None)
    return entry


def _send_email_otp(email: str, otp: str) -> None:
    """Enqueue an email OTP via the worker pool."""
    subject = "Your TheRoyalSaving Verification Code"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1); color: #1E0A3C;">
        <h2 style="color: #D4AF37; margin-top: 0;">Verification Code</h2>
        <p>Please use the verification code below to confirm your email address.</p>
        <p style="font-size: 24px; font-weight: bold; letter-spacing: 4px; padding: 12px; background: #f3f4f6; text-align: center; border-radius: 8px;">
            {otp}
        </p>
        <p>This code expires in 10 minutes. Do not share it with anyone.</p>
    </div>
    """
    if WorkerPool.pool:
        import asyncio
        asyncio.ensure_future(
            WorkerPool.pool.enqueue_job("send_resend_email_task", email, subject, html_body)
        )


# ---------------------------------------------------------------------------
# Registration Step 1 — email → send email OTP
# ---------------------------------------------------------------------------
async def register_user(data: RegisterRequest, db: AsyncSession) -> User:
    """Register a new user with email and send email OTP.

    Re-entrant: if a partial registration exists (no password set), the record
    is reset so the user can restart the flow cleanly.
    """
    await verify_turnstile_token(data.turnstile_token)

    email = str(data.email)
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.hashed_password is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please log in.",
            )
        # Incomplete registration — reset and let them start over
        existing.phone_number = None
        existing.is_verified = False
        existing.onboarding_step = OnboardingStep.REGISTERED
        user = existing
    else:
        user = User(
            email=email,
            is_verified=False,
            onboarding_step=OnboardingStep.REGISTERED,
        )
        db.add(user)
        await db.flush()

        account = Account(user_id=user.id)
        db.add(account)

    otp = generate_otp()
    _store_otp(email, otp, str(user.id))

    subject = "Your TheRoyalSaving Verification Code"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1); color: #1E0A3C;">
        <h2 style="color: #D4AF37; margin-top: 0;">Verification Code</h2>
        <p>Please use the verification code below to confirm your email address.</p>
        <p style="font-size: 24px; font-weight: bold; letter-spacing: 4px; padding: 12px; background: #f3f4f6; text-align: center; border-radius: 8px;">
            {otp}
        </p>
        <p>This code expires in 10 minutes. Do not share it with anyone.</p>
    </div>
    """
    if WorkerPool.pool:
        await WorkerPool.pool.enqueue_job("send_resend_email_task", email, subject, html_body)

    if not settings.is_production:
        print(f"[DEV] Email OTP for {email}: {otp}")

    await db.commit()
    return user


# ---------------------------------------------------------------------------
# Registration Step 2 — verify email OTP
# ---------------------------------------------------------------------------
async def verify_otp(email: str, otp: str, db: AsyncSession) -> dict:
    """Verify email OTP, mark user as verified, return setup token."""
    _validate_otp(email, otp)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_verified = True
    user.onboarding_step = OnboardingStep.EMAIL_VERIFIED
    await db.commit()

    setup_token = create_access_token(
        {"sub": str(user.id), "purpose": "email_verified"},
        expire_minutes=30,
    )
    return {"setup_token": setup_token}


# ---------------------------------------------------------------------------
# Registration Step 3 — submit phone number (no OTP, just collect)
# ---------------------------------------------------------------------------
async def submit_phone(data: SubmitPhoneRequest, db: AsyncSession) -> dict:
    """Collect user's phone number after email verification. No SMS OTP."""
    payload = decode_token(data.token)
    if not payload or payload.get("purpose") != "email_verified":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired setup token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check phone not already taken by another user
    existing = await db.execute(
        select(User).where(User.phone_number == data.phone_number, User.id != user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this phone number already exists")

    user.phone_number = data.phone_number
    user.onboarding_step = OnboardingStep.PHONE_VERIFIED  # phone collected (verification deferred until Termii KYC complete)
    await db.commit()

    setup_token = create_access_token(
        {"sub": str(user.id), "purpose": "phone_collected"},
        expire_minutes=30,
    )
    return {"setup_token": setup_token}


# ---------------------------------------------------------------------------
# Registration Step 4 — set password
# ---------------------------------------------------------------------------
async def set_password(data: SetPasswordRequest, db: AsyncSession) -> dict:
    """Set password for a newly verified user and issue login tokens."""
    payload = decode_token(data.token)
    if not payload or payload.get("purpose") != "phone_collected":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired setup token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(data.password)
    user.onboarding_step = OnboardingStep.PASSWORD_SET
    await db.commit()

    token_data = {"sub": str(user.id), "role": user.role.value}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "onboarding_step": user.onboarding_step.value,
    }


# ---------------------------------------------------------------------------
# Resend OTP — email only (phone OTP deferred until Termii KYC complete)
# ---------------------------------------------------------------------------
async def resend_otp(identifier: str, db: AsyncSession) -> None:
    """Resend OTP to a user's email."""
    result = await db.execute(select(User).where(User.email == identifier))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    otp = generate_otp()
    _store_otp(identifier, otp, str(user.id))

    subject = "Your TheRoyalSaving Verification Code"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1); color: #1E0A3C;">
        <h2 style="color: #D4AF37; margin-top: 0;">Verification Code</h2>
        <p>Your new security code is below.</p>
        <p style="font-size: 24px; font-weight: bold; letter-spacing: 4px; padding: 12px; background: #f3f4f6; text-align: center; border-radius: 8px;">
            {otp}
        </p>
        <p>This code expires in 10 minutes. Do not share it with anyone.</p>
    </div>
    """
    if WorkerPool.pool:
        await WorkerPool.pool.enqueue_job("send_resend_email_task", identifier, subject, html_body)

    if not settings.is_production:
        print(f"[DEV] Resend OTP for {identifier}: {otp}")


# ---------------------------------------------------------------------------
# Login — email or phone, always with password
# ---------------------------------------------------------------------------
async def login_user(data: LoginRequest, db: AsyncSession) -> dict:
    """Authenticate user with (email or phone) + password."""
    await verify_turnstile_token(data.turnstile_token)

    identifier = data.identifier.strip()

    if _is_email(identifier):
        result = await db.execute(select(User).where(User.email == identifier))
    else:
        phone = normalize_phone(identifier)
        result = await db.execute(select(User).where(User.phone_number == phone))

    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    _check_user_status(user)

    token_data = {"sub": str(user.id), "role": user.role.value}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "onboarding_step": user.onboarding_step.value,
    }


def _check_user_status(user: User) -> None:
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please complete your registration before logging in",
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


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------
async def refresh_tokens(refresh_token: str, db: AsyncSession) -> dict:
    """Rotate refresh token and issue new token pair."""
    payload = decode_token(refresh_token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    token_data = {"sub": str(user.id), "role": user.role.value}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
async def logout_user(token: str) -> None:
    """Blacklist the current access token."""
    # TODO: Add to Redis blacklist
    pass


# ---------------------------------------------------------------------------
# Forgot / Reset Password
# ---------------------------------------------------------------------------
async def forgot_password(email: str, db: AsyncSession) -> None:
    """Send password reset token via email."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return  # Silent — don't reveal if email exists

    reset_token = create_access_token({"sub": str(user.id), "purpose": "password_reset"}, expire_minutes=30)

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    subject = "Reset your TheRoyalSaving password"
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1); color: #1E0A3C;">
        <h2 style="color: #D4AF37; margin-top: 0;">Password Reset Request</h2>
        <p>We received a request to reset your password. Click the button below to choose a new one:</p>
        <div style="text-align: center; margin: 24px 0;">
            <a href="{reset_url}" style="background-color: #1E0A3C; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                Reset Password
            </a>
        </div>
        <p>If you did not request this, you can safely ignore this email.</p>
        <p style="font-size: 12px; color: gray;">Or use this link: {reset_url}</p>
    </div>
    """
    if WorkerPool.pool:
        await WorkerPool.pool.enqueue_job("send_resend_email_task", email, subject, html_body)

    if not settings.is_production:
        print(f"[DEV] Password reset link for {email}: {reset_url}")


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
    """Reset password using a valid reset token."""
    payload = decode_token(token)
    if not payload or payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired reset token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.hashed_password = hash_password(new_password)
    await db.commit()
