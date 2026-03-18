"""KYC model — identity verification and document storage."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentType(str, enum.Enum):
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"
    VOTERS_CARD = "voters_card"
    INTL_PASSPORT = "intl_passport"


class KYCStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class KYC(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "kyc"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )

    # Encrypted at rest
    bvn: Mapped[str | None] = mapped_column(Text, nullable=True)
    nin: Mapped[str | None] = mapped_column(Text, nullable=True)

    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)

    # Bank details
    bank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(10), nullable=False)
    account_number: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Document
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), nullable=False)
    document_url: Mapped[str] = mapped_column(Text, nullable=False)
    selfie_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Review
    status: Mapped[KYCStatus] = mapped_column(
        Enum(KYCStatus), default=KYCStatus.PENDING, nullable=False
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    user = relationship("User", back_populates="kyc", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by], lazy="selectin")
