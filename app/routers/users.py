"""Users router — profile endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from sqlalchemy import select
from app.models.kyc import KYC
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(KYC).where(KYC.user_id == current_user.id))
    kyc = result.scalar_one_or_none()

    data = UserResponse.model_validate(current_user).model_dump()
    data["has_bank_account"] = kyc is not None and kyc.account_number is not None
    data["has_proof_of_address"] = kyc is not None and kyc.proof_of_address_url is not None
    data["kyc_status"] = kyc.status.value if kyc else "unsubmitted"

    return {
        "success": True,
        "data": data,
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

    result = await db.execute(select(KYC).where(KYC.user_id == current_user.id))
    kyc = result.scalar_one_or_none()

    data = UserResponse.model_validate(current_user).model_dump()
    data["has_bank_account"] = kyc is not None and kyc.account_number is not None
    data["has_proof_of_address"] = kyc is not None and kyc.proof_of_address_url is not None
    data["kyc_status"] = kyc.status.value if kyc else "unsubmitted"

    return {
        "success": True,
        "data": data,
        "message": "Profile updated successfully.",
    }
