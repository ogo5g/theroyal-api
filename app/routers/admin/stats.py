"""Admin — Dashboard stats + Audit logs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.account import Account
from app.models.kyc import KYC, KYCStatus
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.models.wallet import WalletTransaction, TransactionCategory
from app.services import audit as audit_service

router = APIRouter(tags=["Admin — Dashboard"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.get("/dashboard/stats")
async def dashboard_stats(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get key platform metrics."""
    # Total users
    total_users = (await db.execute(
        select(func.count()).select_from(User)
    )).scalar()

    # Active subscriptions
    active_subs = (await db.execute(
        select(func.count()).select_from(Subscription)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
    )).scalar()

    # Completed subscriptions
    completed_subs = (await db.execute(
        select(func.count()).select_from(Subscription)
        .where(Subscription.status == SubscriptionStatus.COMPLETED)
    )).scalar()

    # Pending KYC
    pending_kyc = (await db.execute(
        select(func.count()).select_from(KYC)
        .where(KYC.status == KYCStatus.PENDING)
    )).scalar()

    # Total wallet funding
    total_funded = (await db.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .where(WalletTransaction.category == TransactionCategory.WALLET_FUNDING)
    )).scalar()

    # Total saved (across all accounts)
    total_saved = (await db.execute(
        select(func.coalesce(func.sum(Account.total_saved), 0))
    )).scalar()

    # Total withdrawn
    total_withdrawn = (await db.execute(
        select(func.coalesce(func.sum(Account.total_withdrawn), 0))
    )).scalar()

    # Defaulted subscriptions
    defaulted_subs = (await db.execute(
        select(func.count()).select_from(Subscription)
        .where(Subscription.status == SubscriptionStatus.DEFAULTED)
    )).scalar()

    return {
        "success": True,
        "data": {
            "total_users": total_users,
            "active_subscriptions": active_subs,
            "completed_subscriptions": completed_subs,
            "defaulted_subscriptions": defaulted_subs,
            "pending_kyc_reviews": pending_kyc,
            "total_funded": str(total_funded),
            "total_saved": str(total_saved),
            "total_withdrawn": str(total_withdrawn),
        },
        "message": "Dashboard stats.",
    }


@router.get("/audit-logs")
async def get_audit_logs(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
):
    result = await audit_service.list_audit_logs(
        db, page=page, per_page=per_page, action_filter=action
    )
    return {
        "success": True,
        "data": [
            {
                "id": str(log.id),
                "actor_id": str(log.actor_id),
                "action": log.action,
                "target_type": log.target_type,
                "target_id": str(log.target_id),
                "metadata": log.metadata_,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in result["items"]
        ],
        "pagination": {
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
        },
    }
