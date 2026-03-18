"""Users router — profile endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return {
        "success": True,
        "data": UserResponse.model_validate(current_user).model_dump(),
        "message": "User profile retrieved.",
    }


@router.put("/me")
async def update_me(
    data: UserUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    return {
        "success": True,
        "data": UserResponse.model_validate(current_user).model_dump(),
        "message": "Profile updated successfully.",
    }
