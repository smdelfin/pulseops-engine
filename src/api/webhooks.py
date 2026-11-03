# Import cryptography, serialization, logging, and typing tools used by webhook handlers.
import hashlib
import hmac
import json
import logging
from uuid import uuid4
from typing import ClassVar, Optional

# Import FastAPI request primitives and Pydantic validation models for the HTTP boundary.
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
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


# - Defines the strict schema for provider payment notifications.
# - Architectural Purpose: Validates and canonicalizes financial inputs before the request can mutate durable records.
# - Plain-English: 'Check the payment message has usable, supported values.'
class PaymentWebhook(BaseModel):
    # - Rejects unknown keys so unexpected provider fields do not silently enter business logic.
    model_config = ConfigDict(extra="forbid")
    # - Lists supported payment states as immutable class-level validation data.
    # - Architectural Purpose: Keeps accepted API states aligned with ORM and PostgreSQL checks.
    # - Plain-English: 'Allow only the payment statuses this system understands.'
    ALLOWED_STATUSES: ClassVar[frozenset[str]] = frozenset({
        "pending",
        "processing",
        "succeeded",
        "paid",
        "failed",
        "past_due",
        "declined",
        "refunded",
        "cancelled",
    })

    # - Identifies the local student associated with the payment.
    ghl_contact_id: str = Field(min_length=1, max_length=200)
    # - Requires a bounded integration name for idempotency scope and reporting.
    provider: str = Field(min_length=1, max_length=80)
    # - Requires the stable provider payment key used to prevent duplicate payment records.
    provider_payment_id: str = Field(min_length=1, max_length=200)
    # - Restricts raw status text length before allowlist normalization.
    status: str = Field(min_length=1, max_length=40)
    # - Accepts an optional amount while rejecting negative values during schema validation.
    amount: float | None = Field(default=None, ge=0)
    # - Accepts an optional three-character code that is further normalized by a validator.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    # - Retains optional provider context while bounding its size.
    failure_reason: str | None = Field(default=None, max_length=500)

    # - Runs status normalization before the parsed model is used by handlers.
    # - Architectural Purpose: Gives integrations a stable internal vocabulary despite casing and whitespace differences.
    # - Plain-English: 'Clean up the status text and reject states we do not support.'
    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        # - Strips surrounding whitespace and lowercases provider status text.
        normalized = value.strip().lower()
        # - Rejects values outside the domain's supported payment state set.
        if normalized not in cls.ALLOWED_STATUSES:
            raise ValueError(f"Unsupported payment status: {value}")
        # - Returns the canonical status used for persistence and event naming.
        return normalized

    # - Normalizes currency before Pydantic applies its declared length constraints.
    # - Architectural Purpose: Accepts harmless provider formatting while satisfying PostgreSQL's uppercase invariant.
    # - Plain-English: 'Trim and capitalize the currency before checking it is a three-letter code.'
    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        # - Preserves an omitted optional currency without inventing a default.
        if value is None:
            return None
        # - Removes outer whitespace and canonicalizes case before storage.
        normalized = value.strip().upper()
        # - Requires exactly three alphabetic characters such as USD or EUR.
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Currency must be a three-letter ISO-style code")
        # - Returns a database-compatible canonical value.
        return normalized


# - Defines the strict request contract for refund and cancellation events.
# - Architectural Purpose: Validates financial offboarding commands before opening a database transaction.
# - Plain-English: 'Check the departure request identifies a student, reason, and supported action.'
class OffboardingWebhook(BaseModel):
    # - Rejects extra request fields to keep the external contract explicit.
    model_config = ConfigDict(extra="forbid")

    # - Identifies the student whose enrollment is being ended.
    ghl_contact_id: str = Field(min_length=1, max_length=200)
    # - Requires a bounded business explanation for audit history and support.
    reason: str = Field(min_length=1, max_length=200)
    # - Limits the command to the two implemented offboarding outcomes.
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


def _require_event_id(request: Request) -> str:
    # Require the provider's stable identifier so retries can be deduplicated safely.
    # - Reads the canonical webhook event identifier from request headers.
    # - Architectural Purpose: Stable IDs let inbox persistence recognize provider retries.
    # - Plain-English: 'Get the provider's unique name for this event.'
    event_id = request.headers.get("X-Webhook-Event-Id")
    # - Stops processing before database work when the idempotency key is absent.
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing webhook event ID")
    # - Returns the validated identifier for inbox and response correlation.
    return event_id


