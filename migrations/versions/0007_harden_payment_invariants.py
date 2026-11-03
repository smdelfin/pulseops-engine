# - Describes the database checks and index added by this revision.
# - Architectural Purpose: Names the financial integrity protections visible in migration history.
# - Plain-English: 'Make PostgreSQL reject invalid payment values.'
"""harden payment event invariants

Revision ID: 0007
Revises: 0006
"""

# - Imports Alembic DDL operations for applying and reversing schema constraints.
# - Architectural Purpose: Makes database integrity rules version-controlled and deployable.
# - Plain-English: 'Use Alembic to add payment safeguards.'
from alembic import op
# - Imports SQLAlchemy for migration-defined schema operations.
# - Architectural Purpose: Supplies the schema types used by Alembic's migration environment.
# - Plain-English: 'Load SQLAlchemy schema helpers for this migration.'
import sqlalchemy as sa


# - Identifies this revision in Alembic's version history.
# - Architectural Purpose: Tracks which database environments have these payment safeguards.
# - Plain-English: 'Name this database change.'
revision = "0007"
# - Requires payment/offboarding tables from revision 0006.
# - Architectural Purpose: Guarantees that the payment table exists before adding its checks.
# - Plain-English: 'Apply the payment table migration first.'
down_revision = "0006"
# - Declares no separate branch label.
# - Architectural Purpose: Keeps the migration chain linear.
# - Plain-English: 'This change stays on the main migration path.'
branch_labels = None
# - Declares no additional revision prerequisites.
# - Architectural Purpose: Makes ordering requirements explicit.
# - Plain-English: 'No extra migration dependency is needed.'
depends_on = None


# - Adds database-level payment validation and a status/time lookup index.
# - Architectural Purpose: Protects data written by scripts or integrations that bypass Pydantic validation.
# - Plain-English: 'Make the database itself enforce valid payment records and support operations queries.'
def upgrade() -> None:
    # - Restricts payment statuses to the same allowlist accepted by the webhook.
    op.create_check_constraint(
        # - Assigns a stable constraint name for inspection and rollback.
        "ck_payment_events_status",
        # - Applies the rule to the payment event table.
        "payment_events",
        # - Allows only the supported normalized payment lifecycle values.
        "status IN ('pending', 'processing', 'succeeded', 'paid', 'failed', "
        "'past_due', 'declined', 'refunded', 'cancelled')",
    )
    # - Blocks negative amounts while continuing to allow unspecified amounts.
    op.create_check_constraint(
        "ck_payment_events_amount",
        "payment_events",
        "amount IS NULL OR amount >= 0",
    )
    # - Ensures persisted currency codes are canonical uppercase values when supplied.
    op.create_check_constraint(
        "ck_payment_events_currency_upper",
        "payment_events",
        "currency IS NULL OR currency = upper(currency)",
    )
    # - Adds a composite index for status-filtered occurrence-time queries.
    op.create_index(
        "ix_payment_events_status_occurred_at",
        "payment_events",
        ["status", "occurred_at"],
    )


# - Removes the index and constraints introduced by the upgrade.
# - Architectural Purpose: Restores the prior schema contract during an explicit downgrade.
# - Plain-English: 'Undo the payment checks and index from revision 0007.'
def downgrade() -> None:
    # - Removes the query index before changing table constraints.
    op.drop_index("ix_payment_events_status_occurred_at", table_name="payment_events")
    # - Removes uppercase currency enforcement.
    op.drop_constraint("ck_payment_events_currency_upper", "payment_events", type_="check")
    # - Removes non-negative amount enforcement.
    op.drop_constraint("ck_payment_events_amount", "payment_events", type_="check")
    # - Removes the supported-status allowlist.
    op.drop_constraint("ck_payment_events_status", "payment_events", type_="check")
