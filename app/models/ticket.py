"""Ticket model — Customer support feature."""

import uuid
from datetime import datetime, timezone
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Ticket(Base):
    """A customer support ticket."""
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    
    status = Column(Enum(TicketStatus, name="ticket_status_enum"), default=TicketStatus.OPEN, nullable=False, index=True)
    priority = Column(Enum(TicketPriority, name="ticket_priority_enum"), default=TicketPriority.MEDIUM, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", backref="tickets", lazy="selectin")
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan", lazy="selectin", order_by="TicketMessage.created_at")


class TicketMessage(Base):
    """A threaded message inside a ticket."""
    __tablename__ = "ticket_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    body = Column(Text, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    ticket = relationship("Ticket", back_populates="messages")
    sender = relationship("User", lazy="selectin")
