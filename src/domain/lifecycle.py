# - Imports the dataclass decorator and field factory for immutable event records.
# - Architectural Purpose: Keeps domain events lightweight and independent of persistence or web frameworks.
# - Plain-English: 'Bring in tools for defining a simple, structured event object.'
from dataclasses import dataclass, field
# - Imports timezone-aware date handling for event timestamps.
# - Architectural Purpose: UTC timestamps make events comparable across services and deployments.
# - Plain-English: 'Use dates that have an explicit global time reference.'
from datetime import datetime, timezone
# - Imports Enum so lifecycle values are finite and type-safe.
# - Architectural Purpose: A shared enum prevents arbitrary status strings from drifting between layers.
# - Plain-English: 'Define a fixed menu of student statuses.'
from enum import Enum
# - Imports Any for domain-event payloads that can contain provider-specific fields.
# - Architectural Purpose: Keeps the event envelope stable while allowing typed-by-consumer payload details.
# - Plain-English: 'Allow event details to carry different kinds of data.'
from typing import Any
# - Imports UUID generation for event identifiers.
# - Architectural Purpose: Globally unique IDs make asynchronous messages traceable and deduplicable.
# - Plain-English: 'Give each event its own identifier.'
from uuid import uuid4


# - Declares the canonical set of student lifecycle states as string enum members.
# - Architectural Purpose: String values persist cleanly to PostgreSQL and serialize consistently in APIs.
# - Plain-English: 'List the statuses a student can have.'
class StudentStatus(str, Enum):
    # - Represents intake that has not yet entered queue processing.
    # - Architectural Purpose: Separates accepted work from work claimed by a worker.
    # - Plain-English: 'The student is waiting to be processed.'
    PENDING = "pending"
    # - Represents work accepted by the durable provisioning queue.
    # - Architectural Purpose: Makes queue admission visible independently of execution.
    # - Plain-English: 'The student is waiting in the work queue.'
    QUEUED = "queued"
    # - Represents a worker currently handling provisioning.
    # - Architectural Purpose: Supports operational dashboards and stale-work auditing.
    # - Plain-English: 'A worker is doing the setup now.'
    PROCESSING = "processing"
    # - Represents that the onboarding workflow has begun.
    # - Architectural Purpose: Distinguishes initial setup from the broader completed lifecycle.
    # - Plain-English: 'The student's onboarding is underway.'
    ONBOARDING_STARTED = "onboarding_started"
    # - Represents successful completion of onboarding.
    # - Architectural Purpose: Provides a stable terminal state for reporting and assignment counts.
    # - Plain-English: 'The student has finished onboarding.'
    COMPLETED = "completed"
    # - Represents a student requiring intervention, such as a payment issue.
    # - Architectural Purpose: Routes operational attention without conflating risk with processing failure.
    # - Plain-English: 'The student needs someone to follow up.'
    AT_RISK = "at_risk"
    # - Represents an active refund or cancellation workflow.
    # - Architectural Purpose: Records offboarding work before its terminal outcome is committed.
    # - Plain-English: 'The student is being offboarded.'
    OFFBOARDING = "offboarding"
    # - Represents a completed refund outcome.
    # - Architectural Purpose: Preserves financial and lifecycle outcome semantics separately from cancellation.
    # - Plain-English: 'The student has been refunded.'
    REFUNDED = "refunded"
    # - Represents a completed cancellation outcome.
    # - Architectural Purpose: Allows analytics to distinguish cancellation from refund.
    # - Plain-English: 'The student's enrollment was cancelled.'
    CANCELLED = "cancelled"
    # - Represents unsuccessful workflow processing that may be retried or reviewed.
    # - Architectural Purpose: Separates technical failure from business risk.
    # - Plain-English: 'The setup did not complete successfully.'
    FAILED = "failed"


# - Groups lifecycle values that should not return to ordinary onboarding.
# - Architectural Purpose: Centralizes terminal-state semantics for lifecycle consumers.
# - Plain-English: 'Identify statuses treated as finished outcomes.'
TERMINAL_STATUSES = {
    # - Marks completed onboarding as a terminal outcome.
    StudentStatus.COMPLETED,
    # - Marks a refund as a terminal outcome.
    StudentStatus.REFUNDED,
    # - Marks cancellation as a terminal outcome.
    StudentStatus.CANCELLED,
}

