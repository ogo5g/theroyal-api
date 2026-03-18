"""User model."""

import enum
import uuid

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    STAFF = "staff"
    MEMBER = "member"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    other_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.MEMBER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    account = relationship("Account", back_populates="user", uselist=False, lazy="selectin")
    kyc = relationship("KYC", back_populates="user", uselist=False, lazy="selectin", foreign_keys="[KYC.user_id]")
    subscriptions = relationship("Subscription", back_populates="user", lazy="selectin")
    notifications = relationship("Notification", back_populates="user", lazy="selectin")
    transactions = relationship("WalletTransaction", back_populates="user", lazy="selectin")
