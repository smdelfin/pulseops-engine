# - Imports datetime for ORM fields that record event timing.
# - Architectural Purpose: Database timestamps let workers schedule retries and audit delivery history.
# - Plain-English: 'Use dates to track when messages were created and handled.'
from datetime import datetime

# - Imports SQLAlchemy column types used by the durable message tables.
# - Architectural Purpose: Explicit column types make queue-related state queryable and constraint-friendly.
# - Plain-English: 'Choose database types for each kind of message data.'
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
# - Imports PostgreSQL's native JSONB type for structured event payload storage.
# - Architectural Purpose: JSONB preserves provider payload shape while supporting efficient JSON operations.
# - Plain-English: 'Store flexible message details as searchable JSON.'
from sqlalchemy.dialects.postgresql import JSONB
# - Imports the database clock function for server-generated timestamps.
# - Architectural Purpose: The database supplies a consistent timestamp even when producers run on different hosts.
# - Plain-English: 'Let PostgreSQL record the time by default.'
from sqlalchemy.sql import func

# - Imports the shared declarative base used to register ORM tables.
# - Architectural Purpose: Keeps all models in the metadata Alembic and SQLAlchemy use.
# - Plain-English: 'Connect these table definitions to the application's database model.'
from src.core.db import Base


# - Maps messages awaiting publication or delivery to a durable PostgreSQL outbox table.
# - Architectural Purpose: Commits business changes and their outgoing work in one database transaction.
# - Plain-English: 'Keep a reliable record of messages the system still needs to send.'
class OutboxEvent(Base):
    # - Sets the physical table name used by SQLAlchemy and Alembic.
    __tablename__ = "outbox_events"

    # - Uses the event's globally unique string ID as the primary key.
    id = Column(String, primary_key=True)
    # - Stores the event category and indexes it for type-based operations.
    event_type = Column(String, nullable=False, index=True)
    # - Identifies the affected aggregate and indexes it for entity-level tracing.
    aggregate_id = Column(Integer, nullable=False, index=True)
    # - Persists the event body as PostgreSQL JSONB for queue serialization.
    payload = Column(JSONB, nullable=False)
    # - Tracks delivery state and makes pending-event scans efficient.
    status = Column(String, nullable=False, default="pending", index=True)
    # - Counts publication attempts to drive bounded exponential retry delays.
    attempts = Column(Integer, nullable=False, default=0)
    # - Sets the next eligible publication time and indexes due-event queries.
    available_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    # - Records successful queue publication time for auditing.
    published_at = Column(DateTime, nullable=True)
    # - Retains the latest delivery error for investigation and retry diagnostics.
    last_error = Column(Text, nullable=True)
    # - Uses the database clock to record when the outbox row was created.
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# - Maps inbound provider events to a durable inbox used for duplicate detection.
# - Architectural Purpose: Persisted provider IDs make webhook handling idempotent across retries and restarts.
# - Plain-English: 'Remember which external events have already arrived.'
class InboxEvent(Base):
    # - Sets the physical table name used for inbound event receipts.
    __tablename__ = "inbox_events"

    # - Adds a database-generated integer identity for the local inbox record.
    id = Column(Integer, primary_key=True)
    # - Identifies the external integration that supplied the event.
    provider = Column(String, nullable=False)
    # - Stores the provider's stable event identifier for duplicate checks.
    provider_event_id = Column(String, nullable=False)
    # - Retains the inbound event body to support processing and audit.
    payload = Column(JSONB, nullable=False)
    # - Remains null until application processing marks the event complete.
    processed_at = Column(DateTime, nullable=True)
    # - Captures receipt time using PostgreSQL's clock.
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
