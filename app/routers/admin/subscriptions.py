"""Admin — Subscription management."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.subscription import PaymentSchedule, Subscription
from app.models.user import User, UserRole
from app.models.wallet import WalletTransaction
from app.schemas.subscription import ScheduleItemResponse, SubscriptionResponse

router = APIRouter(prefix="/subscriptions", tags=["Admin — Subscriptions"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MODERATOR, UserRole.STAFF)


@router.get("")
async def list_subscriptions(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
):
    query = select(Subscription)
    count_query = select(func.count()).select_from(Subscription)

    if status:
        query = query.where(Subscription.status == status)
        count_query = count_query.where(Subscription.status == status)

    if user_id:
        query = query.where(Subscription.user_id == user_id)
        count_query = count_query.where(Subscription.user_id == user_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Subscription.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    subs = result.scalars().all()

    # Build response with user info
    data = []
    for s in subs:
        d = SubscriptionResponse.model_validate(s).model_dump()
        if s.plan:
            d["plan_code"] = s.plan.code
            d["plan_name"] = s.plan.name
        # Eagerly load user for list display
        user_result = await db.execute(select(User).where(User.id == s.user_id))
        u = user_result.scalar_one_or_none()
        if u:
            d["user_email"] = u.email
            d["user_name"] = f"{u.first_name or ''} {u.last_name or ''}".strip() or None
        data.append(d)

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


@router.get("/{sid}")
async def get_subscription(
    sid: str,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Subscription).where(Subscription.sid == sid))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    d = SubscriptionResponse.model_validate(sub).model_dump()

    # Attach plan info
    if sub.plan:
        d["plan_code"] = sub.plan.code
        d["plan_name"] = sub.plan.name

    # Attach user info
    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    u = user_result.scalar_one_or_none()
    if u:
        d["user_email"] = u.email
        d["user_name"] = f"{u.first_name or ''} {u.last_name or ''}".strip() or None
        d["user_id"] = str(u.id)

    # Referral active check
    today = date.today()
    d["is_referral_code_active"] = (
        sub.referral_code_available_at is not None
        and sub.referral_code_expires_at is not None
        and sub.referral_code_available_at <= today <= sub.referral_code_expires_at
    )
    d["referral_code"] = sub.referral_code

    # Downline count
    dl_count_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.upline_subscription_id == sub.id
        )
    )
    d["downline_count"] = dl_count_result.scalar() or 0

    return {
        "success": True,
        "data": d,
        "message": "Subscription retrieved.",
    }


@router.get("/{sid}/schedule")
async def get_subscription_schedule(
    sid: str,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get payment schedule for a subscription."""
    result = await db.execute(select(Subscription).where(Subscription.sid == sid))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    sched_result = await db.execute(
        select(PaymentSchedule)
        .where(PaymentSchedule.subscription_id == sub.id)
        .order_by(PaymentSchedule.week_number)
    )
    schedules = list(sched_result.scalars().all())

    return {
        "success": True,
        "data": [ScheduleItemResponse.model_validate(s).model_dump() for s in schedules],
        "message": f"{len(schedules)} schedule item(s).",
    }


@router.get("/{sid}/transactions")
async def get_subscription_transactions(
    sid: str,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get wallet transactions related to a subscription."""
    result = await db.execute(select(Subscription).where(Subscription.sid == sid))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Find transactions whose description references this SID
    txn_result = await db.execute(
        select(WalletTransaction)
        .where(
            WalletTransaction.user_id == sub.user_id,
            WalletTransaction.description.ilike(f"%{sub.sid}%"),
        )
        .order_by(WalletTransaction.created_at.desc())
    )
    txns = list(txn_result.scalars().all())

    return {
        "success": True,
        "data": [
            {
                "id": str(t.id),
                "txn_id": t.txn_id,
                "amount": str(t.amount),
                "type": t.type.value,
                "category": t.category.value,
                "reference": t.reference,
                "description": t.description,
                "status": t.status.value,
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "message": f"{len(txns)} transaction(s) found.",
    }