@app.post("/webhooks/ghl/deal-won")
async def ghl_deal_won(request: Request):
    # Read raw bytes so signature verification covers precisely the transmitted payload.
    raw_body = await request.body()
    # Authenticate the event before trusting any business fields.
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    # Validate and deserialize the authenticated JSON using the strict Pydantic schema.
    payload = GHLWebhook.model_validate_json(raw_body)
    # - Uses the provider event ID when present and creates a fallback key for non-financial intake.
    # - Architectural Purpose: Enables inbox deduplication for GHL deal-won notifications.
    # - Plain-English: 'Give this intake event an identifier so retries can be recognized.'
    provider_event_id = request.headers.get("X-Webhook-Event-Id") or str(uuid4())

    # Scope the database session to this webhook and guarantee cleanup afterward.
    async with SessionLocal() as session:
        # - Groups persistence and validation errors so partial work can be rolled back.
        try:
            # Lock the matching row so concurrent duplicate webhooks serialize their decision.
            result = await session.execute(
                # - Builds a parameterized query for the student's external GHL identity.
                select(Student)
                # - Restricts lookup to the contact that sent this event.
                .where(Student.ghl_contact_id == payload.ghl_contact_id)
                # - Acquires a row lock so concurrent deliveries cannot provision the same record simultaneously.
                .with_for_update()
            )
            # Extract the one matching student or None when this is a first-time contact.
            student = result.scalar_one_or_none()
            # - Looks up a previously recorded receipt for the same provider event.
            duplicate_event = await session.scalar(
                # - Queries the inbox by provider and stable event ID.
                select(InboxEvent).where(
                    InboxEvent.provider == "ghl",
                    InboxEvent.provider_event_id == provider_event_id,
                )
            )
            # - Returns success-shaped duplicate status without repeating business effects.
            if duplicate_event:
                return {"status": "duplicate", "event_id": provider_event_id}
            # - Creates the student only when no matching external contact exists.
            if student is None:
                # Create the initial queued record before publishing asynchronous work.
                student = Student(
                    # - Copies validated provider fields into the new source-of-truth record.
                    name=payload.name,
                    ghl_contact_id=payload.ghl_contact_id,
                    cohort=payload.cohort,
                    # - Selects the least-loaded configured CSM, or leaves intake unassigned when no pool exists.
                    assigned_csm_id=(
                        await csm_allocator.get_next_csm(session)
                        if csm_allocator
                        else None
                    ),
                    # - Starts newly accepted intake in the queue lifecycle state.
                    status="queued",
                )
                # Stage the insert and force the database to allocate the primary key now.
                session.add(student)
                await session.flush()
                session.add(StudentTransition(
                    # - Links the initial lifecycle history row to the newly created student.
                    student_id=student.id,
                    # - Uses null to represent the absence of a prior state.
                    from_status=None,
                    # - Stores the new queued state using the domain enum's serialized value.
                    to_status=StudentStatus.QUEUED.value,
                    # - Derives the event category from the same domain event vocabulary.
                    event_type=StudentDomainEvent(
                        event_type="student.queued",
                        aggregate_id=student.id,
                        payload={"source": "ghl.deal-won"},
                    ).event_type,
                ))
            # - Treats already-linked or active/completed records as duplicate intake.
            elif student.clickup_task_id or student.status in {"queued", "processing", "completed"}:
                # Roll back the read transaction and report an idempotent duplicate response.
                await session.rollback()
                return {"status": "duplicate", "student_id": student.id}
            else:
                # Reopen an existing incomplete record for another provisioning attempt.
                try:
                    # - Validates that the existing lifecycle state may be re-queued.
                    target_status = transition_status(student.status, StudentStatus.QUEUED)
                except InvalidStudentTransition as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                session.add(StudentTransition(
                    # - Persists the before/after status pair for audit history.
                    student_id=student.id,
                    from_status=student.status,
                    to_status=target_status.value,
                    event_type="student.queued",
                ))
                # - Updates the current source-of-truth status after transition validation.
                student.status = target_status.value

            # Commit the source-of-truth state before enqueueing work.
            # - Records the provider event so future webhook retries can be deduplicated.
            session.add(InboxEvent(
                provider="ghl",
                provider_event_id=provider_event_id,
                payload=payload.model_dump(),
                processed_at=None,
            ))
            # - Stages an outgoing provisioning request in the same transaction as the student update.
            session.add(OutboxEvent(
                id=str(uuid4()),
                event_type="student.provisioning.requested",
                aggregate_id=student.id,
                payload={"id": student.id},
            ))
            # - Commits student state, audit history, inbox receipt, and outbox command atomically.
            await session.commit()
            # Capture the identifier after commit for the queue payload and response.
            student_id = student.id
        except Exception:
            # Undo partial persistence and convert unexpected storage failures to HTTP 500.
            await session.rollback()
            logger.exception("Failed to persist GHL webhook")
            raise HTTPException(status_code=500, detail="Internal Server Error")

    # - Opens a fresh session to publish the already-committed outbox event.
    # - Architectural Purpose: Separates durable state mutation from external queue delivery.
    # - Plain-English: 'After saving the work request, try sending it to the queue.'
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
    # - Reads exact request bytes so HMAC verification uses the provider's original payload.
    raw_body = await request.body()
    # - Verifies the configured GHL signing secret before parsing payment details.
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    # - Validates payment identifiers, status, amount, and currency before opening persistence work.
    payload = PaymentWebhook.model_validate_json(raw_body)
    # - Requires the stable provider event key used for financial idempotency.
    provider_event_id = _require_event_id(request)

    # - Scopes one transaction/session to payment lookup and updates.
    async with SessionLocal() as session:
        # - Checks whether this exact provider event has already been processed.
        duplicate = await session.scalar(
            # - Restricts duplicate detection to the provider and its event identifier.
            select(InboxEvent).where(
                InboxEvent.provider == payload.provider,
                InboxEvent.provider_event_id == provider_event_id,
            )
        )
        # - Returns a duplicate response without repeating payment or lifecycle effects.
        if duplicate:
            return {"status": "duplicate", "event_id": provider_event_id}

        # - Locks the target student so concurrent payment events cannot race its lifecycle status.
        student = await session.scalar(
            select(Student).where(Student.ghl_contact_id == payload.ghl_contact_id).with_for_update()
        )
        # - Rejects an event that references no known student.
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        # - Checks provider payment identity independently from webhook event identity.
        existing_payment = await session.scalar(
            # - Finds a payment already stored under this provider/payment pair.
            select(PaymentEvent).where(
                PaymentEvent.provider == payload.provider,
                PaymentEvent.provider_payment_id == payload.provider_payment_id,
            )
        )
        # - Avoids duplicating financial records even if a provider retries with a new event ID.
        if existing_payment:
            return {"status": "duplicate", "payment_id": existing_payment.id}

        # - Stages the normalized payment facts as an independent audit record.
        session.add(PaymentEvent(
            student_id=student.id,
            provider=payload.provider,
            provider_payment_id=payload.provider_payment_id,
            status=payload.status.lower(),
            amount=payload.amount,
            currency=payload.currency.upper() if payload.currency else None,
            failure_reason=payload.failure_reason,
        ))
        # - Stores the stable webhook receipt in the same database transaction.
        session.add(InboxEvent(
            provider=payload.provider,
            provider_event_id=provider_event_id,
            payload=payload.model_dump(),
        ))
        # - Escalates failed payment states into the at-risk student lifecycle.
        if payload.status.lower() in {"failed", "past_due", "declined"}:
            try:
                # - Enforces the lifecycle rules before applying a risk status.
                target_status = transition_status(student.status, StudentStatus.AT_RISK)
            except InvalidStudentTransition as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            session.add(StudentTransition(
                # - Records the state change and provider failure context for audit.
                student_id=student.id,
                from_status=student.status,
                to_status=target_status.value,
                event_type="payment.failed",
                reason=payload.failure_reason,
            ))
            # - Updates the current student state to the validated risk status.
            student.status = target_status.value
        # - Stages a durable downstream notification for the payment outcome.
        session.add(OutboxEvent(
            id=str(uuid4()),
            event_type=f"payment.{payload.status.lower()}",
            aggregate_id=student.id,
            payload={"student_id": student.id, "payment_id": payload.provider_payment_id},
        ))
        # - Commits payment facts, inbox receipt, lifecycle change, and outbound command atomically.
        await session.commit()

    # - Publishes any due outbox messages after the database transaction has committed.
    async with SessionLocal() as session:
        await outbox_service.publish_pending(session)
    # - Confirms acceptance and returns identifiers for provider-side correlation.
    return {"status": "accepted", "student_id": student.id, "event_id": provider_event_id}


