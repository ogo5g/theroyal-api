"""Admin — KYC review (approve / reject / detail)."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import require_role
from app.models.kyc import KYC, KYCStatus
from app.models.user import User, UserRole
from app.services import audit as audit_service
from app.services import notifications as notif_service
from app.utils.security import decrypt_field

router = APIRouter(prefix="/kyc", tags=["Admin — KYC"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


def _safe_decrypt(value: str | None) -> str | None:
    """Decrypt a Fernet-encrypted field, returning None on failure."""
    if not value:
        return None
    try:
        return decrypt_field(value)
    except Exception:
        return "[decryption error]"


@router.get("")
async def list_kyc(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    query = select(KYC).options(selectinload(KYC.user))
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
                "user_name": f"{k.user.first_name or ''} {k.user.last_name or ''}".strip() or None if k.user else None,
                "user_email": k.user.email if k.user else None,
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


@router.get("/{kyc_id}")
async def get_kyc_detail(
    kyc_id: uuid.UUID,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get full KYC detail with decrypted sensitive fields for admin review."""
    result = await db.execute(
        select(KYC).options(selectinload(KYC.user), selectinload(KYC.reviewer)).where(KYC.id == kyc_id)
    )
    kyc = result.scalar_one_or_none()
    if not kyc:
        return {"success": False, "error": "not_found", "message": "KYC record not found"}

    user = kyc.user
    reviewer = kyc.reviewer

    return {
        "success": True,
        "data": {
            "id": str(kyc.id),
            # User context
            "user": {
                "id": str(user.id) if user else None,
                "email": user.email if user else None,
                "phone_number": user.phone_number if user else None,
                "first_name": user.first_name if user else None,
                "last_name": user.last_name if user else None,
                "profile_image_url": user.profile_image_url if user and hasattr(user, "profile_image_url") else None,
            } if user else None,
            # Identity
            "nin": _safe_decrypt(kyc.nin),
            "bvn": _safe_decrypt(kyc.bvn),
            "date_of_birth": kyc.date_of_birth.isoformat() if kyc.date_of_birth else None,
            "address": kyc.address,
            "state": kyc.state,
            # Bank details
            "bank_name": kyc.bank_name,
            "bank_code": kyc.bank_code,
            "account_number": _safe_decrypt(kyc.account_number),
            "account_name": kyc.account_name,
            # Documents
            "document_type": kyc.document_type.value,
            "document_url": kyc.document_url,
            "selfie_url": kyc.selfie_url,
            # Review status
            "status": kyc.status.value,
            "rejection_reason": kyc.rejection_reason,
            "submitted_at": kyc.submitted_at.isoformat() if kyc.submitted_at else None,
            "reviewed_at": kyc.reviewed_at.isoformat() if kyc.reviewed_at else None,
            "reviewed_by": {
                "id": str(reviewer.id),
                "email": reviewer.email,
                "first_name": reviewer.first_name,
                "last_name": reviewer.last_name,
            } if reviewer else None,
        },
        "message": "KYC detail retrieved.",
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
