"""Security services — bot protection and liveness checks."""

import logging
import httpx
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_turnstile_token(token: str | None, remote_ip: str | None = None) -> bool:
    """
    Verify Cloudflare Turnstile token.
    If TURNSTILE_SECRET_KEY is not set, we skip verification (development mode).
    """
    if not settings.TURNSTILE_SECRET_KEY:
        if token:
            logger.info("Turnstile secret not set - skipping verification of provided token.")
        return True

    if not token:
        logger.warning("Turnstile token missing while secret key is configured.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot protection token is required",
        )

    logger.info("Verifying Turnstile token...")
    
    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=10.0)
            data = response.json()
            
            if data.get("success"):
                logger.info("✅ Turnstile verification successful")
                return True
            
            logger.error(f"❌ Turnstile verification failed. Errors: {data.get('error-codes')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bot protection verification failed. Please try again.",
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Turnstile verification error: {e}")
        # In production, we might want to fail-open if Cloudflare is down, 
        # but usually Turnstile is very reliable. For now, we fail-closed for security.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security verification service is currently unavailable",
        )
