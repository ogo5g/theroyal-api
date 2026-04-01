"""Admin — KYC review (approve / reject)."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.kyc import KYC, KYCStatus
from app.models.user import User, UserRole
from app.services import audit as audit_service
from app.services import notifications as notif_service

router = APIRouter(prefix="/kyc", tags=["Admin — KYC"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.get("")
async def list_kyc(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    query = select(KYC)
    count_query = select(func.count()).select_from(KYC)

    if status:
        query = query.where(KYC.status == status)
        count_query = count_query.where(KYC.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(KYC.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    kyc_records = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "id": str(k.id),
                "user_id": str(k.user_id),
                "status": k.status.value,
                "document_type": k.document_type.value,
                "submitted_at": k.submitted_at.isoformat() if k.submitted_at else None,
                "reviewed_at": k.reviewed_at.isoformat() if k.reviewed_at else None,
                "rejection_reason": k.rejection_reason,
            }
            for k in kyc_records
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
        },
    }


@router.put("/{kyc_id}/approve")
async def approve_kyc(
    kyc_id: uuid.UUID,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    result = await db.execute(select(KYC).where(KYC.id == kyc_id))
    kyc = result.scalar_one_or_none()
    if not kyc:
        return {"success": False, "error": "not_found", "message": "KYC record not found"}

    kyc.status = KYCStatus.APPROVED
    kyc.reviewed_by = admin.id
    kyc.reviewed_at = datetime.now(timezone.utc)
    kyc.rejection_reason = None

    await audit_service.log_action(
        actor_id=admin.id,
        action="kyc.approved",
        target_type="KYC",
        target_id=kyc.id,
        db=db,
        request=request,
    )

    await notif_service.notify_kyc_approved(kyc.user_id, db)

    return {"success": True, "data": None, "message": "KYC approved."}


@router.put("/{kyc_id}/reject")
async def reject_kyc(
    kyc_id: uuid.UUID,
    data: dict,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    result = await db.execute(select(KYC).where(KYC.id == kyc_id))
    kyc = result.scalar_one_or_none()
    if not kyc:
        return {"success": False, "error": "not_found", "message": "KYC record not found"}

    reason = data.get("reason", "No reason provided")

    kyc.status = KYCStatus.REJECTED
    kyc.reviewed_by = admin.id
    kyc.reviewed_at = datetime.now(timezone.utc)
    kyc.rejection_reason = reason

    await audit_service.log_action(
        actor_id=admin.id,
        action="kyc.rejected",
        target_type="KYC",
        target_id=kyc.id,
        db=db,
        metadata={"reason": reason},
        request=request,
    )

    await notif_service.notify_kyc_rejected(kyc.user_id, reason, db)

    return {"success": True, "data": None, "message": "KYC rejected."}
