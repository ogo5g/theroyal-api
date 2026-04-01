"""Seed a super-admin user on startup (idempotent)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import OnboardingStep, User, UserRole
from app.utils.security import hash_password


ADMIN_EMAIL = "admin@theroyalsaving.com"
ADMIN_PASSWORD = "Admin@1234"  # Change in production


async def seed_admin_user(db: AsyncSession) -> None:
    """Create the super-admin if it doesn't already exist."""
    result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
    if result.scalar_one_or_none():
        return  # Already seeded

    admin = User(
        email=ADMIN_EMAIL,
        hashed_password=hash_password(ADMIN_PASSWORD),
        first_name="Super",
        last_name="Admin",
        phone_number="+2340000000000",
        role=UserRole.SUPER_ADMIN,
        onboarding_step=OnboardingStep.COMPLETED,
        is_active=True,
        is_verified=True,
        is_suspended=False,
    )
    db.add(admin)
    await db.commit()
    print(f"[SEED] Super-admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
