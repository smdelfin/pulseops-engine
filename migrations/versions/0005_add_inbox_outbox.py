# - Describes the schema change tracked by this revision.
# - Architectural Purpose: Names the reliability capability this migration adds.
# - Plain-English: 'Add durable records for incoming and outgoing messages.'
"""add durable inbox and outbox messaging records

Revision ID: 0005
Revises: 0004
"""

# - Imports Alembic DDL operations for versioned schema changes.
# - Architectural Purpose: Keeps message-persistence infrastructure reproducible across deployments.
# - Plain-English: 'Use Alembic to create the messaging tables.'
from alembic import op
# - Imports SQLAlchemy schema types for columns and defaults.
# - Architectural Purpose: Defines the database contract without coupling migration history to application code.
# - Plain-English: 'Describe the database fields needed for reliable delivery.'
import sqlalchemy as sa


# - Registers this migration's unique revision identifier.
# - Architectural Purpose: Supports migration state tracking.
# - Plain-English: 'Identify this schema version.'
revision = "0005"
# - Requires schema hardening revision 0004 first.
# - Architectural Purpose: Preserves a single upgrade sequence.
# - Plain-English: 'Apply student schema hardening before messaging storage.'
down_revision = "0004"
# - Declares no separate migration branch.
# - Architectural Purpose: Keeps all changes on one Alembic history line.
# - Plain-English: 'This is part of the main sequence.'
branch_labels = None
# - Declares no extra migration dependencies.
# - Architectural Purpose: Makes migration ordering self-contained and explicit.
# - Plain-English: 'No other migration is required beyond its parent.'
depends_on = None


# - Creates database storage for inbox deduplication and retryable outbox events.
# - Architectural Purpose: Makes provider receipts and outbound work durable across crashes.
# - Plain-English: 'Keep a database record so message retries do not lose work.'
def upgrade() -> None:
    # - Creates the outbound event table used by the transactional outbox.
    op.create_table(
        # - Names the table that tracks pending publications.
        "outbox_events",
        # - Uses a caller-generated stable event ID as the primary key.
        sa.Column("id", sa.String(), primary_key=True),
        # - Stores the event category for routing and filtering.
        sa.Column("event_type", sa.String(), nullable=False),
        # - Stores the business entity identifier related to the event.
        sa.Column("aggregate_id", sa.Integer(), nullable=False),
        # - Persists the structured payload as a JSON value.
        sa.Column("payload", sa.JSON(), nullable=False),
        # - Tracks pending/published state for retry selection.
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        # - Counts attempts for observability and retry policy.
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        # - Schedules the earliest permitted next delivery attempt.
        sa.Column("available_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        # - Records successful queue acceptance time.
        sa.Column("published_at", sa.DateTime(), nullable=True),
        # - Retains the latest delivery error for diagnostics.
        sa.Column("last_error", sa.Text(), nullable=True),
        # - Captures row insertion time using the database clock.
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    # - Indexes event type for operational filtering.
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    # - Indexes aggregate identity for tracing events belonging to one entity.
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    # - Indexes delivery status for fast pending-work scans.
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    # - Indexes due time so retry workers can find eligible messages efficiently.
    op.create_index("ix_outbox_events_available_at", "outbox_events", ["available_at"])

    # - Creates the inbound event receipt table used to deduplicate provider retries.
    op.create_table(
        # - Names the table that stores provider event receipts.
        "inbox_events",
        # - Assigns each receipt a local integer primary key.
        sa.Column("id", sa.Integer(), primary_key=True),
        # - Identifies the external system that sent the event.
        sa.Column("provider", sa.String(), nullable=False),
        # - Stores the stable provider event ID used for duplicate detection.
        sa.Column("provider_event_id", sa.String(), nullable=False),
        # - Retains the original event body for processing and audit.
        sa.Column("payload", sa.JSON(), nullable=False),
        # - Remains unset until event processing succeeds.
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        # - Captures receipt time from the database clock.
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        # - Prevents duplicate receipts for the same provider event.
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_inbox_provider_event"),
    )
    # - Indexes provider event identifiers for lookup and deduplication checks.
    op.create_index("ix_inbox_events_provider_event_id", "inbox_events", ["provider_event_id"])


# - Removes the tables and indexes created by the forward migration.
# - Architectural Purpose: Supports an explicit rollback to the prior schema version.
# - Plain-English: 'Remove durable messaging storage if this revision is undone.'
def downgrade() -> None:
    # - Drops the inbox lookup index before its table.
    op.drop_index("ix_inbox_events_provider_event_id", table_name="inbox_events")
    # - Removes inbox receipts and their uniqueness rule.
    op.drop_table("inbox_events")
    # - Removes retry scheduling lookup.
    op.drop_index("ix_outbox_events_available_at", table_name="outbox_events")
    # - Removes pending-state lookup.
    op.drop_index("ix_outbox_events_status", table_name="outbox_events")
    # - Removes aggregate tracing lookup.
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    # - Removes event-type lookup.
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    # - Removes all remaining outgoing event data.
    op.drop_table("outbox_events")
