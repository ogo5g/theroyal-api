"""Admin — Subscription management."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.subscription import Subscription
from app.models.user import User, UserRole
from app.schemas.subscription import SubscriptionResponse

router = APIRouter(prefix="/subscriptions", tags=["Admin — Subscriptions"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


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

    return {
        "success": True,
        "data": [SubscriptionResponse.model_validate(s).model_dump() for s in subs],
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
        return {"success": False, "error": "not_found", "message": "Subscription not found"}

    return {
        "success": True,
        "data": SubscriptionResponse.model_validate(sub).model_dump(),
        "message": "Subscription retrieved.",
    }