# - Maps each current lifecycle state to its permitted next states.
# - Architectural Purpose: Enforces business transitions consistently before database writes.
# - Plain-English: 'Specify which next steps are valid for every status.'
ALLOWED_TRANSITIONS = {
    # - Pending intake can enter processing, be queued, or stop due to failure/cancellation.
    StudentStatus.PENDING: {
        StudentStatus.QUEUED,
        StudentStatus.PROCESSING,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    # - Queued work can be claimed, started, returned to pending, or closed.
    StudentStatus.QUEUED: {
        StudentStatus.PROCESSING,
        StudentStatus.ONBOARDING_STARTED,
        StudentStatus.PENDING,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    # - Processing work may begin onboarding, complete, return to the queue, or close.
    StudentStatus.PROCESSING: {
        StudentStatus.ONBOARDING_STARTED,
        StudentStatus.COMPLETED,
        StudentStatus.QUEUED,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    # - Active onboarding can complete, become at risk, begin offboarding, or stop.
    StudentStatus.ONBOARDING_STARTED: {
        StudentStatus.COMPLETED,
        StudentStatus.AT_RISK,
        StudentStatus.OFFBOARDING,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    # - At-risk students can recover or proceed to an offboarding outcome.
    StudentStatus.AT_RISK: {
        StudentStatus.ONBOARDING_STARTED,
        StudentStatus.COMPLETED,
        StudentStatus.OFFBOARDING,
        StudentStatus.CANCELLED,
    },
    # - Failed work can be retried through the queue or cancelled.
    StudentStatus.FAILED: {StudentStatus.QUEUED, StudentStatus.CANCELLED},
    # - Offboarding must resolve to a refund, cancellation, or completed state.
    StudentStatus.OFFBOARDING: {StudentStatus.REFUNDED, StudentStatus.CANCELLED, StudentStatus.COMPLETED},
    # - Completed students may only re-enter the managed offboarding process.
    StudentStatus.COMPLETED: {StudentStatus.OFFBOARDING},
    # - Refunded records cannot transition further.
    StudentStatus.REFUNDED: set(),
    # - Cancelled records cannot transition further.
    StudentStatus.CANCELLED: set(),
}


# - Defines a domain-specific validation error for unsupported lifecycle changes.
# - Architectural Purpose: Lets API and worker boundaries distinguish business-rule failures from infrastructure errors.
# - Plain-English: 'Raise a clear error when a status change is not allowed.'
class InvalidStudentTransition(ValueError):
    # - Inherits ValueError behavior without changing its standard exception handling.
    # - Architectural Purpose: Keeps invalid state changes compatible with ordinary input-validation handling.
    # - Plain-English: 'Treat an invalid transition like invalid input.'
    pass


# - Converts a persisted string or existing enum value into the canonical enum type.
# - Architectural Purpose: Normalizes values arriving from APIs, databases, and integrations at one domain boundary.
# - Plain-English: 'Turn incoming status text into one of the known statuses.'
def parse_status(value: str | StudentStatus) -> StudentStatus:
    # - Handles conversion and passes through values already parsed by the domain.
    try:
        # - Reuses enum instances or constructs one from its serialized string value.
        return value if isinstance(value, StudentStatus) else StudentStatus(value)
    # - Converts the enum's unknown-value error into the lifecycle-specific exception.
    except ValueError as exc:
        # - Preserves the original error as a cause for debugging while exposing a domain-level message.
        raise InvalidStudentTransition(f"Unknown student status: {value}") from exc


# - Validates a proposed transition and returns its normalized target state.
# - Architectural Purpose: Centralizes state-machine enforcement before ORM mutation or event publication.
# - Plain-English: 'Check whether the requested next status is allowed.'
def transition_status(
    # - Accepts either database/API strings or already parsed lifecycle values.
    current: str | StudentStatus,
    # - Describes the requested destination state.
    target: str | StudentStatus,
) -> StudentStatus:
    # - Normalize the current value so subsequent membership checks use enum keys.
    current_status = parse_status(current)
    # - Normalize the destination value before comparing it with allowed transitions.
    target_status = parse_status(target)
    # - Treat a repeated status as an idempotent no-op.
    if target_status == current_status:
        return target_status
    # - Reject any destination absent from the current state's transition set.
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        # - Include both states in the error so logs and API responses explain the rejected operation.
        raise InvalidStudentTransition(
            f"Cannot transition student from {current_status.value} to {target_status.value}"
        )
    # - Return the validated enum for the caller to persist or publish.
    return target_status


# - Defines an immutable envelope for events emitted by student-domain workflows.
# - Architectural Purpose: A stable envelope supports the transactional outbox and cross-service tracing.
# - Plain-English: 'Give every student event a consistent shape.'
@dataclass(frozen=True)
class StudentDomainEvent:
    # - Identifies the kind of business event, such as a queued or completed transition.
    event_type: str
    # - Carries the primary key of the student aggregate that emitted the event.
    aggregate_id: int
    # - Stores event-specific details without changing the common envelope.
    payload: dict[str, Any]
    # - Generates an independent event identifier when the caller does not provide one.
    event_id: str = field(default_factory=lambda: str(uuid4()))
    # - Captures event creation time in timezone-aware UTC.
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # - Optionally links related events to a webhook request or workflow trace.
    correlation_id: str | None = None

    # - Converts the immutable domain event into JSON-serializable primitive values.
    # - Architectural Purpose: The outbox and queue require a transport-friendly representation.
    # - Plain-English: 'Package the event fields into a dictionary for delivery.'
    def as_dict(self) -> dict[str, Any]:
        # - Return the envelope while formatting the timestamp as an ISO-8601 string.
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
        }
