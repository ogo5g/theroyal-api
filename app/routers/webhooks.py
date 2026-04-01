"""Platnova webhook handler — HMAC verification + event routing."""

import hashlib
import hmac
from decimal import Decimal

from fastapi import APIRouter, Header, HTTPException, Request, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services import wallet as wallet_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_platnova_signature(payload: bytes, signature: str) -> bool:
    """Verify Platnova webhook HMAC-SHA512 signature."""
    if not settings.PLATNOVA_WEBHOOK_SECRET:
        return True  # Skip in dev if no secret configured

    expected = hmac.new(
        settings.PLATNOVA_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@router.post("/platnova")
async def platnova_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_platnova_signature: str | None = Header(None),
):
    """Handle Platnova webhook events."""
    body = await request.body()

    # 1. Verify HMAC signature
    signature = x_platnova_signature or ""
    if not verify_platnova_signature(body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # 2. Parse event
    data = await request.json()
    event_type = data.get("event", "")
    event_data = data.get("data", {})

    # 3. Route by event type
    if event_type in ("charge.success", "transfer.success", "virtualaccount.credit"):
        reference = event_data.get("reference", "")
        amount = Decimal(str(event_data.get("amount", 0)))
        provider_ref = str(event_data.get("id", event_data.get("provider_reference", "")))

        try:
            await wallet_service.process_funding_webhook(
                reference=reference,
                amount=amount,
                provider_reference=provider_ref,
                metadata=event_data,
                db=db,
            )
        except HTTPException as e:
            if e.status_code == status.HTTP_409_CONFLICT:
                # Duplicate — already processed, return 200 to stop retries
                return {"success": True, "message": "Already processed"}
            raise

    # Always return 200 to acknowledge receipt
    return {"success": True, "message": "Webhook received"}
