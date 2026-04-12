"""Termii SMS Client Service."""

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_termii_sms_task(ctx, to_phone: str, message: str):
    """
    ARQ background task to send an SMS via Termii.
    """
    base_url = "https://v3.api.termii.com"
    if not settings.TERMII_API_KEY:
        logger.warning(f"[STUB] Missing TERMII_API_KEY. Would send to {to_phone}: {message}")
        return

    logger.info(f"Sending SMS to {to_phone}...")
    
    url = f"{base_url}/api/sms/send"
    payload = {
        "to": to_phone,
        "from": settings.TERMII_SENDER_ID,
        "sms": message,
        "type": "plain",
        "channel": "generic",
        "api_key": settings.TERMII_API_KEY,
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            data = response.json()
            
            if response.status_code == 200 and data.get("message") == "Successfully Sent":
                logger.info(f"SMS sent successfully to {to_phone}. ID: {data.get('message_id')}")
            else:
                logger.error(f"Failed to send SMS. Status: {response.status_code}, Response: {data}")
                
            return data
            
    except Exception as e:
        logger.error(f"HTTP Error sending SMS to {to_phone}: {e}")
        raise e

async def send_sendchamp_sms_task(ctx, to_phone: str, message: str):
    """
    ARQ background task to send an SMS via Sendchamp.
    """
    base_url = "https://api.sendchamp.com/api/v1"
    pub_key = settings.SENDCHAMP_API_KEY
    if not pub_key:
        logger.warning(f"[STUB] Missing SENDCHAMP_API_KEY. Would send to {to_phone}: {message}")
        return

    logger.info(f"Sending SMS to {to_phone}...")
    
    url = f"{base_url}/sms/send"
    payload = {
        "to": [to_phone],
        "message": message,
        "sender_name": settings.SENDCHAMP_SENDER_ID,
        "route": "dnd"
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": f"Bearer {pub_key}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            data = response.json()
            
            if response.status_code == 200 and data.get("message") == "Successfully Sent":
                logger.info(f"SMS sent successfully to {to_phone}. ID: {data.get('message_id')}")
            else:
                logger.error(f"Failed to send SMS. Status: {response.status_code}, Response: {data}")
                
            return data
            
    except Exception as e:
        logger.error(f"HTTP Error sending SMS to {to_phone}: {e}")
        raise e