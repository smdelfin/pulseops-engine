# Import cryptography, serialization, logging, and typing tools used by webhook handlers.
import hashlib
import hmac
import json
import logging
from typing import Optional

# Import FastAPI request primitives and Pydantic validation models for the HTTP boundary.
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
# Import SQLAlchemy's query builder for async, parameterized ORM lookups.
from sqlalchemy import select

# Import shared settings, database sessions, the Student entity, and queue abstraction.
from src.core.config import settings
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.queue_service import QueueService

# Configure a useful default log level for local runs and container diagnostics.
logging.basicConfig(level=logging.INFO)
# Create a module logger so failures include the webhook subsystem identity.
logger = logging.getLogger(__name__)

# Construct the FastAPI application object that owns route registration and validation.
app = FastAPI(title="PulseOps-Engine API")
# Construct the queue facade once so handlers reuse its client configuration.
queue_service = QueueService()


@app.get("/health")
async def health():
    # Return a small success document used by Docker/Azure probes to test process liveness.
    return {"status": "ok"}


# Define the strict input contract for a GoHighLevel deal-won event.
class GHLWebhook(BaseModel):
    # Reject unexpected fields so integration drift is visible instead of silently accepted.
    model_config = ConfigDict(extra="forbid")

    # Validate a bounded student name before it reaches persistence or ClickUp.
    name: str = Field(min_length=1, max_length=200)
    # Validate the external contact key used for idempotent database lookup.
    ghl_contact_id: str = Field(min_length=1, max_length=200)
    # Supply a stable cohort default for senders that omit optional segmentation.
    cohort: Optional[str] = Field(default="Default", max_length=200)


# Define the subset of ClickUp history entries needed to detect status changes.
class ClickUpHistoryItem(BaseModel):
    # Ignore provider fields unrelated to synchronization.
    model_config = ConfigDict(extra="ignore")

    # Identify which ClickUp field changed.
    field: str
    # Hold the provider's new field value as a JSON object.
    after: dict


# Define the ClickUp event envelope consumed by the synchronization route.
class ClickUpWebhook(BaseModel):
    # Accept provider extensions because ClickUp can add event metadata over time.
    model_config = ConfigDict(extra="ignore")

    # Carry the external task key used to find the local Student row.
    task_id: str
    # Preserve the event kind for validation/documentation even when routing is path-based.
    event: str
    # Keep the history list optional so non-status events can be ignored cleanly.
    history_items: list[ClickUpHistoryItem] = []


# Verify a provider HMAC before parsing or acting on an inbound webhook.
def _verify_signature(raw_body: bytes, received: str | None, secret: str) -> None:
    # Reject unsigned requests at the HTTP boundary.
    if not received:
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    # Recompute the SHA-256 digest from the exact bytes sent by the provider.
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    # Compare in constant time to reduce timing side-channel leakage.
    if not hmac.compare_digest(expected, received.removeprefix("sha256=")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@app.post("/webhooks/ghl/deal-won")
async def ghl_deal_won(request: Request):
    # Read raw bytes so signature verification covers precisely the transmitted payload.
    raw_body = await request.body()
    # Authenticate the event before trusting any business fields.
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    # Validate and deserialize the authenticated JSON using the strict Pydantic schema.
    payload = GHLWebhook.model_validate_json(raw_body)

    # Scope the database session to this webhook and guarantee cleanup afterward.
    async with SessionLocal() as session:
        try:
            # Lock the matching row so concurrent duplicate webhooks serialize their decision.
            result = await session.execute(
                select(Student)
                .where(Student.ghl_contact_id == payload.ghl_contact_id)
                .with_for_update()
            )
            # Extract the one matching student or None when this is a first-time contact.
            student = result.scalar_one_or_none()
            if student is None:
                # Create the initial queued record before publishing asynchronous work.
                student = Student(
                    name=payload.name,
                    ghl_contact_id=payload.ghl_contact_id,
                    status="queued",
                )
                # Stage the insert and force the database to allocate the primary key now.
                session.add(student)
                await session.flush()
            elif student.clickup_task_id or student.status in {"queued", "processing", "completed"}:
                # Roll back the read transaction and report an idempotent duplicate response.
                await session.rollback()
                return {"status": "duplicate", "student_id": student.id}
            else:
                # Reopen an existing incomplete record for another provisioning attempt.
                student.status = "queued"

            # Commit the source-of-truth state before enqueueing work.
            await session.commit()
            # Capture the identifier after commit for the queue payload and response.
            student_id = student.id
        except Exception:
            # Undo partial persistence and convert unexpected storage failures to HTTP 500.
            await session.rollback()
            logger.exception("Failed to persist GHL webhook")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    try:
        # Publish only the stable identifier; the worker reloads current state from PostgreSQL.
        await queue_service.push_message(json.dumps({"id": student_id}))
    except Exception:
        # Reopen a short transaction to expose that durable queue delivery did not occur.
        async with SessionLocal() as session:
            result = await session.execute(select(Student).where(Student.id == student_id).with_for_update())
            # Find and lock the record before transitioning it back to a retryable state.
            queued_student = result.scalar_one_or_none()
            if queued_student and not queued_student.clickup_task_id:
                # Mark the record pending so recovery tooling can safely requeue it.
                queued_student.status = "pending"
                await session.commit()
        # Preserve the original infrastructure error in logs while returning a stable API response.
        logger.exception("Failed to enqueue student provisioning")
        raise HTTPException(status_code=503, detail="Provisioning queue unavailable")

    # Confirm acceptance only after both database persistence and queue publication succeeded.
    return {"status": "accepted", "student_id": student_id}


@app.post("/webhooks/clickup/task-updated")
async def clickup_task_updated(request: Request):
    # Read raw provider bytes for signature validation.
    raw_body = await request.body()
    # Authenticate ClickUp before applying an external status to local state.
    _verify_signature(
        raw_body,
        request.headers.get("X-Webhook-Signature"),
        settings.CLICKUP_WEBHOOK_SECRET,
    )
    # Parse the event into a tolerant provider-specific schema.
    payload = ClickUpWebhook.model_validate_json(raw_body)
    # Locate the first history entry that represents a status transition.
    new_status = next(
        (
            item.after.get("status")
            for item in payload.history_items
            if item.field == "status"
        ),
        None,
    )
    # Ignore updates that do not alter workflow status.
    if not new_status:
        return {"status": "ignored", "reason": "non-status update"}

    # Lock the matching student row while synchronizing its status.
    async with SessionLocal() as session:
        result = await session.execute(
            select(Student).where(Student.clickup_task_id == payload.task_id).with_for_update()
        )
        # Extract the tracked student, if ClickUp sent an unknown task.
        student = result.scalar_one_or_none()
        if not student:
            # Treat unrelated ClickUp tasks as harmless integration noise.
            return {"status": "ignored", "reason": "task not tracked"}
        # Mirror the provider status in the local workflow source of truth.
        student.status = new_status
        # Commit the synchronization atomically.
        await session.commit()
    # Tell the caller which task and status were applied.
    return {"status": "synchronized", "task_id": payload.task_id, "new_status": new_status}
