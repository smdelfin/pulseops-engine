"""harden student dimensions with cohort, indexes, and invariants

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("cohort", sa.String(), nullable=False, server_default="Default"),
    )
    op.create_check_constraint(
        "ck_students_health_score",
        "students",
        "health_score IS NULL OR health_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_students_follow_up_count",
        "students",
        "follow_up_count >= 0",
    )
    op.create_check_constraint(
        "ck_students_status",
        "students",
        "status IN ('pending', 'queued', 'processing', 'onboarding_started', "
        "'completed', 'at_risk', 'offboarding', 'refunded', 'cancelled', "
        "'failed', 'manual_hold', 'scheduled')",
    )
    op.create_index(
        "ix_students_status_updated_at",
        "students",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_students_csm_status",
        "students",
        ["assigned_csm_id", "status"],
    )
    op.create_index(
        "ix_students_program_cohort_status",
        "students",
        ["program_type", "cohort", "status"],
    )
    op.create_index(
        "ux_students_clickup_task_id",
        "students",
        ["clickup_task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_students_clickup_task_id", table_name="students")
    op.drop_index("ix_students_program_cohort_status", table_name="students")
    op.drop_index("ix_students_csm_status", table_name="students")
    op.drop_index("ix_students_status_updated_at", table_name="students")
    op.drop_constraint("ck_students_status", "students", type_="check")
    op.drop_constraint("ck_students_follow_up_count", "students", type_="check")
    op.drop_constraint("ck_students_health_score", "students", type_="check")
    op.drop_column("students", "cohort")