@app.post("/webhooks/offboarding")
async def offboarding_updated(request: Request):
    # - Captures raw bytes for signature validation against the exact provider payload.
    raw_body = await request.body()
    # - Rejects unauthenticated requests before interpreting the requested action.
    _verify_signature(raw_body, request.headers.get("X-Webhook-Signature"), settings.GHL_WEBHOOK_SECRET)
    # - Validates contact, reason, and refund/cancel action against the strict request schema.
    payload = OffboardingWebhook.model_validate_json(raw_body)
    # - Requires a stable provider event ID so retries remain idempotent.
    provider_event_id = _require_event_id(request)
    # - Maps the validated action to its explicit terminal lifecycle outcome.
    target_status = StudentStatus.REFUNDED if payload.action == "refund" else StudentStatus.CANCELLED

    # - Keeps duplicate check, transition, case, and outbox writes within one async session.
    async with SessionLocal() as session:
        # - Checks whether this provider event was already recorded in the inbox.
        duplicate = await session.scalar(
            # - Scopes the deduplication lookup to GHL and this event identifier.
            select(InboxEvent).where(
                InboxEvent.provider == "ghl",
                InboxEvent.provider_event_id == provider_event_id,
            )
        )
        # - Makes a retry safe by returning without repeating side effects.
        if duplicate:
            return {"status": "duplicate", "event_id": provider_event_id}
        # - Finds and locks the target student for consistent lifecycle mutation.
        student = await session.scalar(
            select(Student).where(Student.ghl_contact_id == payload.ghl_contact_id).with_for_update()
        )
        # - Returns not-found when the external contact does not map to a student.
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        # - Validates both the intermediate offboarding state and requested terminal state.
        try:
            # - Retains the old value so the audit chain records the transition origin.
            current_status = student.status
            # - Checks entry into the offboarding workflow is permitted.
            offboarding_status = transition_status(current_status, StudentStatus.OFFBOARDING)
            # - Checks the terminal refund/cancellation follows the intermediate state.
            target = transition_status(StudentStatus.OFFBOARDING, target_status)
        except InvalidStudentTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        # - Avoids writing a redundant intermediate audit row if already offboarding.
        if current_status != offboarding_status.value:
            session.add(StudentTransition(
                # - Stores the student's prior state and transition destination.
                student_id=student.id,
                from_status=current_status,
                to_status=offboarding_status.value,
                event_type="student.offboarding",
                reason=payload.reason,
                correlation_id=provider_event_id,
            ))
        # - Applies the validated terminal state to the student record.
        student.status = target.value
        # - Creates an operational checklist for follow-up work.
        session.add(OffboardingCase(
            student_id=student.id,
            reason=payload.reason,
            status="open",
        ))
        # - Records the final transition and correlates it with the original provider event.
        session.add(StudentTransition(
            student_id=student.id,
            from_status=StudentStatus.OFFBOARDING.value,
            to_status=target.value,
            event_type=f"student.{payload.action}",
            reason=payload.reason,
            correlation_id=provider_event_id,
        ))
        # - Persists the inbound event receipt for retry deduplication.
        session.add(InboxEvent(
            provider="ghl",
            provider_event_id=provider_event_id,
            payload=payload.model_dump(),
        ))
        # - Persists the downstream refund/cancellation command transactionally.
        session.add(OutboxEvent(
            id=str(uuid4()),
            event_type=f"offboarding.{payload.action}",
            aggregate_id=student.id,
            payload={"student_id": student.id, "reason": payload.reason},
        ))
        # - Commits lifecycle, audit, case, inbox, and outbox records as one unit.
        await session.commit()

    # - Attempts publication after durable database state exists.
    async with SessionLocal() as session:
        await outbox_service.publish_pending(session)
    # - Returns the accepted student and provider event identifiers.
    return {"status": "accepted", "student_id": student.id, "event_id": provider_event_id}
