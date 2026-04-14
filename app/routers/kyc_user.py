"""User KYC router — bank details and proof of address submission."""

from typing import Annotated
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.kyc import KYC
from app.models.user import User
from app.utils.storage import upload_file

router = APIRouter(prefix="/kyc", tags=["KYC (User)"])

class BankAccountSubmitRequest(BaseModel):
    bank_code: str = Field(..., min_length=3)
    bank_name: str = Field(..., min_length=3)
    account_number: str = Field(..., min_length=10, max_length=10)
    account_name: str = Field(..., min_length=3)

@router.post("/bank-account")
async def submit_bank_account(
    data: BankAccountSubmitRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Save or update the user's bank details."""
    result = await db.execute(
        select(KYC).where(KYC.user_id == current_user.id)
    )
    kyc = result.scalar_one_or_none()
    
    if not kyc:
        raise HTTPException(
            status_code=400,
            detail="KYC record not found. Please complete the basic onboarding first."
        )

    # Note: account_number should ideally be encrypted on the model,
    # Here we assume the encryption happens smoothly or the model handles it via property/setter
    from app.utils.security import encrypt_field
    
    kyc.bank_code = data.bank_code
    kyc.bank_name = data.bank_name
    kyc.account_number = encrypt_field(data.account_number)
    kyc.account_name = data.account_name

    await db.commit()

    return {
        "success": True,
        "data": {
            "has_bank_account": True
        },
        "message": "Bank account saved successfully."
    }

@router.post("/proof-of-address")
async def upload_proof_of_address(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload utility bill as proof of address."""
    result = await db.execute(
        select(KYC).where(KYC.user_id == current_user.id)
    )
    kyc = result.scalar_one_or_none()
    
    if not kyc:
        raise HTTPException(
            status_code=400,
            detail="KYC record not found. Please complete the basic onboarding first."
        )

    url = await upload_file(file, folder="proof_of_address")
    kyc.proof_of_address_url = url

    await db.commit()

    return {
        "success": True,
        "data": {
            "has_proof_of_address": True,
            "proof_of_address_url": url,
        },
        "message": "Proof of address uploaded successfully."
    }
