"""add payment and offboarding workflow records

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_payment_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"),
    )
    op.create_index("ix_payment_events_student_id", "payment_events", ["student_id"])

    op.create_table(
        "offboarding_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("access_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("final_communication_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_offboarding_cases_student_id", "offboarding_cases", ["student_id"])
    op.create_index("ix_offboarding_cases_status", "offboarding_cases", ["status"])


def downgrade() -> None:
    op.drop_index("ix_offboarding_cases_status", table_name="offboarding_cases")
    op.drop_index("ix_offboarding_cases_student_id", table_name="offboarding_cases")
    op.drop_table("offboarding_cases")
    op.drop_index("ix_payment_events_student_id", table_name="payment_events")
    op.drop_table("payment_events")
