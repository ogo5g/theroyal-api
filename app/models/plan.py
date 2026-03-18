"""SavingsPlan model."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class PenaltyType(str, enum.Enum):
    FIXED = "fixed"
    PERCENTAGE = "percentage"


class SavingsPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "savings_plans"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    weekly_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    start_commission: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    return_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    penalty_type: Mapped[PenaltyType] = mapped_column(Enum(PenaltyType), nullable=False)
    penalty_value: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    minimum_wallet_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), nullable=False
    )
    max_subscribers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_subscribers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus), default=PlanStatus.ACTIVE, nullable=False
    )
    is_seeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan", lazy="selectin")
