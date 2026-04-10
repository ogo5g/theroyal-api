"""Ticket request/response schemas."""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.ticket import TicketStatus, TicketPriority

class TicketMessageCreate(BaseModel):
    body: str

class TicketMessageResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_id: uuid.UUID | None
    body: str
    is_admin: bool
    created_at: datetime
    
    # Minimal sender info
    sender_name: str | None = None
    
    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketUpdateStatus(BaseModel):
    status: TicketStatus


class TicketResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime
    updated_at: datetime
    
    # To optionally embed messages in detail view
    messages: list[TicketMessageResponse] = []
    
    # Optionally embed user email
    user_email: str | None = None
    user_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
