"""Auth request/response schemas."""

import re
from datetime import datetime

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
# Registration
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    phone_number: str
    password: str
    first_name: str
    last_name: str
    turnstile_token: str | None = None  # Optional in dev, required in prod

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = normalize_phone(v)
        if not re.match(r"^\+234[0-9]{10}$", normalized):
            raise ValueError("Invalid Nigerian phone number")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


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

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
