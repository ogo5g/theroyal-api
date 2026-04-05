"""Auth business logic — register (phone), OTP, login, JWT, password reset."""

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
    PhoneOTPVerifyRequest,
    RegisterRequest,
    SetPasswordRequest,
    SubmitEmailRequest,
)
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
# Keys are phone numbers (for signup/login) or emails (for email OTP).
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


# ---------------------------------------------------------------------------
# Registration Step 1 — phone number → send phone OTP
# ---------------------------------------------------------------------------
async def register_user(data: RegisterRequest, db: AsyncSession) -> User:
    """Register a new user with phone number and send phone OTP."""
    existing = await db.execute(select(User).where(User.phone_number == data.phone_number))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this phone number already exists",
        )

    user = User(
        phone_number=data.phone_number,
        is_verified=False,
        onboarding_step=OnboardingStep.REGISTERED,
    )
    db.add(user)
    await db.flush()

    account = Account(user_id=user.id)
    db.add(account)

    otp = generate_otp()
    _store_otp(data.phone_number, otp, str(user.id))

    # TODO: Send SMS via Termii (enqueue via RQ)
    if not settings.is_production:
        print(f"[DEV] Phone OTP for {data.phone_number}: {otp}")

    await db.commit()
    return user


# ---------------------------------------------------------------------------
# Registration Step 2 — verify phone OTP → return setup token
# ---------------------------------------------------------------------------
async def verify_phone_otp(data: PhoneOTPVerifyRequest, db: AsyncSession) -> dict:
    """Verify phone OTP and return a setup token for the next steps."""
    entry = _validate_otp(data.phone_number, data.otp)

    result = await db.execute(select(User).where(User.phone_number == data.phone_number))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.onboarding_step = OnboardingStep.PHONE_VERIFIED
    await db.commit()

    # Issue a temporary setup token (same mechanism as email OTP step)
    setup_token = create_access_token(
        {"sub": str(user.id), "purpose": "phone_verified"},
        expire_minutes=30,
    )
    return {"setup_token": setup_token}


# ---------------------------------------------------------------------------
# Registration Step 3 — submit email (after phone verified)
# ---------------------------------------------------------------------------
async def submit_email(data: SubmitEmailRequest, db: AsyncSession) -> None:
    """Accept user's email, send email OTP."""
    # Decode setup token
    payload = decode_token(data.token)
    if not payload or payload.get("purpose") != "phone_verified":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired setup token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check email not already taken
    existing = await db.execute(select(User).where(User.email == str(data.email), User.id != user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    user.email = str(data.email)
    await db.commit()

    otp = generate_otp()
    _store_otp(str(data.email), otp, str(user.id))

    # TODO: Send email via Resend (enqueue via RQ)
    if not settings.is_production:
        print(f"[DEV] Email OTP for {data.email}: {otp}")


# ---------------------------------------------------------------------------
# Registration Step 4 — verify email OTP → return setup token for set-password
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
# Registration Step 5 — set password
# ---------------------------------------------------------------------------
async def set_password(data: SetPasswordRequest, db: AsyncSession) -> dict:
    """Set password for a newly verified user and issue login tokens."""
    payload = decode_token(data.token)
    if not payload or payload.get("purpose") != "email_verified":
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
# Resend OTP — phone or email
# ---------------------------------------------------------------------------
async def resend_otp(identifier: str, db: AsyncSession) -> None:
    """Resend OTP to a user's phone or email."""
    if _is_email(identifier):
        result = await db.execute(select(User).where(User.email == identifier))
    else:
        result = await db.execute(select(User).where(User.phone_number == identifier))

    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    otp = generate_otp()
    _store_otp(identifier, otp, str(user.id))

    if not settings.is_production:
        print(f"[DEV] Resend OTP for {identifier}: {otp}")


# ---------------------------------------------------------------------------
# Login — email+password OR phone→OTP
# ---------------------------------------------------------------------------
async def login_user(data: LoginRequest, db: AsyncSession) -> dict:
    """Authenticate user. Email identifier uses password; phone sends OTP."""
    identifier = data.identifier.strip()

    if _is_email(identifier):
        # Email + password login
        if not data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required for email login",
            )

        result = await db.execute(select(User).where(User.email == identifier))
        user = result.scalar_one_or_none()

        if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        _check_user_status(user)

        token_data = {"sub": str(user.id), "role": user.role.value}
        return {
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "onboarding_step": user.onboarding_step.value,
            "requires_otp": False,
        }
    else:
        # Phone → send login OTP
        from app.schemas.auth import normalize_phone
        phone = normalize_phone(identifier)

        result = await db.execute(select(User).where(User.phone_number == phone))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found with this phone number")

        _check_user_status(user)

        otp = generate_otp()
        _store_otp(phone, otp, str(user.id))

        # TODO: Send SMS via Termii
        if not settings.is_production:
            print(f"[DEV] Login OTP for {phone}: {otp}")

        return {
            "requires_otp": True,
            "phone_number": phone,
            "message": "OTP sent to your phone number",
        }


async def verify_login_otp(phone_number: str, otp: str, db: AsyncSession) -> dict:
    """Verify OTP for phone-based login and return tokens."""
    from app.schemas.auth import normalize_phone
    phone = normalize_phone(phone_number)

    _validate_otp(phone, otp)

    result = await db.execute(select(User).where(User.phone_number == phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    _check_user_status(user)

    token_data = {"sub": str(user.id), "role": user.role.value}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "onboarding_step": user.onboarding_step.value,
        "requires_otp": False,
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

    # TODO: Send reset email via Resend
    if not settings.is_production:
        print(f"[DEV] Password reset token for {email}: {reset_token}")


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
