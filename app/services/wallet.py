"""Wallet business logic — activation, balance, credit/debit, transactions."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.user import User
from app.models.wallet import (
    TransactionCategory,
    TransactionStatus,
    TransactionType,
    WalletTransaction,
)
from app.services.payments.platnova import platnova
from app.utils.codes import generate_payment_reference


# ---------------------------------------------------------------------------
# Wallet Activation (creates Platnova virtual account)
# ---------------------------------------------------------------------------
async def activate_wallet(user: User, db: AsyncSession) -> Account:
    """Activate user's wallet by creating a Platnova virtual account."""
    result = await db.execute(select(Account).where(Account.user_id == user.id))
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if account.wallet_activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wallet is already activated",
        )

    # Call Platnova to create virtual account
    try:
        virtual_account = await platnova.create_virtual_account(
            email=user.email,
            first_name=user.first_name or "User",
            last_name=user.last_name or "User",
            phone=user.phone_number,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create virtual account: {str(e)}",
        )

    account.virtual_account_number = virtual_account["account_number"]
    account.virtual_account_bank = virtual_account["bank_name"]
    account.virtual_account_reference = virtual_account["reference"]
    account.wallet_activated = True

    return account


# ---------------------------------------------------------------------------
# Get Wallet Info
# ---------------------------------------------------------------------------
async def get_wallet(user: User, db: AsyncSession) -> Account:
    """Get the user's wallet/account info."""
    result = await db.execute(select(Account).where(Account.user_id == user.id))
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return account


# ---------------------------------------------------------------------------
# Credit / Debit
# ---------------------------------------------------------------------------
async def credit_wallet(
    user_id,
    amount: Decimal,
    category: TransactionCategory,
    reference: str,
    description: str,
    db: AsyncSession,
    provider_reference: str | None = None,
    metadata: dict | None = None,
) -> WalletTransaction:
    """Credit the user's wallet and record a transaction."""
    result = await db.execute(select(Account).where(Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Create transaction
    txn = WalletTransaction(
        user_id=user_id,
        amount=amount,
        type=TransactionType.CREDIT,
        category=category,
        reference=reference,
        description=description,
        status=TransactionStatus.SUCCESSFUL,
        provider_reference=provider_reference,
        metadata_=metadata,
    )
    db.add(txn)

    # Update balance
    account.wallet_balance += amount

    if category == TransactionCategory.PAYOUT:
        account.total_withdrawn += amount
    elif category == TransactionCategory.WALLET_FUNDING:
        pass  # wallet_balance already reflects it

    return txn


async def debit_wallet(
    user_id,
    amount: Decimal,
    category: TransactionCategory,
    reference: str,
    description: str,
    db: AsyncSession,
    provider_reference: str | None = None,
    metadata: dict | None = None,
) -> WalletTransaction:
    """Debit the user's wallet and record a transaction. Raises if insufficient funds."""
    result = await db.execute(select(Account).where(Account.user_id == user_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if account.wallet_balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient wallet balance. Available: ₦{account.wallet_balance:,.2f}",
        )

    # Create transaction
    txn = WalletTransaction(
        user_id=user_id,
        amount=amount,
        type=TransactionType.DEBIT,
        category=category,
        reference=reference,
        description=description,
        status=TransactionStatus.SUCCESSFUL,
        provider_reference=provider_reference,
        metadata_=metadata,
    )
    db.add(txn)

    # Update balance
    account.wallet_balance -= amount

    if category in (TransactionCategory.PLAN_INSTALLMENT, TransactionCategory.PLAN_COMMISSION):
        account.total_saved += amount

    return txn


# ---------------------------------------------------------------------------
# Transaction History
# ---------------------------------------------------------------------------
async def get_transactions(
    user: User,
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    category: str | None = None,
    tx_type: str | None = None,
) -> dict:
    """Get paginated wallet transactions for a user."""
    query = select(WalletTransaction).where(WalletTransaction.user_id == user.id)
    count_query = select(func.count()).select_from(WalletTransaction).where(
        WalletTransaction.user_id == user.id
    )

    if category:
        query = query.where(WalletTransaction.category == category)
        count_query = count_query.where(WalletTransaction.category == category)

    if tx_type:
        query = query.where(WalletTransaction.type == tx_type)
        count_query = count_query.where(WalletTransaction.type == tx_type)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = query.order_by(WalletTransaction.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    transactions = result.scalars().all()

    return {
        "items": transactions,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


# ---------------------------------------------------------------------------
# Process Funding Webhook
# ---------------------------------------------------------------------------
async def process_funding_webhook(
    reference: str,
    amount: Decimal,
    provider_reference: str,
    metadata: dict,
    db: AsyncSession,
) -> WalletTransaction:
    """Process a successful wallet funding event from Platnova webhook."""
    # Find the account by virtual account reference
    account_ref = metadata.get("virtual_account_reference", "")
    result = await db.execute(
        select(Account).where(Account.virtual_account_reference == account_ref)
    )
    account = result.scalar_one_or_none()

    if not account:
        # Try finding by other means in metadata
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found for this virtual account",
        )

    # Check for duplicate transaction (idempotency at DB level)
    existing = await db.execute(
        select(WalletTransaction).where(WalletTransaction.reference == reference)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction already processed",
        )

    # Credit the wallet
    txn = await credit_wallet(
        user_id=account.user_id,
        amount=amount,
        category=TransactionCategory.WALLET_FUNDING,
        reference=reference,
        description=f"Wallet funded via bank transfer - ₦{amount:,.2f}",
        db=db,
        provider_reference=provider_reference,
        metadata=metadata,
    )

    return txn
