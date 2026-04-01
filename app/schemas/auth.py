"""Auth request/response schemas."""

import re

from pydantic import BaseModel, EmailStr, field_validator


def normalize_phone(phone: str) -> str:
    """Normalize Nigerian phone number to +234 format."""
    phone = re.sub(r"[\s\-()]", "", phone)
    if phone.startswith("0"):
        phone = "+234" + phone[1:]
    elif phone.startswith("234"):
        phone = "+" + phone
    elif not phone.startswith("+234"):
        phone = "+234" + phone
    return phone


# ---------------------------------------------------------------------------
# Registration (email-only, step 1)
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = None  # Optional in dev, required in prod


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------
class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("OTP must be a 6-digit number")
        return v


class OTPResendRequest(BaseModel):
    email: EmailStr


# ---------------------------------------------------------------------------
# Set Password (step 3, after OTP)
# ---------------------------------------------------------------------------
class SetPasswordRequest(BaseModel):
    token: str  # Setup token from OTP verification
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        password = info.data.get("password")
        if password and v != password:
            raise ValueError("Passwords do not match")
        return v


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: str | None = None


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        password = info.data.get("new_password")
        if password and v != password:
            raise ValueError("Passwords do not match")
        return v
