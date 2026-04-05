"""Auth router — register, OTP, login, refresh, logout, password reset."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginOTPVerifyRequest,
    LoginRequest,
    OTPResendRequest,
    OTPVerifyRequest,
    PhoneOTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
    SubmitEmailRequest,
)
from app.schemas.user import UserResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
async def register(
    data: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Step 1: Submit phone number — receive phone OTP."""
    user = await auth_service.register_user(data, db)
    return {
        "success": True,
        "data": {"user_id": str(user.id), "phone_number": user.phone_number},
        "message": "OTP sent to your phone number.",
    }


@router.post("/verify-phone-otp")
async def verify_phone_otp(
    data: PhoneOTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Step 2: Verify phone OTP — receive setup token for email submission."""
    result = await auth_service.verify_phone_otp(data, db)
    return {
        "success": True,
        "data": result,
        "message": "Phone verified. Please provide your email address.",
    }


@router.post("/submit-email")
async def submit_email(
    data: SubmitEmailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Step 3: Submit email address — receive email OTP."""
    await auth_service.submit_email(data, db)
    return {
        "success": True,
        "data": None,
        "message": "OTP sent to your email address.",
    }


@router.post("/verify-otp")
async def verify_otp(
    data: OTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Step 4: Verify email OTP — receive setup token for set-password."""
    result = await auth_service.verify_otp(data.email, data.otp, db)
    return {
        "success": True,
        "data": result,
        "message": "Email verified. Please set your password.",
    }


@router.post("/set-password")
async def set_password(
    data: SetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Step 5: Set password and complete registration — receive auth tokens."""
    tokens = await auth_service.set_password(data, db)
    return {
        "success": True,
        "data": tokens,
        "message": "Password set. You are now logged in.",
    }


@router.post("/resend-otp")
async def resend_otp(
    data: OTPResendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await auth_service.resend_otp(data.identifier, db)
    return {
        "success": True,
        "data": None,
        "message": "OTP resent.",
    }


@router.post("/login")
async def login(
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login with email+password (returns tokens) or phone (sends OTP)."""
    result = await auth_service.login_user(data, db)
    return {
        "success": True,
        "data": result,
        "message": "Login successful." if not result.get("requires_otp") else "OTP sent to your phone.",
    }


@router.post("/login-otp-verify")
async def login_otp_verify(
    data: LoginOTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Verify phone OTP for phone-based login — returns auth tokens."""
    tokens = await auth_service.verify_login_otp(data.phone_number, data.otp, db)
    return {
        "success": True,
        "data": tokens,
        "message": "Login successful.",
    }


@router.post("/refresh")
async def refresh(
    data: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tokens = await auth_service.refresh_tokens(data.refresh_token, db)
    return {
        "success": True,
        "data": tokens,
        "message": "Tokens refreshed.",
    }


@router.post("/logout")
async def logout(
    current_user: Annotated[User, Depends(get_current_user)],
):
    await auth_service.logout_user("")
    return {
        "success": True,
        "data": None,
        "message": "Logged out successfully.",
    }


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await auth_service.forgot_password(data.email, db)
    return {
        "success": True,
        "data": None,
        "message": "If an account exists with that email, a reset link has been sent.",
    }


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await auth_service.reset_password(data.token, data.new_password, db)
    return {
        "success": True,
        "data": None,
        "message": "Password has been reset successfully.",
    }


@router.get("/me")
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return {
        "success": True,
        "data": UserResponse.model_validate(current_user).model_dump(),
        "message": "User retrieved.",
    }
