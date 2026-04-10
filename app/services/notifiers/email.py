"""Resend Email Client Service."""

import logging
import smtplib
from email.message import EmailMessage

import resend

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Resend
if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY


def send_smtp_email(to_email: str, subject: str, html_body: str):
    """Fallback mechanism using standard SMTP."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(f"[STUB] Missing both RESEND_API_KEY and SMTP_PASSWORD. Would send: '{subject}' to {to_email}")
        return

    logger.info(f"Sending via SMTP Fallback to {to_email}...")
    
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to_email
    msg.set_content("Please enable HTML to view this email.")
    msg.add_alternative(html_body, subtype="html")

    try:
        # Check standard SSL port vs TLS port
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
            
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"✅ Email sent successfully via SMTP Fallback to {to_email}.")
    except Exception as e:
        logger.error(f"❌ Failed to send email via SMTP Fallback to {to_email}. Error: {e}")
        raise e


async def send_resend_email_task(ctx, to_email: str, subject: str, html_body: str):
    """
    ARQ background task to send an email via Resend.
    Gracefully falls back to SMTP if Resend is unavailable or lacks keys.
    """
    logger.info(f"Attempting to send email '{subject}' to {to_email}...")
    
    # 1. Provide a quick fallback if Resend is explicitly missing
    if not settings.RESEND_API_KEY:
        logger.info("RESEND_API_KEY missing. Diverting to SMTP Fallback immediately.")
        send_smtp_email(to_email, subject, html_body)
        return

    # 2. Try Resend API
    try:
        params = {
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        
        email = resend.Emails.send(params)
        logger.info(f"✅ Email sent successfully via Resend. ID: {email.get('id')}")
        return email
        
    except Exception as e:
        logger.warning(f"⚠️ Resend failed ({e}). Falling back to SMTP...")
        send_smtp_email(to_email, subject, html_body)
