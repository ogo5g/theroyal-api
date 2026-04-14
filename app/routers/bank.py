"""Bank router — handle bank lists and account resolution."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.payments.paystack import paystack

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.get("")
async def list_banks(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all supported Nigerian banks."""
    try:
        banks = await paystack.list_banks()
        # Optionally cache this in redis in the future, as it rarely changes
        return {
            "success": True,
            "data": banks,
            "message": "Bank list retrieved.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch bank list: {str(e)}"
        )


@router.get("/resolve")
async def resolve_account(
    current_user: Annotated[User, Depends(get_current_user)],
    account_number: str = Query(..., min_length=10, max_length=10),
    bank_code: str = Query(...),
):
    """Resolve an account number to an account name."""
    try:
        data = await paystack.resolve_account(account_number, bank_code)
        return {
            "success": True,
            "data": data,
            "message": "Account resolved successfully.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to resolve account. Verify the account number and bank. Error: {str(e)}"
        )
