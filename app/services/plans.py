"""Plan business logic — seeding, listing, CRUD."""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import PenaltyType, PlanStatus, SavingsPlan
from app.schemas.plan import PlanCreateRequest, PlanUpdateRequest
from app.utils.codes import generate_plan_code


# ---------------------------------------------------------------------------
# Seeding (runs on startup)
# ---------------------------------------------------------------------------
async def seed_default_plans(db: AsyncSession) -> None:
    """Seed 3 default plans if no plans exist. Runs once."""
    result = await db.execute(select(SavingsPlan).limit(1))
    if result.scalar_one_or_none():
        return

    plans = [
        SavingsPlan(
            code="PLAN-001",
            name="Starter",
            description="Perfect for beginners. Save ₦2,000 weekly for 12 weeks and earn 8% returns at maturity.",
            weekly_amount=Decimal("2000.00"),
            duration_weeks=12,
            start_commission=Decimal("500.00"),
            return_rate=Decimal("8.00"),
            penalty_type=PenaltyType.FIXED,
            penalty_value=Decimal("500.00"),
            minimum_wallet_balance=Decimal("2500.00"),
            max_subscribers=None,
            is_seeded=True,
        ),
        SavingsPlan(
            code="PLAN-002",
            name="Classic",
            description="Our most popular plan. Save ₦5,000 weekly for 24 weeks and earn 12% returns at maturity.",
            weekly_amount=Decimal("5000.00"),
            duration_weeks=24,
            start_commission=Decimal("1000.00"),
            return_rate=Decimal("12.00"),
            penalty_type=PenaltyType.FIXED,
            penalty_value=Decimal("1000.00"),
            minimum_wallet_balance=Decimal("6000.00"),
            max_subscribers=None,
            is_seeded=True,
        ),
        SavingsPlan(
            code="PLAN-003",
            name="Premium",
            description="For serious savers. Save ₦10,000 weekly for 52 weeks and earn 18% returns at maturity.",
            weekly_amount=Decimal("10000.00"),
            duration_weeks=52,
            start_commission=Decimal("2000.00"),
            return_rate=Decimal("18.00"),
            penalty_type=PenaltyType.PERCENTAGE,
            penalty_value=Decimal("10.00"),
            minimum_wallet_balance=Decimal("12000.00"),
            max_subscribers=500,
            is_seeded=True,
        ),
    ]

    db.add_all(plans)
    await db.commit()
    print("[SEED] 3 default savings plans created.")


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
        start_commission=data.start_commission,
        return_rate=data.return_rate,
        penalty_type=PenaltyType(data.penalty_type),
        penalty_value=data.penalty_value,
        minimum_wallet_balance=data.minimum_wallet_balance,
        max_subscribers=data.max_subscribers,
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
        if field == "status" and value is not None:
            value = PlanStatus(value)
        setattr(plan, field, value)

    await db.commit()
    await db.refresh(plan)

    return plan
