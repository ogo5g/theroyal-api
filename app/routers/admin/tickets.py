"""Admin Support Tickets Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.schemas.ticket import TicketMessageCreate, TicketUpdateStatus, TicketResponse, TicketMessageResponse
from app.services import ticket as ticket_service
from app.services import audit as audit_service

router = APIRouter(prefix="/tickets", tags=["Admin — Support Tickets"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.SUPPORT)


@router.get("")
async def list_all_tickets(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    """Admin endpoint to list all customer tickets across the system."""
    results = await ticket_service.admin_list_tickets(db, page=page, per_page=per_page, ticket_status=status)
    
    # We extend the dump to include user email for admin listing
    items = []
    for t in results["items"]:
        dump = TicketResponse.model_validate(t).model_dump()
        dump["user_email"] = t.user.email if hasattr(t, "user") and t.user else None
        dump["user_name"] = t.user.first_name if hasattr(t, "user") and t.user else None
        items.append(dump)
        
    results["items"] = items
    results["success"] = True
    return results


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin view full ticket details and conversation."""
    ticket = await ticket_service.get_ticket_detail(ticket_id, user_id=None, db=db)
    
    dump = TicketResponse.model_validate(ticket).model_dump()
    dump["user_email"] = ticket.user.email if hasattr(ticket, "user") and ticket.user else None
    
    # Optional enhancement: We can patch the message dump with sender names
    for m in dump["messages"]:
        if m["is_admin"]:
            m["sender_name"] = "Admin"
    
    return {"success": True, "data": dump}


@router.put("/{ticket_id}")
async def update_ticket_status(
    ticket_id: uuid.UUID,
    data: TicketUpdateStatus,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Admin updates the status of a ticket (e.g. resolve, close)."""
    ticket = await ticket_service.admin_update_ticket_status(ticket_id, data, db)
    
    await audit_service.log_action(
        actor_id=admin.id,
        action="ticket.status_updated",
        target_type="Ticket",
        target_id=ticket.id,
        db=db,
        metadata={"new_status": data.status.value},
        request=request,
    )
    
    return {
        "success": True, 
        "data": TicketResponse.model_validate(ticket).model_dump(),
        "message": f"Ticket marked as {data.status.value}"
    }


@router.post("/{ticket_id}/messages")
async def admin_add_message(
    ticket_id: uuid.UUID,
    data: TicketMessageCreate,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin responds to a customer ticket."""
    message = await ticket_service.add_ticket_message(
        ticket_id=ticket_id,
        sender_id=admin.id,
        data=data,
        is_admin=True,
        db=db
    )
    
    return {
        "success": True,
        "data": TicketMessageResponse.model_validate(message).model_dump(),
        "message": "Response sent."
    }
