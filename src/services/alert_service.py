import os
import logging
import httpx
import asyncio

logger = logging.getLogger(__name__)

ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

async def send_alert(subject: str, message: str, details: dict = None):
    """
    Sends an alert to the configured webhook URL.
    """
    if not ALERT_WEBHOOK_URL:
        logger.warning("[Alert] No ALERT_WEBHOOK_URL configured. Suppressing alert.")
        return

    payload = {
        "text": f"🚨 *{subject}*\n{message}\nDetails: `{details}`" if details else f"🚨 *{subject}*\n{message}"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(ALERT_WEBHOOK_URL, json=payload, timeout=10.0)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
