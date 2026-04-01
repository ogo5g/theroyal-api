"""Plans router — public plan listing."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.plan import PlanResponse
from app.services import plans as plans_service

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.get("")
async def list_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    plans = await plans_service.list_plans(db)
    return {
        "success": True,
        "data": [PlanResponse.model_validate(p).model_dump() for p in plans],
        "message": f"{len(plans)} plan(s) found.",
    }


@router.get("/{code}")
async def get_plan(
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    plan = await plans_service.get_plan_by_code(code, db)
    return {
        "success": True,
        "data": PlanResponse.model_validate(plan).model_dump(),
        "message": "Plan retrieved.",
    }
