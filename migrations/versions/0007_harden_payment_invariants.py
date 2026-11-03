"""harden payment event invariants

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_payment_events_status",
        "payment_events",
        "status IN ('pending', 'processing', 'succeeded', 'paid', 'failed', "
        "'past_due', 'declined', 'refunded', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_payment_events_amount",
        "payment_events",
        "amount IS NULL OR amount >= 0",
    )
    op.create_check_constraint(
        "ck_payment_events_currency_upper",
        "payment_events",
        "currency IS NULL OR currency = upper(currency)",
    )
    op.create_index(
        "ix_payment_events_status_occurred_at",
        "payment_events",
        ["status", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_events_status_occurred_at", table_name="payment_events")
    op.drop_constraint("ck_payment_events_currency_upper", "payment_events", type_="check")
    op.drop_constraint("ck_payment_events_amount", "payment_events", type_="check")
    op.drop_constraint("ck_payment_events_status", "payment_events", type_="check")
