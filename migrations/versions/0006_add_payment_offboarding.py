# - Describes the operational database structures introduced by this revision.
# - Architectural Purpose: Makes migration intent visible in Alembic history and deployment logs.
# - Plain-English: 'Create durable records for payment updates and offboarding work.'
"""add payment and offboarding workflow records

Revision ID: 0006
Revises: 0005
"""

# - Imports Alembic operations for applying versioned schema changes.
# - Architectural Purpose: Keeps production and local database upgrades repeatable.
# - Plain-English: 'Use Alembic to create the workflow tables.'
from alembic import op
# - Imports SQLAlchemy schema types for table and constraint definitions.
# - Architectural Purpose: Defines stable DDL without relying on mutable application models.
# - Plain-English: 'Describe the columns and relationships the database needs.'
import sqlalchemy as sa


# - Identifies this node in the Alembic revision graph.
# - Architectural Purpose: Records the schema version applied to each environment.
# - Plain-English: 'Give this database update its revision ID.'
revision = "0006"
# - Requires durable messaging revision 0005 to be installed first.
# - Architectural Purpose: Maintains the ordered migration chain.
# - Plain-English: 'Apply the inbox/outbox schema before these operations tables.'
down_revision = "0005"
# - Declares no separate branch label.
# - Architectural Purpose: Keeps the migration history linear.
# - Plain-English: 'This change belongs to the main database upgrade path.'
branch_labels = None
# - Declares no additional revision prerequisites.
# - Architectural Purpose: Makes migration dependencies explicit.
# - Plain-English: 'No other migration is needed beyond revision 0005.'
depends_on = None


# - Creates durable payment-event and offboarding-case storage.
# - Architectural Purpose: Separates financial facts and follow-up tasks from the student aggregate.
# - Plain-English: 'Add tables to track payment provider events and departure checklists.'
def upgrade() -> None:
    # - Creates the independent payment-event history table.
    op.create_table(
        # - Names the payment persistence table.
        "payment_events",
        # - Assigns each payment row a database-generated primary key.
        sa.Column("id", sa.Integer(), primary_key=True),
        # - Links payment activity to a student and cascades dependent rows on student removal.
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        # - Identifies the provider that originated the payment.
        sa.Column("provider", sa.String(), nullable=False),
        # - Stores the provider's stable payment key for idempotent storage.
        sa.Column("provider_payment_id", sa.String(), nullable=False),
        # - Stores the payment status supplied and normalized by the API.
        sa.Column("status", sa.String(), nullable=False),
        # - Stores optional decimal monetary value without floating-point rounding.
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        # - Stores an optional three-character currency code.
        sa.Column("currency", sa.String(3), nullable=True),
        # - Retains provider failure details for operational follow-up.
        sa.Column("failure_reason", sa.Text(), nullable=True),
        # - Stores the event timestamp reported by the provider.
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        # - Stores database insertion time independently from provider event time.
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        # - Prevents duplicate rows for the same provider/payment identifier pair.
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"),
    )
    # - Speeds queries that load payment records for a student.
    op.create_index("ix_payment_events_student_id", "payment_events", ["student_id"])

    # - Creates a checklist record for each refund or cancellation workflow.
    op.create_table(
        # - Names the offboarding workflow table.
        "offboarding_cases",
        # - Assigns each workflow case a database-generated primary key.
        sa.Column("id", sa.Integer(), primary_key=True),
        # - Links the case to its student for ownership and cleanup.
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        # - Requires the business reason that initiated departure.
        sa.Column("reason", sa.String(), nullable=False),
        # - Starts new cases in the open state.
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        # - Starts the access-revocation task as incomplete.
        sa.Column("access_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        # - Starts the final-communication task as incomplete.
        sa.Column("final_communication_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        # - Remains null until all case tasks are complete.
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        # - Uses the database clock to record case creation.
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    # - Supports lookup of a student's offboarding cases.
    op.create_index("ix_offboarding_cases_student_id", "offboarding_cases", ["student_id"])
    # - Supports operational queues filtered by case status.
    op.create_index("ix_offboarding_cases_status", "offboarding_cases", ["status"])


# - Removes the offboarding and payment structures in dependency-safe order.
# - Architectural Purpose: Provides an explicit rollback path for this schema revision.
# - Plain-English: 'Undo the workflow tables if the migration is rolled back.'
def downgrade() -> None:
    # - Removes status lookup before dropping its table.
    op.drop_index("ix_offboarding_cases_status", table_name="offboarding_cases")
    # - Removes student lookup before dropping its table.
    op.drop_index("ix_offboarding_cases_student_id", table_name="offboarding_cases")
    # - Removes offboarding cases and their checklist data.
    op.drop_table("offboarding_cases")
    # - Removes the student lookup before dropping payment events.
    op.drop_index("ix_payment_events_student_id", table_name="payment_events")
    # - Removes payment-event rows and their unique provider/payment rule.
    op.drop_table("payment_events")
