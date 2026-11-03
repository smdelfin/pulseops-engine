# Import cryptography, serialization, logging, and typing tools used by webhook handlers.
import hashlib
import hmac
import json
import logging
from uuid import uuid4
from typing import Optional

# Import FastAPI request primitives and Pydantic validation models for the HTTP boundary.
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
# Import SQLAlchemy's query builder for async, parameterized ORM lookups.
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

# Import shared settings, database sessions, the Student entity, and queue abstraction.
from src.core.config import settings
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.queue_service import QueueService
from src.domain.lifecycle import InvalidStudentTransition, StudentDomainEvent, StudentStatus, transition_status
from src.models.student_transition import StudentTransition
from src.models.messaging import InboxEvent, OutboxEvent
from src.services.outbox_service import OutboxService
from src.models.student_operations import OffboardingCase, PaymentEvent
from src.services.csm_allocator import CSMAllocator

# Configure a useful default log level for local runs and container diagnostics.
logging.basicConfig(level=logging.INFO)
# Create a module logger so failures include the webhook subsystem identity.
logger = logging.getLogger(__name__)

# Construct the FastAPI application object that owns route registration and validation.
app = FastAPI(title="PulseOps-Engine API")
# Construct the queue facade once so handlers reuse its client configuration.
queue_service = QueueService()
outbox_service = OutboxService(queue_service)
csm_allocator = CSMAllocator(settings.CSM_IDS.split(",")) if settings.CSM_IDS else None

CLICKUP_STATUS_MAP = {
    "to do": StudentStatus.ONBOARDING_STARTED,
    "open": StudentStatus.ONBOARDING_STARTED,
    "in progress": StudentStatus.ONBOARDING_STARTED,
    "complete": StudentStatus.COMPLETED,
    "completed": StudentStatus.COMPLETED,
    "closed": StudentStatus.COMPLETED,
}


@app.get("/health")
async def health():
    # Return a small success document used by Docker/Azure probes to test process liveness.
    return {"status": "ok"}


@app.get("/ready")
async def readiness():
    # Open a short-lived session so readiness reflects the dependency used by request handlers.
    async with SessionLocal() as session:
        try:
            # Execute a minimal round trip to prove the configured database is reachable.
            await session.execute(select(1))
        except SQLAlchemyError as exc:
            # Return a non-success response so orchestrators keep traffic away from an unready instance.
            logger.exception("Readiness database check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
    # Report readiness only after the database dependency has answered successfully.
    return {"status": "ready", "dependencies": {"database": "ok"}}


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


class PaymentWebhook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ghl_contact_id: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=80)
    provider_payment_id: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=40)
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    failure_reason: str | None = Field(default=None, max_length=500)


class OffboardingWebhook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ghl_contact_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(refund|cancel)$")


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
    provider_event_id = request.headers.get("X-Webhook-Event-Id") or str(uuid4())

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
            duplicate_event = await session.scalar(
                select(InboxEvent).where(
                    InboxEvent.provider == "ghl",
                    InboxEvent.provider_event_id == provider_event_id,
                )
            )
            if duplicate_event:
                return {"status": "duplicate", "event_id": provider_event_id}
            if student is None:
                # Create the initial queued record before publishing asynchronous work.
                student = Student(
                    name=payload.name,
                    ghl_contact_id=payload.ghl_contact_id,
                    cohort=payload.cohort,
                    assigned_csm_id=(
                        await csm_allocator.get_next_csm(session)
                        if csm_allocator
                        else None
                    ),
                    status="queued",
                )
                # Stage the insert and force the database to allocate the primary key now.
                session.add(student)
                await session.flush()
                session.add(StudentTransition(
                    student_id=student.id,
                    from_status=None,
                    to_status=StudentStatus.QUEUED.value,
                    event_type=StudentDomainEvent(
                        event_type="student.queued",
                        aggregate_id=student.id,
                        payload={"source": "ghl.deal-won"},
                    ).event_type,
                ))
            elif student.clickup_task_id or student.status in {"queued", "processing", "completed"}:
                # Roll back the read transaction and report an idempotent duplicate response.
                await session.rollback()
                return {"status": "duplicate", "student_id": student.id}
            else:
                # Reopen an existing incomplete record for another provisioning attempt.
                try:
                    target_status = transition_status(student.status, StudentStatus.QUEUED)
                except InvalidStudentTransition as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                session.add(StudentTransition(
                    student_id=student.id,
                    from_status=student.status,
                    to_status=target_status.value,
                    event_type="student.queued",
                ))
                student.status = target_status.value

            # Commit the source-of-truth state before enqueueing work.
            session.add(InboxEvent(
                provider="ghl",
                provider_event_id=provider_event_id,
                payload=payload.model_dump(),
                processed_at=None,
            ))
            session.add(OutboxEvent(
                id=str(uuid4()),
                event_type="student.provisioning.requested",
                aggregate_id=student.id,
                payload={"id": student.id},
            ))
            await session.commit()
            # Capture the identifier after commit for the queue payload and response.
            student_id = student.id
        except Exception:
            # Undo partial persistence and convert unexpected storage failures to HTTP 500.
            await session.rollback()
            logger.exception("Failed to persist GHL webhook")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    async with SessionLocal() as session:
        await outbox_service.publish_pending(session)

    # Confirm acceptance only after both database persistence and queue publication succeeded.
    return {"status": "accepted", "student_id": student_id, "event_id": provider_event_id}


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
    provider_status = next(
        (
            item.after.get("status")
            for item in payload.history_items
            if item.field == "status"
        ),
        None,
    )
    # Ignore updates that do not alter workflow status.
    if not provider_status:
        return {"status": "ignored", "reason": "non-status update"}
    new_status = CLICKUP_STATUS_MAP.get(str(provider_status).strip().lower())
    if not new_status:
        return {"status": "ignored", "reason": "unsupported status"}

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
        try:
            target_status = transition_status(student.status, new_status)
        except InvalidStudentTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        session.add(StudentTransition(
            student_id=student.id,
            from_status=student.status,
            to_status=target_status.value,
            event_type="student.status-synchronized",
        ))
        student.status = target_status.value
        # Commit the synchronization atomically.
        await session.commit()
    # Tell the caller which task and status were applied.
    return {"status": "synchronized", "task_id": payload.task_id, "new_status": target_status.value}


