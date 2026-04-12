"""Plan business logic — seeding, listing, CRUD."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import BonusType, PenaltyType, PlanStatus, SavingsPlan
from app.schemas.plan import PlanCreateRequest, PlanUpdateRequest
from app.utils.codes import generate_plan_code


# ---------------------------------------------------------------------------
# Seeding (runs on startup)
# ---------------------------------------------------------------------------
async def seed_default_plans(db: AsyncSession) -> None:
    """Seed Prime 6 and Prime 13 plans if no plans exist. Runs once."""
    result = await db.execute(select(SavingsPlan).limit(1))
    if result.scalar_one_or_none():
        return

    plans = [
        SavingsPlan(
            code="PRIME-6",
            name="Prime 6",
            description=(
                "6-week savings cycle. Save ₦3,500 weekly and earn returns at maturity. "
                "Your referral code becomes available in week 2."
            ),
            weekly_amount=Decimal("3500.00"),
            duration_weeks=6,
            registration_fee=Decimal("2000.00"),
            clearance_fee=Decimal("2000.00"),
            return_rate=Decimal("0.00"),
            penalty_type=PenaltyType.FIXED,
            penalty_value=Decimal("3500.00"),
            minimum_wallet_balance=Decimal("5500.00"),
            max_subscribers=None,
            referral_code_release_week=2,
            referral_code_validity_weeks=1,
            downline_qualification_week=4,
            referral_bonus_type=BonusType.FIXED,
            referral_bonus_value=Decimal("0.00"),
            referral_required_for_payout=False,
            is_seeded=True,
        ),
        SavingsPlan(
            code="PRIME-13",
            name="Prime 13",
            description=(
                "13-week savings cycle. Save ₦3,500 weekly and earn returns at maturity. "
                "Your referral code becomes available in week 4."
            ),
            weekly_amount=Decimal("3500.00"),
            duration_weeks=13,
            registration_fee=Decimal("2000.00"),
            clearance_fee=Decimal("2000.00"),
            return_rate=Decimal("0.00"),
            penalty_type=PenaltyType.FIXED,
            penalty_value=Decimal("3500.00"),
            minimum_wallet_balance=Decimal("5500.00"),
            max_subscribers=None,
            referral_code_release_week=4,
            referral_code_validity_weeks=2,
            downline_qualification_week=6,
            referral_bonus_type=BonusType.FIXED,
            referral_bonus_value=Decimal("0.00"),
            referral_required_for_payout=False,
            is_seeded=True,
        ),
    ]

    db.add_all(plans)
    await db.commit()
    print("[SEED] Prime 6 and Prime 13 savings plans created.")


# ---------------------------------------------------------------------------
# Public queries
# ---------------------------------------------------------------------------
async def list_plans(db: AsyncSession) -> list[SavingsPlan]:
    """List all active savings plans."""
    result = await db.execute(
        select(SavingsPlan)
        .where(SavingsPlan.status == PlanStatus.ACTIVE)
        .order_by(SavingsPlan.weekly_amount)
    )
    return list(result.scalars().all())


async def get_plan_by_code(code: str, db: AsyncSession) -> SavingsPlan:
    """Get a single plan by its code."""
    result = await db.execute(select(SavingsPlan).where(SavingsPlan.code == code))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan with code '{code}' not found",
        )
    return plan


# ---------------------------------------------------------------------------
# Admin operations
# ---------------------------------------------------------------------------
async def create_plan(data: PlanCreateRequest, admin_id, db: AsyncSession) -> SavingsPlan:
    """Admin creates a new savings plan."""
    code = generate_plan_code()

    # Check for duplicate code (unlikely but safe)
    existing = await db.execute(select(SavingsPlan).where(SavingsPlan.code == code))
    if existing.scalar_one_or_none():
        code = generate_plan_code()

    plan = SavingsPlan(
        code=code,
        name=data.name,
        description=data.description,
        weekly_amount=data.weekly_amount,
        duration_weeks=data.duration_weeks,
        registration_fee=data.registration_fee,
        clearance_fee=data.clearance_fee,
        return_rate=data.return_rate,
        penalty_type=PenaltyType(data.penalty_type),
        penalty_value=data.penalty_value,
        minimum_wallet_balance=data.minimum_wallet_balance,
        max_subscribers=data.max_subscribers,
        referral_code_release_week=data.referral_code_release_week,
        referral_code_validity_weeks=data.referral_code_validity_weeks,
        downline_qualification_week=data.downline_qualification_week,
        referral_bonus_type=BonusType(data.referral_bonus_type),
        referral_bonus_value=data.referral_bonus_value,
        referral_required_for_payout=data.referral_required_for_payout,
        created_by=admin_id,
    )
    db.add(plan)
    return plan


async def update_plan(code: str, data: PlanUpdateRequest, db: AsyncSession) -> SavingsPlan:
    """Admin updates an existing plan."""
    plan = await get_plan_by_code(code, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "penalty_type" and value is not None:
            value = PenaltyType(value)
        elif field == "referral_bonus_type" and value is not None:
            value = BonusType(value)
        elif field == "status" and value is not None:
            value = PlanStatus(value)
        setattr(plan, field, value)

    await db.commit()
    await db.refresh(plan)

    return plan
