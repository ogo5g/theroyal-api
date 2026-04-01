"""Admin — Clearance (approve/reject payouts)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.services import audit as audit_service
from app.services import clearance as clearance_service
from app.services import notifications as notif_service

router = APIRouter(prefix="/clearance", tags=["Admin — Clearance"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.post("/{sid}/approve")
async def approve_clearance(
    sid: str,
    admin: Annotated[User, Depends(admin_dep)],
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

    await notif_service.notify_payout_processed(
        user_id=None,  # Will be set by the service  
        sid=sid,
        amount=result["settlement_amount"],
        db=db,
    )

    return {
        "success": True,
        "data": result,
        "message": f"Payout of ₦{result['settlement_amount']} initiated for {sid}.",
    }


@router.post("/{sid}/reject")
async def reject_clearance(
    sid: str,
    data: dict,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Reject a clearance request."""
    from sqlalchemy import select
    from app.models.subscription import Subscription

    result = await db.execute(select(Subscription).where(Subscription.sid == sid))
    sub = result.scalar_one_or_none()
    if not sub:
        return {"success": False, "error": "not_found", "message": "Subscription not found"}

    reason = data.get("reason", "No reason provided")

    await audit_service.log_action(
        actor_id=admin.id,
        action="clearance.rejected",
        target_type="Subscription",
        target_id=sub.id,
        db=db,
        metadata={"reason": reason},
        request=request,
    )

    return {
        "success": True,
        "data": {"sid": sid, "reason": reason},
        "message": "Clearance rejected.",
    }
