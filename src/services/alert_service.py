# Read deployment environment, emit operational diagnostics, and call webhooks asynchronously.
import os
import logging
import httpx
import asyncio

# Create a module logger so alert failures are observable without interrupting core workflows.
logger = logging.getLogger(__name__)

# Resolve the general alert destination once when the worker process starts.
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
# Prefer an engineering-specific destination while retaining the general URL as a fallback.
ENG_ALERT_WEBHOOK_URL = os.getenv("ENG_ALERT_WEBHOOK_URL", ALERT_WEBHOOK_URL)
# Prefer a CSM-specific destination while retaining the general URL as a fallback.
CSM_ALERT_WEBHOOK_URL = os.getenv("CSM_ALERT_WEBHOOK_URL", ALERT_WEBHOOK_URL)

# Build the provider-neutral payload so every alert channel receives consistent context.
def build_alert_payload(subject: str, message: str, details: dict = None) -> dict:
    return {
        "text": f"*{subject}*\n{message}",
        "details": details or {},
    }


# Define the async alert contract used by background jobs and operational integrations.
async def send_alert(
    subject: str,
    message: str,
    details: dict = None,
    webhook_url: str = None,
):
    """
    Sends an alert to the configured webhook URL.
    """
    # Avoid an outbound request when alerting is intentionally not configured in an environment.
    destination = webhook_url or ALERT_WEBHOOK_URL
    if not destination:
        logger.warning("[Alert] No ALERT_WEBHOOK_URL configured. Suppressing alert.")
        return

    payload = build_alert_payload(subject, message, details)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(destination, json=payload)
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("[Alert] Failed to deliver alert subject=%s", subject)
        raise


async def send_csm_sla_alert(breaches: list[dict]):
    # Suppress delivery when this deployment has no CSM notification endpoint.
    if not CSM_ALERT_WEBHOOK_URL:
        logger.warning("[Alert] No CSM_ALERT_WEBHOOK_URL configured. Suppressing alert.")
        return

    # Start a human-readable incident summary that can be rendered by chat webhook consumers.
    summary = "🚨 *CSM SLA Breach Alert*\n\nThe following students are currently out of SLA:"
    # Avoid sending an empty alert when the auditor found no violations.
    if not breaches:
        return

    # Add one line per breached student so responders can identify the required follow-up.
    for b in breaches:
        summary += f"\n• {b['student_id']} - {b['name']} ({b['program']}): {b['breach_type']}"

    await send_alert(
        "CSM SLA Breach Alert",
        summary,
        {"breach_count": len(breaches)},
        webhook_url=CSM_ALERT_WEBHOOK_URL,
    )
