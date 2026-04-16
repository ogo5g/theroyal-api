"""Admin — Payout History."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.kyc import KYC
from app.models.user import User, UserRole
from app.models.wallet import WalletTransaction, TransactionCategory, TransactionStatus
from app.utils.security import decrypt_field

router = APIRouter(prefix="/payouts", tags=["Admin — Payouts"])

admin_all = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MODERATOR, UserRole.STAFF)


@router.get("/stats")
async def get_payout_stats(
    admin: Annotated[User, Depends(admin_all)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Aggregate payout stats for summary cards."""
    base_where = WalletTransaction.category == TransactionCategory.PAYOUT

    total_count = (
        await db.execute(
            select(func.count()).select_from(WalletTransaction).where(base_where)
        )
    ).scalar() or 0

    success_count = (
        await db.execute(
            select(func.count())
            .select_from(WalletTransaction)
            .where(base_where, WalletTransaction.status == TransactionStatus.SUCCESSFUL)
        )
    ).scalar() or 0

    failed_count = (
        await db.execute(
            select(func.count())
            .select_from(WalletTransaction)
            .where(base_where, WalletTransaction.status == TransactionStatus.FAILED)
        )
    ).scalar() or 0

    pending_count = (
        await db.execute(
            select(func.count())
            .select_from(WalletTransaction)
            .where(base_where, WalletTransaction.status == TransactionStatus.PENDING)
        )
    ).scalar() or 0

    total_amount = (
        await db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(base_where)
        )
    ).scalar() or 0

    successful_amount = (
        await db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                base_where, WalletTransaction.status == TransactionStatus.SUCCESSFUL
            )
        )
    ).scalar() or 0

    return {
        "success": True,
        "data": {
            "total_count": total_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "total_amount": str(total_amount),
            "successful_amount": str(successful_amount),
        },
    }


@router.get("")
async def list_payouts(
    admin: Annotated[User, Depends(admin_all)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    """List all payout transactions with user and bank details."""
    base_where = WalletTransaction.category == TransactionCategory.PAYOUT

    count_query = (
        select(func.count()).select_from(WalletTransaction).where(base_where)
    )
    query = select(WalletTransaction).where(base_where)

    if status:
        query = query.where(WalletTransaction.status == status)
        count_query = count_query.where(WalletTransaction.status == status)

    total = (await db.execute(count_query)).scalar() or 0

    query = (
        query.order_by(WalletTransaction.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    txns = (await db.execute(query)).scalars().all()

    # Batch-load users and KYC records for all transactions
    user_ids = list({txn.user_id for txn in txns})
    users_map: dict = {}
    kyc_map: dict = {}

    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_result.scalars().all():
            users_map[u.id] = u

        kyc_result = await db.execute(select(KYC).where(KYC.user_id.in_(user_ids)))
        for k in kyc_result.scalars().all():
            kyc_map[k.user_id] = k

    data = []
    for txn in txns:
        item = {
            "id": str(txn.id),
            "txn_id": txn.txn_id,
            "reference": txn.reference,
            "provider_reference": txn.provider_reference,
            "amount": str(txn.amount),
            "status": txn.status.value,
            "description": txn.description,
            "created_at": txn.created_at.isoformat(),
        }

        u = users_map.get(txn.user_id)
        if u:
            item["user_id"] = str(u.id)
            item["user_email"] = u.email
            item["user_name"] = f"{u.first_name or ''} {u.last_name or ''}".strip() or None

        kyc = kyc_map.get(txn.user_id)
        if kyc:
            item["bank_name"] = kyc.bank_name
            item["account_name"] = kyc.account_name
            try:
                item["account_number"] = decrypt_field(kyc.account_number)
            except Exception:
                item["account_number"] = "****"

        data.append(item)

    return {
        "success": True,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
        },
    }
