from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class StudentStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    ONBOARDING_STARTED = "onboarding_started"
    COMPLETED = "completed"
    AT_RISK = "at_risk"
    OFFBOARDING = "offboarding"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_STATUSES = {
    StudentStatus.COMPLETED,
    StudentStatus.REFUNDED,
    StudentStatus.CANCELLED,
}

ALLOWED_TRANSITIONS = {
    StudentStatus.PENDING: {
        StudentStatus.QUEUED,
        StudentStatus.PROCESSING,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    StudentStatus.QUEUED: {
        StudentStatus.PROCESSING,
        StudentStatus.ONBOARDING_STARTED,
        StudentStatus.PENDING,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    StudentStatus.PROCESSING: {
        StudentStatus.ONBOARDING_STARTED,
        StudentStatus.COMPLETED,
        StudentStatus.QUEUED,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    StudentStatus.ONBOARDING_STARTED: {
        StudentStatus.COMPLETED,
        StudentStatus.AT_RISK,
        StudentStatus.OFFBOARDING,
        StudentStatus.FAILED,
        StudentStatus.CANCELLED,
    },
    StudentStatus.AT_RISK: {
        StudentStatus.ONBOARDING_STARTED,
        StudentStatus.COMPLETED,
        StudentStatus.OFFBOARDING,
        StudentStatus.CANCELLED,
    },
    StudentStatus.FAILED: {StudentStatus.QUEUED, StudentStatus.CANCELLED},
    StudentStatus.OFFBOARDING: {StudentStatus.REFUNDED, StudentStatus.CANCELLED, StudentStatus.COMPLETED},
    StudentStatus.COMPLETED: {StudentStatus.OFFBOARDING},
    StudentStatus.REFUNDED: set(),
    StudentStatus.CANCELLED: set(),
}


class InvalidStudentTransition(ValueError):
    pass


def parse_status(value: str | StudentStatus) -> StudentStatus:
    try:
        return value if isinstance(value, StudentStatus) else StudentStatus(value)
    except ValueError as exc:
        raise InvalidStudentTransition(f"Unknown student status: {value}") from exc


def transition_status(
    current: str | StudentStatus,
    target: str | StudentStatus,
) -> StudentStatus:
    current_status = parse_status(current)
    target_status = parse_status(target)
    if target_status == current_status:
        return target_status
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        raise InvalidStudentTransition(
            f"Cannot transition student from {current_status.value} to {target_status.value}"
        )
    return target_status


@dataclass(frozen=True)
class StudentDomainEvent:
    event_type: str
    aggregate_id: int
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
        }
