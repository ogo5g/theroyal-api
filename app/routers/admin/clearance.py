"""Admin — Clearance (list, approve, reject payouts)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.schemas.subscription import SubscriptionResponse
from app.services import audit as audit_service
from app.services import clearance as clearance_service
from app.services import notifications as notif_service

router = APIRouter(prefix="/clearance", tags=["Admin — Clearance"])

# All 4 admin roles can view clearances
admin_all = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MODERATOR, UserRole.STAFF)
# Only senior roles can approve/reject
admin_senior = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.get("")
async def list_clearances(
    admin: Annotated[User, Depends(admin_all)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    """List all subscriptions that have been submitted for clearance."""
    query = select(Subscription).where(Subscription.clearance_submitted.is_(True))
    count_query = (
        select(func.count())
        .select_from(Subscription)
        .where(Subscription.clearance_submitted.is_(True))
    )

    if status:
        query = query.where(Subscription.status == status)
        count_query = count_query.where(Subscription.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Subscription.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    subs = result.scalars().all()

    data = []
    for s in subs:
        d = SubscriptionResponse.model_validate(s).model_dump()
        if s.plan:
            d["plan_code"] = s.plan.code
            d["plan_name"] = s.plan.name
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


@router.post("/{sid}/approve")
async def approve_clearance(
    sid: str,
    admin: Annotated[User, Depends(admin_senior)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Approve a completed subscription for payout."""
    result = await clearance_service.initiate_payout(admin, sid, db)

    await audit_service.log_action(
        actor_id=admin.id,
        action="clearance.approved",
        target_type="Subscription",
        target_id=result["subscription_sid"],
        db=db,
        metadata={"settlement_amount": result["settlement_amount"]},
        request=request,
    )

    await db.commit()

    return {
        "success": True,
        "data": result,
        "message": f"Payout of ₦{result['settlement_amount']} initiated for {sid}.",
    }


@router.post("/{sid}/reject")
async def reject_clearance(
    sid: str,
    data: dict,
    admin: Annotated[User, Depends(admin_senior)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Reject a clearance request. Resets submission flag so user can resubmit."""
    result = await db.execute(select(Subscription).where(Subscription.sid == sid))
    sub = result.scalar_one_or_none()
    if not sub:
        return {"success": False, "error": "not_found", "message": "Subscription not found"}

    reason = data.get("reason", "No reason provided")

    # Reset the submission flag so member can resubmit after resolving the issue
    sub.clearance_submitted = False

    await audit_service.log_action(
        actor_id=admin.id,
        action="clearance.rejected",
        target_type="Subscription",
        target_id=sub.id,
        db=db,
        metadata={"reason": reason},
        request=request,
    )

    await notif_service.notify_clearance_rejected(sub.user_id, sid, reason, db)

    await db.commit()

    return {
        "success": True,
        "data": {"sid": sid, "reason": reason},
        "message": "Clearance rejected.",
    }


@router.post("/{sid}/submit")
async def admin_submit_clearance(
    sid: str,
    admin: Annotated[User, Depends(admin_all)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Admin/moderator/staff submits clearance on behalf of a member."""
    sub = await clearance_service.submit_for_clearance(sid, admin, db, admin_mode=True)

    await audit_service.log_action(
        actor_id=admin.id,
        action="clearance.submitted",
        target_type="Subscription",
        target_id=sub.id,
        db=db,
        metadata={"sid": sid},
        request=request,
    )

    await notif_service.notify_clearance_submitted(sub.user_id, sid, db)
    await db.commit()

    return {
        "success": True,
        "data": {"sid": sid},
        "message": "Clearance submitted successfully.",
    }
