"""Ticket business logic — customer support service."""

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketMessage, TicketStatus
from app.schemas.ticket import TicketCreate, TicketMessageCreate, TicketUpdateStatus
from app.services import notifications as notify_service


# ---------------------------------------------------------------------------
# Core Ticket Operations (User/Admin)
# ---------------------------------------------------------------------------

async def create_ticket(user_id: uuid.UUID, data: TicketCreate, db: AsyncSession) -> Ticket:
    """Customer creates a new support ticket."""
    ticket = Ticket(
        user_id=user_id,
        subject=data.subject,
        description=data.description,
        priority=data.priority,
        status=TicketStatus.OPEN,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    
    # Send in-app notification to the user
    await notify_service.create_notification(
        user_id=user_id,
        title="Ticket Created",
        body=f"Your support ticket '{ticket.subject}' has been received. Our team will respond shortly.",
        notification_type=notify_service.NotificationType.INFO,
        channel=notify_service.NotificationChannel.IN_APP,
        db=db,
    )
    
    return ticket


async def get_ticket_detail(ticket_id: uuid.UUID, user_id: Optional[uuid.UUID], db: AsyncSession) -> Ticket:
    """Get ticket detail with messages. If user_id is provided, enforces ownership."""
    query = select(Ticket).options(
        selectinload(Ticket.messages),
        selectinload(Ticket.user)
    ).where(Ticket.id == ticket_id)
    
    if user_id:
        query = query.where(Ticket.user_id == user_id)
        
    result = await db.execute(query)
    ticket = result.scalar_one_or_none()
    
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
        
    return ticket


async def add_ticket_message(
    ticket_id: uuid.UUID, 
    sender_id: uuid.UUID, 
    data: TicketMessageCreate, 
    is_admin: bool, 
    db: AsyncSession
) -> TicketMessage:
    """Add a new message to an existing ticket."""
    # Ensure ticket exists (and conditionally check ownership if not admin)
    ticket = await get_ticket_detail(ticket_id, user_id=None if is_admin else sender_id, db=db)
    
    message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=sender_id,
        body=data.body,
        is_admin=is_admin,
    )
    db.add(message)
    
    # Auto-update status if admin responds to an open ticket
    if is_admin and ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.IN_PROGRESS
        
    await db.commit()
    await db.refresh(message)
    
    # Notify user if admin replies
    if is_admin:
        await notify_service.create_notification(
            user_id=ticket.user_id,
            title="Ticket Update",
            body=f"An admin has replied to your ticket '{ticket.subject}'.",
            notification_type=notify_service.NotificationType.INFO,
            channel=notify_service.NotificationChannel.IN_APP,
            db=db,
        )
        
    return message


# ---------------------------------------------------------------------------
# Admin Operations
# ---------------------------------------------------------------------------

async def admin_list_tickets(
    db: AsyncSession, 
    page: int = 1, 
    per_page: int = 20, 
    ticket_status: str | None = None
) -> dict:
    """Admin lists all tickets with pagination and optional status filter."""
    query = select(Ticket).options(selectinload(Ticket.user))
    count_query = select(func.count()).select_from(Ticket)
    
    if ticket_status:
        query = query.where(Ticket.status == ticket_status)
        count_query = count_query.where(Ticket.status == ticket_status)
        
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    query = query.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    return {
        "items": tickets,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


async def admin_update_ticket_status(ticket_id: uuid.UUID, data: TicketUpdateStatus, db: AsyncSession) -> Ticket:
    """Admin changes the status of a ticket."""
    ticket = await get_ticket_detail(ticket_id, user_id=None, db=db)
    ticket.status = data.status
    
    await db.commit()
    await db.refresh(ticket)
    
    # Notify user if status changed to resolved/closed
    if data.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]:
        await notify_service.create_notification(
            user_id=ticket.user_id,
            title="Ticket Resolved",
            body=f"Your ticket '{ticket.subject}' has been marked as {data.status.value}.",
            notification_type=notify_service.NotificationType.SUCCESS,
            channel=notify_service.NotificationChannel.IN_APP,
            db=db,
        )
        
    return ticket


# ---------------------------------------------------------------------------
# User Operations
# ---------------------------------------------------------------------------

async def user_list_tickets(user_id: uuid.UUID, db: AsyncSession, page: int = 1, per_page: int = 20) -> dict:
    """Customer lists their own tickets."""
    query = select(Ticket).where(Ticket.user_id == user_id)
    count_query = select(func.count()).select_from(Ticket).where(Ticket.user_id == user_id)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    query = query.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    tickets = result.scalars().all()
    
    return {
        "items": tickets,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }
