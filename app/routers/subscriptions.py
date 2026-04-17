"""Subscriptions router — create, list, pay, penalty, referral."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User
from app.schemas.subscription import (
    BatchSubscribeRequest,
    DownlineStatusResponse,
    ReferralInfoResponse,
    ScheduleItemResponse,
    SubscriptionResponse,
    ValidateReferralCodesRequest,
)
from app.services import subscriptions as sub_service
from app.services import clearance as clearance_service
from app.services import notifications as notif_service

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.post("")
async def create_subscription(
    data: dict,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sub = await sub_service.create_subscription(
        user=current_user,
        plan_code=data.get("plan_code", ""),
        referral_code=data.get("referral_code"),
        db=db,
    )
    await db.commit()
    await db.refresh(sub)
    return {
        "success": True,
        "data": _sub_to_response(sub),
        "message": "Subscription created successfully. Registration fee deducted.",
    }


@router.get("")
async def list_subscriptions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    subs = await sub_service.list_subscriptions(current_user, db)
    return {
        "success": True,
        "data": [_sub_to_response(s) for s in subs],
        "message": f"{len(subs)} subscription(s) found.",
    }


@router.post("/batch")
async def create_batch_subscription(
    data: BatchSubscribeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create N subscriptions atomically. First installment included in debit."""
    result = await sub_service.create_batch_subscriptions(
        user=current_user,
        plan_code=data.plan_code,
        quantity=data.quantity,
        referral_codes=data.referral_codes,
        db=db,
    )
    await db.commit()
    for sub in result["subscriptions"]:
        await db.refresh(sub)
    return {
        "success": True,
        "data": {
            "subscriptions": [_sub_to_response(s) for s in result["subscriptions"]],
            "total_debited": str(result["total_debited"]),
            "quantity": result["quantity"],
        },
        "message": f"{result['quantity']} subscription(s) created successfully. First installment(s) paid.",
    }


@router.post("/validate-referral-codes")
async def validate_referral_codes_endpoint(
    data: ValidateReferralCodesRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Validate a list of referral codes. Returns per-code validation results."""
    results = await sub_service.validate_referral_codes(data.referral_codes, db)
    return {
        "success": True,
        "data": results,
    }


@router.get("/{sid}/referral")
async def get_referral_info(
    sid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sub = await sub_service.get_subscription(current_user, sid, db)
    today = date.today()

    is_active = (
        sub.referral_code_available_at is not None
        and sub.referral_code_expires_at is not None
        and sub.referral_code_available_at <= today <= sub.referral_code_expires_at
    )

    # Load downlines and their plan's qualification week
    downlines_result = await db.execute(
        select(Subscription).where(Subscription.upline_subscription_id == sub.id)
    )
    downline_subs = list(downlines_result.scalars().all())

    qualification_week = 1
    if sub.plan:
        qualification_week = sub.plan.downline_qualification_week

    downlines = [
        DownlineStatusResponse(
            sid=dl.sid,
            weeks_paid=dl.weeks_paid,
            qualification_week=qualification_week,
            is_qualified=dl.weeks_paid >= qualification_week,
            status=dl.status.value,
        )
        for dl in downline_subs
    ]

    info = ReferralInfoResponse(
        referral_code=sub.referral_code if is_active else None,
        available_at=sub.referral_code_available_at,
        expires_at=sub.referral_code_expires_at,
        is_active=is_active,
        downlines=downlines,
    )

    return {
        "success": True,
        "data": info.model_dump(),
        "message": "Referral info retrieved.",
    }


@router.get("/{sid}")
async def get_subscription(
    sid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sub = await sub_service.get_subscription(current_user, sid, db)
    return {
        "success": True,
        "data": _sub_to_response(sub),
        "message": "Subscription retrieved.",
    }


@router.get("/{sid}/schedule")
async def get_schedule(
    sid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    schedules = await sub_service.get_schedule(current_user, sid, db)
    return {
        "success": True,
        "data": [ScheduleItemResponse.model_validate(s).model_dump() for s in schedules],
        "message": f"{len(schedules)} schedule item(s).",
    }


@router.post("/{sid}/pay")
async def pay_installment(
    sid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await sub_service.pay_installment(current_user, sid, db)
    sub = result["subscription"]
    schedule = result["schedule"]
    await db.commit()
    await db.refresh(sub)
    return {
        "success": True,
        "data": {
            "subscription": _sub_to_response(sub),
            "week_paid": schedule.week_number,
            "amount": str(schedule.amount),
        },
        "message": f"Week {schedule.week_number} installment paid successfully.",
    }


@router.post("/{sid}/submit-clearance")
async def submit_clearance(
    sid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Member submits their completed subscription for clearance review."""
    sub = await clearance_service.submit_for_clearance(sid, current_user, db, admin_mode=False)
    await notif_service.notify_clearance_submitted(current_user.id, sid, db)
    await db.commit()
    return {
        "success": True,
        "data": {"sid": sid},
        "message": "Clearance submitted successfully. Pending admin review.",
    }


@router.post("/{sid}/pay-penalty")
async def pay_penalty(
    sid: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await sub_service.pay_penalty(current_user, sid, db)
    sub = result["subscription"]
    await db.commit()
    await db.refresh(sub)
    return {
        "success": True,
        "data": {
            "subscription": _sub_to_response(sub),
            "penalty_amount": str(result["penalty_amount"]),
        },
        "message": "Penalty paid. Subscription reactivated.",
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _sub_to_response(sub) -> dict:
    """Convert subscription ORM to response dict, including referral active state."""
    today = date.today()
    is_active = (
        sub.referral_code_available_at is not None
        and sub.referral_code_expires_at is not None
        and sub.referral_code_available_at <= today <= sub.referral_code_expires_at
    )
    data = SubscriptionResponse.model_validate(sub).model_dump()
    data["is_referral_code_active"] = is_active
    # Only expose the referral code when the window is open
    data["referral_code"] = sub.referral_code if is_active else None
    if sub.plan:
        data["plan_code"] = sub.plan.code
        data["plan_name"] = sub.plan.name
    return data
