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
# Registration Step 1 — phone number
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    phone_number: str
    turnstile_token: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = normalize_phone(v)
        if not re.match(r"^\+234\d{10}$", normalized):
            raise ValueError("Please provide a valid Nigerian phone number")
        return normalized


# ---------------------------------------------------------------------------
# Phone OTP Verification (step 2 of signup)
# ---------------------------------------------------------------------------
class PhoneOTPVerifyRequest(BaseModel):
    phone_number: str
    otp: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("OTP must be a 6-digit number")
        return v


# ---------------------------------------------------------------------------
# Registration Step 3 — submit email (after phone verified)
# ---------------------------------------------------------------------------
class SubmitEmailRequest(BaseModel):
    token: str   # setup token from phone OTP verification
    email: EmailStr


# ---------------------------------------------------------------------------
# Email OTP Verification (step 4 of signup)
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
    """Resend OTP — can be email or phone."""
    identifier: str  # phone number or email


# ---------------------------------------------------------------------------
# Set Password (step 5, after email OTP)
# ---------------------------------------------------------------------------
class SetPasswordRequest(BaseModel):
    token: str  # Setup token from email OTP verification
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
# Login — dual identifier (email+password OR phone→OTP)
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    identifier: str   # email address or phone number
    password: str | None = None  # required for email login; omit for phone OTP
    turnstile_token: str | None = None


class LoginOTPVerifyRequest(BaseModel):
    """Verify OTP for phone-based login."""
    phone_number: str
    otp: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("OTP must be a 6-digit number")
        return v


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
