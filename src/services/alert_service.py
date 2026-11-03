import os
import logging
import httpx
import asyncio

logger = logging.getLogger(__name__)

ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ENG_ALERT_WEBHOOK_URL = os.getenv("ENG_ALERT_WEBHOOK_URL", ALERT_WEBHOOK_URL)
CSM_ALERT_WEBHOOK_URL = os.getenv("CSM_ALERT_WEBHOOK_URL", ALERT_WEBHOOK_URL)

async def send_alert(subject: str, message: str, details: dict = None):
    """
    Sends an alert to the configured webhook URL.
    """
    if not ALERT_WEBHOOK_URL:
        logger.warning("[Alert] No ALERT_WEBHOOK_URL configured. Suppressing alert.")
        return

async def send_csm_sla_alert(breaches: list[dict]):
    if not CSM_ALERT_WEBHOOK_URL:
        logger.warning("[Alert] No CSM_ALERT_WEBHOOK_URL configured. Suppressing alert.")
        return

    summary = "🚨 *CSM SLA Breach Alert*\n\nThe following students are currently out of SLA:"
    if not breaches:
        return

    for b in breaches:
        summary += f"\n• {b['student_id']} - {b['name']} ({b['program']}): {b['breach_type']}"

    payload = {"text": summary}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(CSM_ALERT_WEBHOOK_URL, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send CSM alert: {e}")
