"""User model."""

import enum

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    STAFF = "staff"
    MEMBER = "member"


class OnboardingStep(str, enum.Enum):
    REGISTERED = "registered"             # Phone submitted, phone OTP pending
    PHONE_VERIFIED = "phone_verified"     # Phone OTP verified
    EMAIL_VERIFIED = "email_verified"     # Email submitted & OTP verified
    PASSWORD_SET = "password_set"         # Password created
    BASIC_INFO = "basic_info"             # Names, phone, DOB, address
    NIN_SUBMITTED = "nin_submitted"       # NIN encrypted & saved
    BVN_SUBMITTED = "bvn_submitted"       # BVN encrypted & saved
    PROFILE_UPLOADED = "profile_uploaded" # Profile photo uploaded
    COMPLETED = "completed"               # All steps done


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    other_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.MEMBER, nullable=False
    )
    onboarding_step: Mapped[OnboardingStep] = mapped_column(
        Enum(OnboardingStep), default=OnboardingStep.REGISTERED, nullable=False
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
