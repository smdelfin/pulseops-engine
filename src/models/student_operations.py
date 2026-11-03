# - Imports SQLAlchemy types and schema objects for operational payment and offboarding tables.
# - Architectural Purpose: Database constraints and indexes enforce invariants even for writes outside the API.
# - Plain-English: 'Bring in the building blocks for safe, queryable workflow records.'
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
# - Imports the PostgreSQL-side clock function for database-generated timestamps.
# - Architectural Purpose: Server timestamps remain consistent across API and worker instances.
# - Plain-English: 'Let the database fill in record creation times.'
from sqlalchemy.sql import func

# - Imports the common declarative base that registers this model with application metadata.
# - Architectural Purpose: Ensures migrations and runtime ORM queries share the same schema definition.
# - Plain-English: 'Attach these records to the application's database model.'
from src.core.db import Base


# - Maps provider payment updates to a separate durable table.
# - Architectural Purpose: Payment history remains auditable without overloading the student lifecycle row.
# - Plain-English: 'Store each payment update as its own record.'
class PaymentEvent(Base):
    # - Sets the physical table name used by SQLAlchemy and Alembic.
    __tablename__ = "payment_events"
    # - Declares database-level uniqueness, validation checks, and a query-oriented composite index.
    # - Architectural Purpose: Protects data integrity for all writers and supports common status/time lookups.
    # - Plain-English: 'Make duplicate payments and invalid financial values impossible to store.'
    __table_args__ = (
        # - Prevents one provider payment from being recorded more than once.
        UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"),
        # - Restricts persisted payment states to the same explicit vocabulary accepted by the webhook.
        CheckConstraint(
            "status IN ('pending', 'processing', 'succeeded', 'paid', 'failed', "
            "'past_due', 'declined', 'refunded', 'cancelled')",
            name="ck_payment_events_status",
        ),
        # - Allows an omitted amount but blocks negative monetary values.
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_payment_events_amount"),
        # - Allows an omitted currency but requires a canonical uppercase code when supplied.
        CheckConstraint(
            "currency IS NULL OR currency = upper(currency)",
            name="ck_payment_events_currency_upper",
        ),
        # - Speeds queries that filter by payment status and sort or bound by occurrence time.
        Index("ix_payment_events_status_occurred_at", "status", "occurred_at"),
    )

    # - Provides a database-generated primary key for the payment event.
    id = Column(Integer, primary_key=True)
    # - Associates the payment with a student and cascades cleanup if that student is deleted.
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    # - Names the payment provider for uniqueness scope and operational reporting.
    provider = Column(String, nullable=False)
    # - Stores the provider's stable payment identifier for deduplication.
    provider_payment_id = Column(String, nullable=False)
    # - Persists the normalized status while the check constraint guards allowed values.
    status = Column(String, nullable=False)
    # - Stores an optional exact decimal amount with two fractional digits.
    amount = Column(Numeric(12, 2), nullable=True)
    # - Stores an optional three-character ISO-style currency code.
    currency = Column(String(3), nullable=True)
    # - Retains provider failure detail for support and operational review.
    failure_reason = Column(Text, nullable=True)
    # - Records when the provider says the payment event occurred.
    occurred_at = Column(DateTime, nullable=True)
    # - Records database insertion time independently of provider event time.
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# - Maps the operational checklist for a refund or cancellation.
# - Architectural Purpose: Tracks offboarding tasks independently from the student's terminal lifecycle status.
# - Plain-English: 'Keep a checklist for finishing a student's departure.'
class OffboardingCase(Base):
    # - Sets the physical table name for offboarding workflow cases.
    __tablename__ = "offboarding_cases"

    # - Provides a local database identity for the case.
    id = Column(Integer, primary_key=True)
    # - Links the case to its student and indexes case lookup by student.
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    # - Stores the business reason that initiated offboarding.
    reason = Column(String, nullable=False)
    # - Tracks workflow progress and indexes operational status queues.
    status = Column(String, nullable=False, default="open", index=True)
    # - Records whether required access has been revoked.
    access_revoked = Column(Boolean, nullable=False, default=False)
    # - Records whether the final student communication has been sent.
    final_communication_sent = Column(Boolean, nullable=False, default=False)
    # - Remains empty until the offboarding checklist is completed.
    completed_at = Column(DateTime, nullable=True)
    # - Uses the database clock to record case creation time.
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
