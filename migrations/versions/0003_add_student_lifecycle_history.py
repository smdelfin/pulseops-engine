"""add explicit student lifecycle transition history

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_transitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_student_transitions_student_id", "student_transitions", ["student_id"])
    op.create_index("ix_student_transitions_correlation_id", "student_transitions", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_student_transitions_correlation_id", table_name="student_transitions")
    op.drop_index("ix_student_transitions_student_id", table_name="student_transitions")
    op.drop_table("student_transitions")
