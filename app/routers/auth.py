"""Auth router — register, OTP, login, refresh, logout, password reset."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    OTPResendRequest,
    OTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SetPasswordRequest,
)
from app.schemas.user import UserResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register")
async def register(
    data: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await auth_service.register_user(data, db)
    return {
        "success": True,
        "data": {"user_id": str(user.id), "email": user.email},
        "message": "Registration successful. Please check your email for the OTP.",
    }


@router.post("/verify-otp")
async def verify_otp(
    data: OTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await auth_service.verify_otp(data.email, data.otp, db)
    return {
        "success": True,
        "data": result,
        "message": "Email verified successfully. Please set your password.",
    }


@router.post("/set-password")
async def set_password(
    data: SetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tokens = await auth_service.set_password(data, db)
    return {
        "success": True,
        "data": tokens,
        "message": "Password set successfully. You are now logged in.",
    }


@router.post("/resend-otp")
async def resend_otp(
    data: OTPResendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await auth_service.resend_otp(data.email, db)
    return {
        "success": True,
        "data": None,
        "message": "OTP has been resent to your email.",
    }


@router.post("/login")
async def login(
    data: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tokens = await auth_service.login_user(data, db)
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
        "message": "Tokens refreshed successfully.",
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
