"""Admin — Plans CRUD."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.plan import SavingsPlan
from app.models.user import User, UserRole
from app.schemas.plan import PlanCreateRequest, PlanResponse, PlanUpdateRequest
from app.services import audit as audit_service
from app.services import plans as plans_service

router = APIRouter(prefix="/plans", tags=["Admin — Plans"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.get("")
async def list_all_plans(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all plans including inactive/archived (admin view)."""
    count_result = await db.execute(select(func.count()).select_from(SavingsPlan))
    total = count_result.scalar()

    result = await db.execute(
        select(SavingsPlan)
        .order_by(SavingsPlan.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    plans = result.scalars().all()

    return {
        "success": True,
        "data": [PlanResponse.model_validate(p).model_dump() for p in plans],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
        },
    }


@router.post("")
async def create_plan(
    data: PlanCreateRequest,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    plan = await plans_service.create_plan(data, admin.id, db)
    await db.flush()

    await audit_service.log_action(
        actor_id=admin.id,
        action="plan.created",
        target_type="SavingsPlan",
        target_id=plan.id,
        db=db,
        metadata={"name": plan.name, "code": plan.code},
        request=request,
    )

    return {
        "success": True,
        "data": PlanResponse.model_validate(plan).model_dump(),
        "message": f"Plan '{plan.name}' created.",
    }


@router.put("/{code}")
async def update_plan(
    code: str,
    data: PlanUpdateRequest,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    plan = await plans_service.update_plan(code, data, db)

    await audit_service.log_action(
        actor_id=admin.id,
        action="plan.updated",
        target_type="SavingsPlan",
        target_id=plan.id,
        db=db,
        metadata=data.model_dump(exclude_unset=True),
        request=request,
    )

    return {
        "success": True,
        "data": PlanResponse.model_validate(plan).model_dump(),
        "message": f"Plan '{plan.name}' updated.",
    }


@router.delete("/{code}")
async def deactivate_plan(
    code: str,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Soft-delete: set plan status to archived."""
    plan = await plans_service.get_plan_by_code(code, db)

    from app.models.plan import PlanStatus
    plan.status = PlanStatus.ARCHIVED

    await audit_service.log_action(
        actor_id=admin.id,
        action="plan.archived",
        target_type="SavingsPlan",
        target_id=plan.id,
        db=db,
        request=request,
    )

    return {"success": True, "data": None, "message": f"Plan '{plan.name}' archived."}
