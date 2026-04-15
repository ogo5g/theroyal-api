"""Admin — Staff user management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.services import auth as auth_service
from app.services import audit as audit_service

router = APIRouter(prefix="/staff", tags=["Admin — Staff"])

admin_senior = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)
admin_super = require_role(UserRole.SUPER_ADMIN)

STAFF_ROLES = {UserRole.ADMIN, UserRole.MODERATOR, UserRole.STAFF}


class CreateStaffRequest(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: str | None = None
    role: str  # admin, moderator, staff


@router.get("")
async def list_staff(
    admin: Annotated[User, Depends(admin_senior)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all staff users (admin, moderator, staff roles)."""
    staff_roles = [UserRole.ADMIN, UserRole.MODERATOR, UserRole.STAFF]

    count_query = (
        select(func.count())
        .select_from(User)
        .where(User.role.in_(staff_roles))
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        select(User)
        .where(User.role.in_(staff_roles))
        .order_by(User.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    data = [
        {
            "id": str(u.id),
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "role": u.role.value,
            "is_active": u.is_active,
            "is_suspended": u.is_suspended,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]

    return {
        "success": True,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
        },
    }


@router.post("")
async def create_staff(
    data: CreateStaffRequest,
    admin: Annotated[User, Depends(admin_super)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Create a new staff/admin/moderator user (super_admin only)."""
    try:
        role = UserRole(data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}. Must be one of: admin, moderator, staff")

    if role not in STAFF_ROLES:
        raise HTTPException(status_code=400, detail="Role must be one of: admin, moderator, staff")

    user = await auth_service.create_staff_user(
        email=str(data.email),
        first_name=data.first_name,
        last_name=data.last_name,
        phone_number=data.phone_number,
        role=role,
        db=db,
    )

    await audit_service.log_action(
        actor_id=admin.id,
        action="staff.created",
        target_type="User",
        target_id=user.id,
        db=db,
        metadata={"email": str(data.email), "role": data.role},
        request=request,
    )

    await db.commit()

    return {
        "success": True,
        "data": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.value,
        },
        "message": f"Staff user created. Welcome email sent to {data.email}.",
    }
