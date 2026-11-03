# - Describes the schema changes shown in the migration history.
# - Architectural Purpose: Gives reviewers and operators the intent before inspecting DDL details.
# - Plain-English: 'Add cohort reporting fields and protections to student records.'
"""harden student dimensions with cohort, indexes, and invariants

Revision ID: 0004
Revises: 0003
"""

# - Imports Alembic's operations for applying versioned schema changes.
# - Architectural Purpose: Ensures schema updates are repeatable in development and production.
# - Plain-English: 'Use Alembic to update the database.'
from alembic import op
# - Imports SQLAlchemy column types used by the migration.
# - Architectural Purpose: Keeps migration DDL explicit and stable.
# - Plain-English: 'Describe the types and constraints the database will create.'
import sqlalchemy as sa


# - Identifies this migration in Alembic's revision graph.
# - Architectural Purpose: Lets deployments record their current database version.
# - Plain-English: 'Give this schema update its version ID.'
revision = "0004"
# - Requires lifecycle-history migration 0003 to be applied first.
# - Architectural Purpose: Maintains a deterministic sequence of schema changes.
# - Plain-English: 'This update follows revision 0003.'
down_revision = "0003"
# - Declares no named migration branch.
# - Architectural Purpose: Keeps this project's migration graph linear.
# - Plain-English: 'This migration belongs to the main migration path.'
branch_labels = None
# - Declares no additional revision dependency.
# - Architectural Purpose: Makes the absence of cross-branch ordering explicit.
# - Plain-English: 'No other migration must be applied separately.'
depends_on = None


# - Applies cohort, integrity, and query-performance schema changes.
# - Architectural Purpose: Adds dimensions and guardrails required by operational dashboards.
# - Plain-English: 'Upgrade student storage to support safer reporting and operations.'
def upgrade() -> None:
    # - Adds a non-null cohort with a temporary/default value for existing rows.
    op.add_column(
        "students",
        sa.Column("cohort", sa.String(), nullable=False, server_default="Default"),
    )
    # - Rejects health scores outside the supported 0-100 range while allowing unknown values.
    op.create_check_constraint(
        "ck_students_health_score",
        "students",
        "health_score IS NULL OR health_score BETWEEN 0 AND 100",
    )
    # - Prevents negative follow-up counts from entering the student table.
    op.create_check_constraint(
        "ck_students_follow_up_count",
        "students",
        "follow_up_count >= 0",
    )
    # - Limits persisted statuses to the lifecycle and compatibility values supported by the application.
    op.create_check_constraint(
        "ck_students_status",
        "students",
        "status IN ('pending', 'queued', 'processing', 'onboarding_started', "
        "'completed', 'at_risk', 'offboarding', 'refunded', 'cancelled', "
        "'failed', 'manual_hold', 'scheduled')",
    )
    # - Speeds dashboards and auditors that filter by status and inspect update recency.
    op.create_index(
        "ix_students_status_updated_at",
        "students",
        ["status", "updated_at"],
    )
    # - Speeds workload lookups grouped by assigned CSM and student status.
    op.create_index(
        "ix_students_csm_status",
        "students",
        ["assigned_csm_id", "status"],
    )
    # - Supports program/cohort/status segmentation without repeated table scans.
    op.create_index(
        "ix_students_program_cohort_status",
        "students",
        ["program_type", "cohort", "status"],
    )
    # - Prevents assigning one external ClickUp task to multiple students while enabling lookup.
    op.create_index(
        "ux_students_clickup_task_id",
        "students",
        ["clickup_task_id"],
        unique=True,
    )


# - Reverses this revision in dependency-safe order.
# - Architectural Purpose: Allows a controlled downgrade without leaving orphaned indexes or constraints.
# - Plain-English: 'Remove the protections and cohort field added by this upgrade.'
def downgrade() -> None:
    # - Removes the ClickUp uniqueness index before removing related schema dependencies.
    op.drop_index("ux_students_clickup_task_id", table_name="students")
    # - Removes the program/cohort/status query index.
    op.drop_index("ix_students_program_cohort_status", table_name="students")
    # - Removes the CSM/status workload index.
    op.drop_index("ix_students_csm_status", table_name="students")
    # - Removes the status/update-time operational index.
    op.drop_index("ix_students_status_updated_at", table_name="students")
    # - Removes lifecycle-status validation.
    op.drop_constraint("ck_students_status", "students", type_="check")
    # - Removes the non-negative follow-up-count rule.
    op.drop_constraint("ck_students_follow_up_count", "students", type_="check")
    # - Removes the bounded health-score rule.
    op.drop_constraint("ck_students_health_score", "students", type_="check")
    # - Removes the cohort column introduced by this migration.
    op.drop_column("students", "cohort")
