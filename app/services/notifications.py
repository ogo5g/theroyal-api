"""Notification service — create, list, mark read, trigger helpers."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationChannel, NotificationType


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def create_notification(
    user_id,
    title: str,
    body: str,
    notification_type: NotificationType,
    channel: NotificationChannel,
    db: AsyncSession,
) -> Notification:
    """Create an in-app notification record."""
    notif = Notification(
        user_id=user_id,
        title=title,
        body=body,
        type=notification_type,
        channel=channel,
    )
    db.add(notif)
    return notif


async def list_notifications(
    user,
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    unread_only: bool = False,
) -> dict:
    """Get paginated notifications for a user."""
    query = select(Notification).where(Notification.user_id == user.id)
    count_query = select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id
    )

    if unread_only:
        query = query.where(Notification.is_read == False)
        count_query = count_query.where(Notification.is_read == False)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Notification.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    notifications = result.scalars().all()

    return {
        "items": list(notifications),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


async def mark_read(user, notification_id, db: AsyncSession) -> Notification:
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    return notif


async def mark_all_read(user, db: AsyncSession) -> int:
    """Mark all notifications as read for a user."""
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    return result.rowcount


# ---------------------------------------------------------------------------
# Trigger helpers — called from other services
# ---------------------------------------------------------------------------
async def notify_registration_success(user_id, email: str, db: AsyncSession):
    """Registration success — in-app."""
    await create_notification(
        user_id=user_id,
        title="Welcome to TheRoyalSaving!",
        body="Your account has been created successfully. Complete your onboarding to get started.",
        notification_type=NotificationType.SUCCESS,
        channel=NotificationChannel.IN_APP,
        db=db,
    )
    # TODO: Enqueue email via RQ (send_notification_email)


async def notify_kyc_approved(user_id, db: AsyncSession):
    """KYC approved — email + in-app."""
    await create_notification(
        user_id=user_id,
        title="KYC Approved ✓",
        body="Your identity verification has been approved. You can now subscribe to savings plans.",
        notification_type=NotificationType.SUCCESS,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_kyc_rejected(user_id, reason: str, db: AsyncSession):
    """KYC rejected — email + in-app."""
    await create_notification(
        user_id=user_id,
        title="KYC Review Update",
        body=f"Your identity verification was not approved. Reason: {reason}. Please resubmit.",
        notification_type=NotificationType.ACTION_REQUIRED,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_wallet_funded(user_id, amount, db: AsyncSession):
    """Wallet funded — in-app + email."""
    await create_notification(
        user_id=user_id,
        title="Wallet Funded",
        body=f"Your wallet has been credited with ₦{amount:,.2f}.",
        notification_type=NotificationType.SUCCESS,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_payment_confirmed(user_id, week_number: int, sid: str, db: AsyncSession):
    """Payment confirmed — in-app only."""
    await create_notification(
        user_id=user_id,
        title="Payment Confirmed",
        body=f"Week {week_number} installment for subscription {sid} has been recorded.",
        notification_type=NotificationType.SUCCESS,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_payment_due(user_id, sid: str, due_date: str, db: AsyncSession):
    """Payment due in 3 days — SMS + in-app."""
    await create_notification(
        user_id=user_id,
        title="Payment Reminder",
        body=f"Your next installment for {sid} is due on {due_date}. Please ensure your wallet has sufficient funds.",
        notification_type=NotificationType.WARNING,
        channel=NotificationChannel.IN_APP,
        db=db,
    )
    # TODO: Enqueue SMS via RQ


async def notify_plan_defaulted(user_id, sid: str, db: AsyncSession):
    """Plan defaulted — SMS + email + in-app."""
    await create_notification(
        user_id=user_id,
        title="Subscription Defaulted",
        body=f"Your subscription {sid} has been marked as defaulted due to missed payments. Pay the penalty to reactivate.",
        notification_type=NotificationType.ACTION_REQUIRED,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_penalty_paid(user_id, sid: str, db: AsyncSession):
    """Penalty paid, plan reactivated — in-app."""
    await create_notification(
        user_id=user_id,
        title="Subscription Reactivated",
        body=f"Your penalty for {sid} has been paid. Your subscription is now active again.",
        notification_type=NotificationType.SUCCESS,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_plan_maturing(user_id, sid: str, end_date: str, db: AsyncSession):
    """Plan maturing in 7 days — email + in-app."""
    await create_notification(
        user_id=user_id,
        title="Savings Plan Maturing Soon!",
        body=f"Your subscription {sid} will mature on {end_date}. Your payout will be processed after admin clearance.",
        notification_type=NotificationType.INFO,
        channel=NotificationChannel.IN_APP,
        db=db,
    )


async def notify_payout_processed(user_id, sid: str, amount, db: AsyncSession):
    """Payout processed — SMS + email + in-app."""
    await create_notification(
        user_id=user_id,
        title="Payout Processed! 🎉",
        body=f"Your savings payout of ₦{amount:,.2f} for {sid} has been transferred to your bank account.",
        notification_type=NotificationType.SUCCESS,
        channel=NotificationChannel.IN_APP,
        db=db,
    )
