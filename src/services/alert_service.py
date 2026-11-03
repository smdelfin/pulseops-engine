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

# - Builds the provider-neutral payload shared by all alert channels.
# - Architectural Purpose: Keeps human-readable text and machine-readable details consistent across integrations.
# - Plain-English: 'Package an alert the same way regardless of where it is sent.'
def build_alert_payload(subject: str, message: str, details: dict = None) -> dict:
    # - Returns a text summary and structured details in one JSON-serializable object.
    return {
        # - Formats the subject as a visible heading followed by the message body.
        "text": f"*{subject}*\n{message}",
        # - Uses an empty mapping when callers omit optional context.
        "details": details or {},
    }


# - Defines the asynchronous alert-delivery contract used by workers and integrations.
# - Architectural Purpose: Async HTTP keeps alert delivery from blocking queue processing while a bounded timeout limits stalls.
# - Plain-English: 'Send an alert without freezing the worker if the destination is slow.'
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

    # - Builds a consistent payload before making the outbound network request.
    payload = build_alert_payload(subject, message, details)
    # - Converts network failures into explicit exceptions for the caller's retry/error policy.
    try:
        # - Creates a short-lived async HTTP client with a five-second timeout.
        async with httpx.AsyncClient(timeout=5.0) as client:
            # - Sends the JSON body to the selected webhook destination.
            response = await client.post(destination, json=payload)
            # - Treats non-success HTTP status codes as delivery failures.
            response.raise_for_status()
    # - Logs HTTP transport and status failures, then re-raises them to avoid false success.
    except httpx.HTTPError:
        logger.exception("[Alert] Failed to deliver alert subject=%s", subject)
        raise


# - Converts a collection of CSM SLA breaches into one routed notification.
# - Architectural Purpose: Batches related student issues into an actionable team alert.
# - Plain-English: 'Tell the CSM team which students need follow-up.'
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

    # - Sends the batch through the shared delivery path with its breach count as structured metadata.
    await send_alert(
        "CSM SLA Breach Alert",
        summary,
        {"breach_count": len(breaches)},
        webhook_url=CSM_ALERT_WEBHOOK_URL,
    )
