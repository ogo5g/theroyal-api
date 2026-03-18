"""Plan seeding — inserts 3 default plans on first app startup."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import PenaltyType, SavingsPlan


async def seed_default_plans(db: AsyncSession) -> None:
    """Seed 3 default plans if no plans exist. Runs once."""
    result = await db.execute(select(SavingsPlan).limit(1))
    if result.scalar_one_or_none():
        return  # Plans already exist

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
