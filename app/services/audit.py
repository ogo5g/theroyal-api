"""Audit log service — append-only admin action logging."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.audit import AuditLog


async def log_action(
    actor_id,
    action: str,
    target_type: str,
    target_id,
    db: AsyncSession,
    metadata: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Record an admin action in the audit log."""
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_=metadata,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(entry)
    return entry


async def list_audit_logs(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 50,
    action_filter: str | None = None,
) -> dict:
    """Get paginated audit logs (newest first)."""
    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action_filter:
        query = query.where(AuditLog.action.ilike(f"%{action_filter}%"))
        count_query = count_query.where(AuditLog.action.ilike(f"%{action_filter}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": list(logs),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }
