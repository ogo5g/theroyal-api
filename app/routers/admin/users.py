"""Admin — User management."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models.user import User, UserRole
from app.services import audit as audit_service

router = APIRouter(prefix="/users", tags=["Admin — Users"])
admin_dep = require_role(UserRole.SUPER_ADMIN, UserRole.ADMIN)


@router.get("")
async def list_users(
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    role: str | None = Query(None),
):
    query = select(User)
    count_query = select(func.count()).select_from(User)

    if search:
        search_filter = User.email.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "id": str(u.id),
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "phone_number": u.phone_number,
                "role": u.role.value,
                "is_active": u.is_active,
                "is_verified": u.is_verified,
                "is_suspended": u.is_suspended,
                "onboarding_step": u.onboarding_step.value if u.onboarding_step else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
        },
    }


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.models.account import Account
    from app.models.kyc import KYC
    from app.models.subscription import Subscription

    # Query user with eagerly loaded relationships or manual side queries depending on model structure.
    # Since we might not have pure relationships configured on the User model for all these,
    # let's just do individual queries which is safe and performant enough for admin detail views.
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"success": False, "error": "not_found", "message": "User not found"}

    # Fetch supplementary data
    account_res = await db.execute(select(Account).where(Account.user_id == user_id))
    account = account_res.scalar_one_or_none()

    kyc_res = await db.execute(select(KYC).where(KYC.user_id == user_id))
    kyc = kyc_res.scalar_one_or_none()

    subs_res = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    subscriptions = subs_res.scalars().all()

    # Format the supplementary data
    account_data = None
    if account:
        account_data = {
            "wallet_balance": float(account.wallet_balance),
            "total_saved": float(account.total_saved),
            "total_withdrawn": float(account.total_withdrawn),
            "virtual_account": account.virtual_account_number,
            "bank_name": account.virtual_account_bank,
        }

    kyc_data = None
    if kyc:
        kyc_data = {
            "status": kyc.status.value if kyc.status else "pending",
            "document_type": kyc.document_type,
            "submitted_at": kyc.submitted_at.isoformat() if kyc.submitted_at else None,
            "rejection_reason": kyc.rejection_reason,
        }
        
    subs_data = [
        {
            "id": str(s.id),
            "sid": s.sid,
            "plan_code": s.plan_id,
            "status": s.status.value,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subscriptions
    ]

    return {
        "success": True,
        "data": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "profile_image_url": user.profile_image_url if hasattr(user, "profile_image_url") else None,
            "role": user.role.value,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_suspended": user.is_suspended,
            "onboarding_step": user.onboarding_step.value if user.onboarding_step else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "account": account_data,
            "kyc": kyc_data,
            "recent_subscriptions": subs_data[:5], # Send 5 most recent
            "total_subscriptions": len(subscriptions)
        },
        "message": "User retrieved.",
    }


@router.put("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    data: dict,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"success": False, "error": "not_found", "message": "User not found"}

    before_state = {"role": user.role.value, "is_active": user.is_active, "is_suspended": user.is_suspended}

    # Only allow updating specific admin-managed fields
    allowed = {"role", "is_active", "is_suspended"}
    for field in allowed:
        if field in data:
            if field == "role":
                setattr(user, field, UserRole(data[field]))
            else:
                setattr(user, field, data[field])

    after_state = {"role": user.role.value, "is_active": user.is_active, "is_suspended": user.is_suspended}

    await audit_service.log_action(
        actor_id=admin.id,
        action="user.updated",
        target_type="User",
        target_id=user.id,
        db=db,
        metadata={"before": before_state, "after": after_state},
        request=request,
    )

    return {
        "success": True,
        "data": {"id": str(user.id), "role": user.role.value, "is_active": user.is_active, "is_suspended": user.is_suspended},
        "message": "User updated.",
    }


# ---------------------------------------------------------------------------
# Admin Wallet Credit & Bypass
# ---------------------------------------------------------------------------

class ToggleBypassRequest(BaseModel):
    wallet_bypass: bool = Field(..., description="Whether to bypass wallet activation check")

@router.post("/{user_id}/toggle-wallet-bypass")
async def toggle_wallet_bypass(
    user_id: uuid.UUID,
    data: ToggleBypassRequest,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    # 1. Get user and account
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    acct_result = await db.execute(
        select(Account).where(Account.user_id == user_id)
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="User account not found")

    # 2. Update bypass flag
    old_status = account.wallet_bypass
    account.wallet_bypass = data.wallet_bypass

    # 3. Audit log
    ip_address = request.client.host if request else None
    action = "enabled" if data.wallet_bypass else "disabled"
    await audit_service.log_action(
        db=db,
        admin_id=admin.id,
        action="wallet.bypass_toggled",
        entity_type="account",
        entity_id=account.id,
        details={
            "user_id": str(user.id),
            "user_email": user.email,
            "old_status": old_status,
            "new_status": data.wallet_bypass,
            "reason": f"Admin manually {action} wallet activation bypass.",
        },
        ip_address=ip_address,
    )

    await db.commit()

    return {
        "success": True,
        "data": {"wallet_bypass": account.wallet_bypass},
        "message": f"Wallet activation bypass {action} successfully.",
    }

class CreditWalletRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to credit in Naira")
    description: str = Field(..., min_length=3, max_length=500, description="Reason for the credit")


@router.post("/{user_id}/credit-wallet")
async def credit_user_wallet(
    user_id: uuid.UUID,
    data: CreditWalletRequest,
    admin: Annotated[User, Depends(admin_dep)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
):
    """Admin manually credits a user's wallet. Creates a transaction and audit log."""
    from app.models.account import Account
    from app.models.wallet import TransactionCategory
    from app.services.wallet import credit_wallet

    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify user has an account
    acc_result = await db.execute(select(Account).where(Account.user_id == user_id))
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="User has no wallet account")

    amount = Decimal(str(data.amount))
    reference = f"ADMIN-CREDIT-{uuid.uuid4().hex[:12].upper()}"

    txn = await credit_wallet(
        user_id=user_id,
        amount=amount,
        category=TransactionCategory.WALLET_FUNDING,
        reference=reference,
        description=f"Admin credit: {data.description}",
        db=db,
        metadata={"admin_id": str(admin.id), "reason": data.description},
    )

    await audit_service.log_action(
        actor_id=admin.id,
        action="wallet.admin_credit",
        target_type="User",
        target_id=user_id,
        db=db,
        metadata={"amount": float(amount), "reference": reference, "description": data.description},
        request=request,
    )

    await db.commit()

    # Refresh to get updated balance
    await db.refresh(account)

    return {
        "success": True,
        "data": {
            "wallet_balance": float(account.wallet_balance),
            "transaction_id": str(txn.id),
            "reference": reference,
        },
        "message": f"₦{amount:,.2f} credited to user wallet.",
    }
