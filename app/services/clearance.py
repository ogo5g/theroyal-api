"""Clearance business logic — completion check + payout."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kyc import KYC, KYCStatus
from app.models.plan import SavingsPlan
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.wallet import TransactionCategory
from app.services import wallet as wallet_service
from app.services.payments.platnova import platnova
from app.utils.codes import generate_payment_reference
from app.utils.security import decrypt_field


# ---------------------------------------------------------------------------
# Check completion
# ---------------------------------------------------------------------------
async def check_subscription_completed(sub: Subscription, db: AsyncSession) -> bool:
    """Check if a subscription has been fully paid and mark as completed."""
    plan_result = await db.execute(select(SavingsPlan).where(SavingsPlan.id == sub.plan_id))
    plan = plan_result.scalar_one_or_none()

    if not plan:
        return False

    if sub.weeks_paid >= plan.duration_weeks and sub.status == SubscriptionStatus.ACTIVE:
        sub.status = SubscriptionStatus.COMPLETED
        return True

    return False


# ---------------------------------------------------------------------------
# Initiate Payout (admin approves clearance)
# ---------------------------------------------------------------------------
async def initiate_payout(
    admin_user,
    sid: str,
    db: AsyncSession,
) -> dict:
    """
    Admin approves payout for a completed subscription:
    1. Verify subscription is COMPLETED
    2. Load plan — check referral_required_for_payout if set
    3. Deduct clearance_fee if configured
    4. Get user's bank details from KYC
    5. Initiate Platnova transfer with net_payout
    6. Credit user wallet and mark SETTLED
    """
    result = await db.execute(select(Subscription).where(Subscription.sid == sid))
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    if sub.status != SubscriptionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subscription must be COMPLETED to initiate payout. Current: {sub.status.value}",
        )

    # Load plan for clearance fee and referral requirements
    plan_result = await db.execute(select(SavingsPlan).where(SavingsPlan.id == sub.plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    # Check referral requirement if configured
    if plan.referral_required_for_payout:
        downline_result = await db.execute(
            select(Subscription).where(
                Subscription.upline_subscription_id == sub.id,
                Subscription.weeks_paid >= plan.downline_qualification_week,
            )
        )
        qualifying_downline = downline_result.scalar_one_or_none()
        if not qualifying_downline:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Payout requires at least one downline who has reached "
                    f"week {plan.downline_qualification_week} of their cycle."
                ),
            )

    # Get KYC for bank details
    kyc_result = await db.execute(select(KYC).where(KYC.user_id == sub.user_id))
    kyc = kyc_result.scalar_one_or_none()

    if not kyc or kyc.status != KYCStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User's KYC must be approved before payout",
        )

    # Deduct clearance fee if applicable
    if plan.clearance_fee and plan.clearance_fee > Decimal("0"):
        clearance_ref = generate_payment_reference()
        await wallet_service.debit_wallet(
            user_id=sub.user_id,
            amount=plan.clearance_fee,
            category=TransactionCategory.CLEARANCE_FEE,
            reference=clearance_ref,
            description=f"Clearance fee for {sub.sid} (₦{plan.clearance_fee:,.2f})",
            db=db,
        )

    net_payout = sub.settlement_amount - (plan.clearance_fee or Decimal("0"))

    # Decrypt bank details
    account_number = decrypt_field(kyc.account_number)

    # Initiate transfer
    ref = generate_payment_reference()
    try:
        transfer = await platnova.initiate_transfer(
            amount=net_payout,
            bank_code=kyc.bank_code,
            account_number=account_number,
            account_name=kyc.account_name,
            narration=f"PrimeHC payout for {sub.sid}",
            reference=ref,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payout transfer failed: {str(e)}",
        )

    # Credit wallet (for record-keeping) and mark settled
    await wallet_service.credit_wallet(
        user_id=sub.user_id,
        amount=net_payout,
        category=TransactionCategory.PAYOUT,
        reference=ref,
        description=f"Payout for {sub.sid} — ₦{net_payout:,.2f}",
        db=db,
        provider_reference=transfer.get("provider_reference"),
    )

    sub.status = SubscriptionStatus.SETTLED

    return {
        "subscription_sid": sub.sid,
        "settlement_amount": str(sub.settlement_amount),
        "clearance_fee": str(plan.clearance_fee),
        "net_payout": str(net_payout),
        "transfer_reference": ref,
        "status": "settled",
    }
