"""Subscription business logic — create, list, pay, penalty."""

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.plan import PlanStatus, SavingsPlan
from app.models.subscription import (
    PaymentSchedule,
    ScheduleStatus,
    Subscription,
    SubscriptionStatus,
)
from app.models.wallet import TransactionCategory
from app.services import wallet as wallet_service
from app.utils.codes import generate_payment_reference


# ---------------------------------------------------------------------------
# Create Subscription
# ---------------------------------------------------------------------------
async def create_subscription(
    user,
    plan_code: str,
    referral_code: str | None,
    db: AsyncSession,
) -> Subscription:
    """
    Create a new subscription:
    1. Validate plan is active and not full
    2. Check wallet >= minimum_wallet_balance
    3. Debit start_commission from wallet
    4. Create Subscription (ACTIVE)
    5. Generate payment schedule rows
    6. Increment plan.current_subscribers
    7. Link referral if provided
    """
    # 1. Get plan
    result = await db.execute(
        select(SavingsPlan).where(SavingsPlan.code == plan_code)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    if plan.status != PlanStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is not active")

    if plan.max_subscribers and plan.current_subscribers >= plan.max_subscribers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is full")

    # 2. Check wallet balance
    acct_result = await db.execute(select(Account).where(Account.user_id == user.id))
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if not account.wallet_activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please activate your wallet first",
        )

    if account.wallet_balance < plan.minimum_wallet_balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum wallet balance of ₦{plan.minimum_wallet_balance:,.2f} required. "
                   f"Your balance: ₦{account.wallet_balance:,.2f}",
        )

    # 3. Debit commission
    commission_ref = generate_payment_reference()
    await wallet_service.debit_wallet(
        user_id=user.id,
        amount=plan.start_commission,
        category=TransactionCategory.PLAN_COMMISSION,
        reference=commission_ref,
        description=f"Start commission for {plan.name} plan (₦{plan.start_commission:,.2f})",
        db=db,
    )

    # 4. Calculate dates and amounts
    today = date.today()
    start_date = today + timedelta(days=(7 - today.weekday()) % 7 or 7)  # Next Monday
    end_date = start_date + timedelta(weeks=plan.duration_weeks)
    total_expected = plan.weekly_amount * plan.duration_weeks
    settlement_amount = total_expected * (1 + plan.return_rate / 100)

    # 5. Handle referral
    upline_sub_id = None
    if referral_code:
        ref_result = await db.execute(
            select(Subscription).where(
                Subscription.referral_code == referral_code,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED]),
            )
        )
        upline_sub = ref_result.scalar_one_or_none()
        if upline_sub:
            upline_sub_id = upline_sub.id

    # 6. Create subscription
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        weekly_amount=plan.weekly_amount,
        total_expected=total_expected,
        settlement_amount=settlement_amount,
        start_date=start_date,
        end_date=end_date,
        next_due_date=start_date,
        referred_by_code=referral_code,
        upline_subscription_id=upline_sub_id,
        commission_paid=True,
    )
    db.add(subscription)
    await db.flush()

    # 7. Generate payment schedule
    for week in range(1, plan.duration_weeks + 1):
        due = start_date + timedelta(weeks=week - 1)
        schedule = PaymentSchedule(
            subscription_id=subscription.id,
            week_number=week,
            due_date=due,
            amount=plan.weekly_amount,
        )
        db.add(schedule)

    # 8. Increment subscriber count
    plan.current_subscribers += 1

    return subscription


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------
async def list_subscriptions(user, db: AsyncSession) -> list[Subscription]:
    """List all subscriptions for a user."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    return list(result.scalars().all())


async def get_subscription(user, sid: str, db: AsyncSession) -> Subscription:
    """Get a single subscription by SID."""
    result = await db.execute(
        select(Subscription).where(Subscription.sid == sid, Subscription.user_id == user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return sub


async def get_schedule(user, sid: str, db: AsyncSession) -> list[PaymentSchedule]:
    """Get the payment schedule for a subscription."""
    sub = await get_subscription(user, sid, db)
    result = await db.execute(
        select(PaymentSchedule)
        .where(PaymentSchedule.subscription_id == sub.id)
        .order_by(PaymentSchedule.week_number)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Pay Installment
# ---------------------------------------------------------------------------
async def pay_installment(user, sid: str, db: AsyncSession) -> dict:
    """
    Pay the next pending installment:
    1. Find next PENDING schedule row
    2. Debit weekly_amount from wallet
    3. Mark schedule as PAID
    4. Update subscription totals
    """
    sub = await get_subscription(user, sid, db)

    if sub.status not in (SubscriptionStatus.ACTIVE,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pay installment on a {sub.status.value} subscription",
        )

    # Find next pending schedule
    result = await db.execute(
        select(PaymentSchedule)
        .where(
            PaymentSchedule.subscription_id == sub.id,
            PaymentSchedule.status == ScheduleStatus.PENDING,
        )
        .order_by(PaymentSchedule.week_number)
        .limit(1)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending payments. All installments may already be paid.",
        )

    # Debit wallet
    ref = generate_payment_reference()
    txn = await wallet_service.debit_wallet(
        user_id=user.id,
        amount=schedule.amount,
        category=TransactionCategory.PLAN_INSTALLMENT,
        reference=ref,
        description=f"Week {schedule.week_number} installment for {sub.sid}",
        db=db,
    )

    # Update schedule
    schedule.status = ScheduleStatus.PAID
    schedule.paid_at = datetime.now(timezone.utc)
    schedule.transaction_id = txn.id

    # Update subscription
    sub.total_paid += schedule.amount
    sub.weeks_paid += 1
    sub.current_streak += 1
    sub.longest_streak = max(sub.longest_streak, sub.current_streak)
    sub.last_payment_date = date.today()

    # Calculate next due date
    next_result = await db.execute(
        select(PaymentSchedule)
        .where(
            PaymentSchedule.subscription_id == sub.id,
            PaymentSchedule.status == ScheduleStatus.PENDING,
        )
        .order_by(PaymentSchedule.week_number)
        .limit(1)
    )
    next_schedule = next_result.scalar_one_or_none()
    sub.next_due_date = next_schedule.due_date if next_schedule else None

    # Check if subscription is now completed
    if sub.weeks_paid >= sub.total_expected / sub.weekly_amount:
        sub.status = SubscriptionStatus.COMPLETED

    return {
        "subscription": sub,
        "schedule": schedule,
        "transaction": txn,
    }


# ---------------------------------------------------------------------------
# Pay Penalty
# ---------------------------------------------------------------------------
async def pay_penalty(user, sid: str, db: AsyncSession) -> dict:
    """
    Pay penalty to reactivate a defaulted subscription:
    1. Validate subscription is DEFAULTED
    2. Calculate penalty amount
    3. Debit from wallet
    4. Reset status to ACTIVE, reset streak
    """
    sub = await get_subscription(user, sid, db)

    if sub.status != SubscriptionStatus.DEFAULTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is not in defaulted state",
        )

    # Get plan for penalty calculation
    plan_result = await db.execute(
        select(SavingsPlan).where(SavingsPlan.id == sub.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    # Calculate penalty
    from app.models.plan import PenaltyType
    if plan.penalty_type == PenaltyType.FIXED:
        penalty_amount = plan.penalty_value
    else:
        penalty_amount = sub.weekly_amount * (plan.penalty_value / 100)

    # Debit penalty
    ref = generate_payment_reference()
    txn = await wallet_service.debit_wallet(
        user_id=user.id,
        amount=penalty_amount,
        category=TransactionCategory.PENALTY_FEE,
        reference=ref,
        description=f"Penalty fee for {sub.sid} — ₦{penalty_amount:,.2f}",
        db=db,
    )

    # Reactivate
    sub.status = SubscriptionStatus.ACTIVE
    sub.current_streak = 0
    sub.penalty_count += 1

    return {
        "subscription": sub,
        "penalty_amount": penalty_amount,
        "transaction": txn,
    }
