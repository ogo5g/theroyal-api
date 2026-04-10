"""Onboarding router — progressive profile completion endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.onboarding import (
    BasicInfoRequest,
    BVNSubmitRequest,
    NINSubmitRequest,
    ProfilePhotoRequest,
)
from app.schemas.user import UserResponse
from app.services import onboarding as onboarding_service

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/status")
async def get_status(
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await onboarding_service.get_onboarding_status(current_user)
    return {
        "success": True,
        "data": result,
        "message": "Onboarding status retrieved.",
    }


@router.post("/basic-info")
async def submit_basic_info(
    data: BasicInfoRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await onboarding_service.submit_basic_info(current_user, data, db)
    return {
        "success": True,
        "data": UserResponse.model_validate(user).model_dump(),
        "message": "Basic information saved successfully.",
    }


@router.post("/nin")
async def submit_nin(
    data: NINSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await onboarding_service.submit_nin(current_user, data, db)
    return {
        "success": True,
        "data": UserResponse.model_validate(user).model_dump(),
        "message": "NIN submitted successfully.",
    }


@router.post("/bvn")
async def submit_bvn(
    data: BVNSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await onboarding_service.submit_bvn(current_user, data, db)
    return {
        "success": True,
        "data": UserResponse.model_validate(user).model_dump(),
        "message": "BVN submitted successfully.",
    }


@router.post("/profile-photo")
async def upload_profile_photo(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    user = await onboarding_service.upload_profile_photo(current_user, file, db)
    return {
        "success": True,
        "data": UserResponse.model_validate(user).model_dump(),
        "message": "Profile photo uploaded. Onboarding complete!",
    }
