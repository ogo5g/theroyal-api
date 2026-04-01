"""Wallet router — balance, activate, transactions, virtual account."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.wallet import TransactionResponse, VirtualAccountResponse, WalletResponse
from app.services import wallet as wallet_service

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get("")
async def get_wallet(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = await wallet_service.get_wallet(current_user, db)
    return {
        "success": True,
        "data": WalletResponse.model_validate(account).model_dump(),
        "message": "Wallet info retrieved.",
    }


@router.post("/activate")
async def activate_wallet(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = await wallet_service.activate_wallet(current_user, db)
    return {
        "success": True,
        "data": {
            "wallet_activated": account.wallet_activated,
            "virtual_account_number": account.virtual_account_number,
            "virtual_account_bank": account.virtual_account_bank,
        },
        "message": "Wallet activated successfully. Use the virtual account to fund your wallet.",
    }


@router.get("/transactions")
async def get_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    type: str | None = Query(None, alias="type"),
):
    result = await wallet_service.get_transactions(
        current_user, db, page=page, per_page=per_page, category=category, tx_type=type
    )
    return {
        "success": True,
        "data": [
            TransactionResponse.model_validate(t).model_dump()
            for t in result["items"]
        ],
        "pagination": {
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
        },
    }


@router.get("/virtual-account")
async def get_virtual_account(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    account = await wallet_service.get_wallet(current_user, db)
    if not account.wallet_activated:
        return {
            "success": False,
            "error": "wallet_not_activated",
            "message": "Please activate your wallet first.",
        }
    return {
        "success": True,
        "data": {
            "account_number": account.virtual_account_number,
            "bank_name": account.virtual_account_bank,
            "reference": account.virtual_account_reference,
        },
        "message": "Virtual account details retrieved.",
    }
