"""Subscription business logic — create, list, pay, penalty."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.plan import BonusType, PlanStatus, SavingsPlan
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
# Validate Referral Codes (batch)
# ---------------------------------------------------------------------------
async def validate_referral_codes(
    codes: list[str],
    db: AsyncSession,
) -> list[dict]:
    """Batch-validate a list of referral codes. Returns validation results."""
    if not codes:
        return []

    today = date.today()

    # Fetch all matching subscriptions in one query
    result = await db.execute(
        select(Subscription).where(
            Subscription.referral_code.in_(codes),
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED]),
        )
    )
    found: dict[str, Subscription] = {s.referral_code: s for s in result.scalars().all()}

    results = []
    for code in codes:
        sub = found.get(code)
        if not sub:
            results.append({"code": code, "valid": False, "error": "Referral code not found or inactive"})
            continue
        if sub.referral_code_available_at and today < sub.referral_code_available_at:
            results.append({"code": code, "valid": False, "error": "Referral code is not yet active"})
            continue
        if sub.referral_code_expires_at and today > sub.referral_code_expires_at:
            results.append({"code": code, "valid": False, "error": "Referral code has expired"})
            continue
        results.append({"code": code, "valid": True, "error": None})

    return results


# ---------------------------------------------------------------------------
# Create Batch Subscriptions
# ---------------------------------------------------------------------------
async def create_batch_subscriptions(
    user,
    plan_code: str,
    quantity: int,
    referral_codes: list[str],
    db: AsyncSession,
) -> dict:
    """Create N subscriptions atomically including first installment payment."""
    today = date.today()

    # 1. Lock plan row to prevent race conditions on subscriber count
    plan_result = await db.execute(
        select(SavingsPlan).where(SavingsPlan.code == plan_code).with_for_update()
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    if plan.status != PlanStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is not active")
    if plan.max_subscribers and (plan.current_subscribers + quantity) > plan.max_subscribers:
        spots_left = plan.max_subscribers - plan.current_subscribers
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan only has {spots_left} spot(s) left. Requested: {quantity}",
        )

    # 2. Lock account row to prevent balance race conditions
    acct_result = await db.execute(
        select(Account).where(Account.user_id == user.id).with_for_update()
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if not account.wallet_activated and not account.wallet_bypass:
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

    # 3. Pre-validate all referral codes before any mutation
    # Pad or trim codes list to match quantity
    padded_codes: list[str | None] = list(referral_codes[:quantity])
    while len(padded_codes) < quantity:
        padded_codes.append(None)

    non_null_codes = [c for c in padded_codes if c]
    upline_map: dict[str, Subscription | None] = {}

    if non_null_codes:
        ref_result = await db.execute(
            select(Subscription).where(
                Subscription.referral_code.in_(non_null_codes),
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED]),
            )
        )
        found_subs: dict[str, Subscription] = {s.referral_code: s for s in ref_result.scalars().all()}

        for code in non_null_codes:
            sub = found_subs.get(code)
            if not sub:
                upline_map[code] = None  # invalid but we won't error, just skip
                continue
            if sub.referral_code_available_at and today < sub.referral_code_available_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Referral code '{code}' is not yet active",
                )
            if sub.referral_code_expires_at and today > sub.referral_code_expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Referral code '{code}' has expired",
                )
            upline_map[code] = sub

    # 4. Debit wallet — two transactions: registration fees + first installments
    total_reg = plan.registration_fee * quantity
    total_installment = plan.weekly_amount * quantity

    reg_ref = generate_payment_reference()
    await wallet_service.debit_wallet(
        user_id=user.id,
        amount=total_reg,
        category=TransactionCategory.REGISTRATION_FEE,
        reference=reg_ref,
        description=f"Registration fee for {quantity}x {plan.name} (₦{plan.registration_fee:,.2f} each)",
        db=db,
    )

    inst_ref = generate_payment_reference()
    installment_txn = await wallet_service.debit_wallet(
        user_id=user.id,
        amount=total_installment,
        category=TransactionCategory.PLAN_INSTALLMENT,
        reference=inst_ref,
        description=f"First installment for {quantity}x {plan.name} (₦{plan.weekly_amount:,.2f} each)",
        db=db,
    )

    # 5. Calculate shared date/amount values (all subs share the same start date)
    start_date = today + timedelta(days=(7 - today.weekday()) % 7 or 7)  # Next Monday
    end_date = start_date + timedelta(weeks=plan.duration_weeks)
    total_expected = plan.weekly_amount * plan.duration_weeks
    settlement_amount = total_expected * (1 + plan.return_rate / 100)
    referral_code_available_at = start_date + timedelta(weeks=plan.referral_code_release_week - 1)
    referral_code_expires_at = referral_code_available_at + timedelta(weeks=plan.referral_code_validity_weeks)

    # Week 2 due date for next_due_date
    week2_date = start_date + timedelta(weeks=1) if plan.duration_weeks > 1 else None

    # 6. Create N subscriptions
    created_subs = []
    for i in range(quantity):
        ref_code = padded_codes[i]
        upline_sub = upline_map.get(ref_code) if ref_code else None

        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            weekly_amount=plan.weekly_amount,
            total_expected=total_expected,
            settlement_amount=settlement_amount,
            start_date=start_date,
            end_date=end_date,
            next_due_date=week2_date,
            referral_code_available_at=referral_code_available_at,
            referral_code_expires_at=referral_code_expires_at,
            referred_by_code=ref_code,
            upline_subscription_id=upline_sub.id if upline_sub else None,
            commission_paid=True,
            # First week already paid
            total_paid=plan.weekly_amount,
            weeks_paid=1,
            current_streak=1,
            longest_streak=1,
            last_payment_date=today,
        )
        db.add(sub)
        await db.flush()  # Get sub.id for schedule FK

        # Generate payment schedule
        for week in range(1, plan.duration_weeks + 1):
            due = start_date + timedelta(weeks=week - 1)
            schedule = PaymentSchedule(
                subscription_id=sub.id,
                week_number=week,
                due_date=due,
                amount=plan.weekly_amount,
            )
            if week == 1:
                schedule.status = ScheduleStatus.PAID
                schedule.paid_at = datetime.now(timezone.utc)
                schedule.transaction_id = installment_txn.id
            db.add(schedule)

        created_subs.append(sub)

    # 7. Increment subscriber count
    plan.current_subscribers += quantity

    total_debited = total_reg + total_installment
    return {
        "subscriptions": created_subs,
        "total_debited": total_debited,
        "quantity": quantity,
    }


# ---------------------------------------------------------------------------
# Create Subscription
# ---------------------------------------------------------------------------
async def create_subscription(
    user,
    plan_code: str,
    referral_code: str | None,
    db: AsyncSession,
) -> Subscription:
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

    if not account.wallet_activated and not account.wallet_bypass:
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

    # 3. Debit registration fee
    reg_ref = generate_payment_reference()
    await wallet_service.debit_wallet(
        user_id=user.id,
        amount=plan.registration_fee,
        category=TransactionCategory.REGISTRATION_FEE,
        reference=reg_ref,
        description=f"Registration fee for {plan.name} (₦{plan.registration_fee:,.2f})",
        db=db,
    )

    # 4. Calculate dates and amounts
    today = date.today()
    start_date = today + timedelta(days=(7 - today.weekday()) % 7 or 7)  # Next Monday
    end_date = start_date + timedelta(weeks=plan.duration_weeks)
    total_expected = plan.weekly_amount * plan.duration_weeks
    settlement_amount = total_expected * (1 + plan.return_rate / 100)

    # 5. Compute referral code availability window
    referral_code_available_at = start_date + timedelta(weeks=plan.referral_code_release_week - 1)
    referral_code_expires_at = referral_code_available_at + timedelta(weeks=plan.referral_code_validity_weeks)

    # 6. Handle referral — validate timing and link upline
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
            today_check = date.today()
            if (
                upline_sub.referral_code_available_at
                and today_check < upline_sub.referral_code_available_at
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This referral code is not yet active",
                )
            if (
                upline_sub.referral_code_expires_at
                and today_check > upline_sub.referral_code_expires_at
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This referral code has expired",
                )
            upline_sub_id = upline_sub.id

    # 7. Create subscription
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
        referral_code_available_at=referral_code_available_at,
        referral_code_expires_at=referral_code_expires_at,
        referred_by_code=referral_code,
        upline_subscription_id=upline_sub_id,
        commission_paid=True,
    )
    db.add(subscription)
    await db.flush()

    # 8. Generate payment schedule
    for week in range(1, plan.duration_weeks + 1):
        due = start_date + timedelta(weeks=week - 1)
        schedule = PaymentSchedule(
            subscription_id=subscription.id,
            week_number=week,
            due_date=due,
            amount=plan.weekly_amount,
        )
        db.add(schedule)

    # 9. Increment subscriber count
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
    """Pay the next pending installment."""
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

    # Trigger upline referral bonus if downline hits qualification week
    await _maybe_credit_upline_bonus(sub, db)

    return {
        "subscription": sub,
        "schedule": schedule,
        "transaction": txn,
    }


async def _maybe_credit_upline_bonus(sub: Subscription, db: AsyncSession) -> None:
    """Credit the upline's referral bonus when this subscription reaches the qualification week."""
    if not sub.upline_subscription_id:
        return

    # Load the plan to get the qualification week and bonus settings
    plan_result = await db.execute(
        select(SavingsPlan).where(SavingsPlan.id == sub.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if not plan or sub.weeks_paid != plan.downline_qualification_week:
        return

    upline_result = await db.execute(
        select(Subscription).where(Subscription.id == sub.upline_subscription_id)
    )
    upline_sub = upline_result.scalar_one_or_none()
    if not upline_sub or upline_sub.status not in (
        SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED
    ):
        return

    if plan.referral_bonus_type == BonusType.FIXED:
        bonus = plan.referral_bonus_value
    else:
        # Percentage of the downline's total plan value
        bonus = sub.total_expected * (plan.referral_bonus_value / Decimal("100"))

    if bonus <= Decimal("0"):
        return

    bonus_ref = generate_payment_reference()
    await wallet_service.credit_wallet(
        user_id=upline_sub.user_id,
        amount=bonus,
        category=TransactionCategory.REFERRAL_BONUS,
        reference=bonus_ref,
        description=f"Referral bonus: {sub.sid} reached week {plan.downline_qualification_week}",
        db=db,
    )


# ---------------------------------------------------------------------------
# Pay Penalty
# ---------------------------------------------------------------------------
async def pay_penalty(user, sid: str, db: AsyncSession) -> dict:
    """Pay penalty to reactivate a defaulted subscription."""
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

    from app.models.plan import PenaltyType
    if plan.penalty_type == PenaltyType.FIXED:
        penalty_amount = plan.penalty_value
    else:
        penalty_amount = sub.weekly_amount * (plan.penalty_value / Decimal("100"))

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