@app.post("/webhooks/payments/updated")
async def payment_updated(request: Request):
    raw_body = await request.body()
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    payload = PaymentWebhook.model_validate_json(raw_body)
    provider_event_id = request.headers.get("X-Webhook-Event-Id") or str(uuid4())

    async with SessionLocal() as session:
        duplicate = await session.scalar(
            select(InboxEvent).where(
                InboxEvent.provider == payload.provider,
                InboxEvent.provider_event_id == provider_event_id,
            )
        )
        if duplicate:
            return {"status": "duplicate", "event_id": provider_event_id}

        student = await session.scalar(
            select(Student).where(Student.ghl_contact_id == payload.ghl_contact_id).with_for_update()
        )
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        existing_payment = await session.scalar(
            select(PaymentEvent).where(
                PaymentEvent.provider == payload.provider,
                PaymentEvent.provider_payment_id == payload.provider_payment_id,
            )
        )
        if existing_payment:
            return {"status": "duplicate", "payment_id": existing_payment.id}

        session.add(PaymentEvent(
            student_id=student.id,
            provider=payload.provider,
            provider_payment_id=payload.provider_payment_id,
            status=payload.status.lower(),
            amount=payload.amount,
            currency=payload.currency.upper() if payload.currency else None,
            failure_reason=payload.failure_reason,
        ))
        session.add(InboxEvent(
            provider=payload.provider,
            provider_event_id=provider_event_id,
            payload=payload.model_dump(),
        ))
        if payload.status.lower() in {"failed", "past_due", "declined"}:
            try:
                target_status = transition_status(student.status, StudentStatus.AT_RISK)
            except InvalidStudentTransition as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            session.add(StudentTransition(
                student_id=student.id,
                from_status=student.status,
                to_status=target_status.value,
                event_type="payment.failed",
                reason=payload.failure_reason,
            ))
            student.status = target_status.value
        session.add(OutboxEvent(
            id=str(uuid4()),
            event_type=f"payment.{payload.status.lower()}",
            aggregate_id=student.id,
            payload={"student_id": student.id, "payment_id": payload.provider_payment_id},
        ))
        await session.commit()

    async with SessionLocal() as session:
        await outbox_service.publish_pending(session)
    return {"status": "accepted", "student_id": student.id, "event_id": provider_event_id}


@app.post("/webhooks/offboarding")
async def offboarding_updated(request: Request):
    raw_body = await request.body()
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    payload = OffboardingWebhook.model_validate_json(raw_body)
    provider_event_id = request.headers.get("X-Webhook-Event-Id") or str(uuid4())
    target_status = StudentStatus.REFUNDED if payload.action == "refund" else StudentStatus.CANCELLED

    async with SessionLocal() as session:
        duplicate = await session.scalar(
            select(InboxEvent).where(
                InboxEvent.provider == "ghl",
                InboxEvent.provider_event_id == provider_event_id,
            )
        )
        if duplicate:
            return {"status": "duplicate", "event_id": provider_event_id}
        student = await session.scalar(
            select(Student).where(Student.ghl_contact_id == payload.ghl_contact_id).with_for_update()
        )
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        try:
            transition_status(student.status, StudentStatus.OFFBOARDING)
            target = transition_status(StudentStatus.OFFBOARDING, target_status)
        except InvalidStudentTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        student.status = target.value
        session.add(OffboardingCase(
            student_id=student.id,
            reason=payload.reason,
            status="open",
        ))
        session.add(StudentTransition(
            student_id=student.id,
            from_status=StudentStatus.OFFBOARDING.value,
            to_status=target.value,
            event_type=f"student.{payload.action}",
            reason=payload.reason,
        ))
        session.add(InboxEvent(
            provider="ghl",
            provider_event_id=provider_event_id,
            payload=payload.model_dump(),
        ))
        session.add(OutboxEvent(
            id=str(uuid4()),
            event_type=f"offboarding.{payload.action}",
            aggregate_id=student.id,
            payload={"student_id": student.id, "reason": payload.reason},
        ))
        await session.commit()

    async with SessionLocal() as session:
        await outbox_service.publish_pending(session)
    return {"status": "accepted", "student_id": student.id, "event_id": provider_event_id}
