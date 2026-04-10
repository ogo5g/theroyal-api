"""Customer Support Tickets Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketMessageCreate, TicketResponse, TicketMessageResponse
from app.services import ticket as ticket_service
from app.services import audit as audit_service

router = APIRouter(prefix="/tickets", tags=["Support Tickets"])


@router.post("")
async def create_ticket(
    data: TicketCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Create a new support ticket."""
    ticket = await ticket_service.create_ticket(user.id, data, db)
    
    await audit_service.log_action(
        actor_id=user.id,
        action="ticket.created",
        target_type="Ticket",
        target_id=ticket.id,
        db=db,
        metadata={"subject": data.subject},
        request=request,
    )
    
    return {
        "success": True, 
        "data": TicketResponse.model_validate(ticket).model_dump(),
        "message": "Ticket created successfully. Our team will contact you shortly."
    }


@router.get("")
async def list_my_tickets(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all tickets created by the user."""
    results = await ticket_service.user_list_tickets(user.id, db, page=page, per_page=per_page)
    results["items"] = [TicketResponse.model_validate(t).model_dump() for t in results["items"]]
    results["success"] = True
    return results


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get ticket details including all messages."""
    ticket = await ticket_service.get_ticket_detail(ticket_id, user_id=user.id, db=db)
    return {
        "success": True, 
        "data": TicketResponse.model_validate(ticket).model_dump()
    }


@router.post("/{ticket_id}/messages")
async def add_ticket_message(
    ticket_id: uuid.UUID,
    data: TicketMessageCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reply to a ticket."""
    message = await ticket_service.add_ticket_message(
        ticket_id=ticket_id,
        sender_id=user.id,
        data=data,
        is_admin=False,
        db=db
    )
    
    return {
        "success": True,
        "data": TicketMessageResponse.model_validate(message).model_dump(),
        "message": "Reply sent successfully."
    }
