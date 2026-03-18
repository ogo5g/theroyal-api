"""Subscription and PaymentSchedule models."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.utils.codes import generate_referral_code, generate_subscription_sid


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DEFAULTED = "defaulted"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    SETTLED = "settled"


class ScheduleStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    MISSED = "missed"
    WAIVED = "waived"


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    sid: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, default=generate_subscription_sid, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("savings_plans.id"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False
    )
    weekly_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_expected: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_paid: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), default=Decimal("0.00"), nullable=False
    )
    settlement_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    weeks_paid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missed_payments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    referral_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, default=generate_referral_code
    )
    referred_by_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    upline_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True
    )
    commission_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    penalty_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_debit_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("SavingsPlan", back_populates="subscriptions")
    schedule = relationship("PaymentSchedule", back_populates="subscription", lazy="selectin")
    upline = relationship("Subscription", remote_side="Subscription.id", lazy="selectin")


class PaymentSchedule(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_schedules"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus), default=ScheduleStatus.PENDING, nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallet_transactions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    # Relationships
    subscription = relationship("Subscription", back_populates="schedule")
    transaction = relationship("WalletTransaction", lazy="selectin")
