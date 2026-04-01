"""Notifications router — list, read, read-all."""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services import notifications as notif_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
):
    result = await notif_service.list_notifications(
        current_user, db, page=page, per_page=per_page, unread_only=unread_only
    )
    return {
        "success": True,
        "data": [
            {
                "id": str(n.id),
                "title": n.title,
                "body": n.body,
                "type": n.type.value,
                "channel": n.channel.value,
                "is_read": n.is_read,
                "read_at": n.read_at.isoformat() if n.read_at else None,
                "created_at": n.created_at.isoformat(),
            }
            for n in result["items"]
        ],
        "pagination": {
            "page": result["page"],
            "per_page": result["per_page"],
            "total": result["total"],
            "pages": result["pages"],
        },
    }


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await notif_service.mark_read(current_user, notification_id, db)
    return {
        "success": True,
        "data": None,
        "message": "Notification marked as read.",
    }


@router.put("/read-all")
async def mark_all_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    count = await notif_service.mark_all_read(current_user, db)
    return {
        "success": True,
        "data": {"marked_count": count},
        "message": f"{count} notification(s) marked as read.",
    }
