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

# Define the async alert contract used by background jobs and operational integrations.
async def send_alert(subject: str, message: str, details: dict = None):
    """
    Sends an alert to the configured webhook URL.
    """
    # Avoid an outbound request when alerting is intentionally not configured in an environment.
    if not ALERT_WEBHOOK_URL:
        logger.warning("[Alert] No ALERT_WEBHOOK_URL configured. Suppressing alert.")
        return

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

    # Wrap the text in the webhook provider's expected request shape.
    payload = {"text": summary}

    try:
        # Use a short-lived async client so network I/O does not block the event loop.
        async with httpx.AsyncClient(timeout=5.0) as client:
            # POST the alert and require a successful HTTP status from the provider.
            response = await client.post(CSM_ALERT_WEBHOOK_URL, json=payload)
            response.raise_for_status()
    except Exception as e:
        # Log delivery failure while allowing the audit job itself to finish and be retried externally.
        logger.error(f"Failed to send CSM alert: {e}")
