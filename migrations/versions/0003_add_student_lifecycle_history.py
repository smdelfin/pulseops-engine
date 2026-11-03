# - Describes the schema change shown by Alembic history.
# - Architectural Purpose: Human-readable migration metadata helps operators understand deployment order.
# - Plain-English: 'This change creates the student status-change history.'
"""add explicit student lifecycle transition history

Revision ID: 0003
Revises: 0002
"""

# - Imports Alembic's migration operations for transactional schema changes.
# - Architectural Purpose: Keeps schema evolution versioned and repeatable across environments.
# - Plain-English: 'Use Alembic commands to change the database structure.'
from alembic import op
# - Imports SQLAlchemy schema types used to define new database columns.
# - Architectural Purpose: Migration types describe the database independently from application ORM imports.
# - Plain-English: 'Choose the exact data types for the new table.'
import sqlalchemy as sa


# - Identifies this migration node in Alembic's revision graph.
# - Architectural Purpose: Stable IDs let deployments track exactly which schema version is installed.
# - Plain-English: 'Name this database change.'
revision = "0003"
# - Connects this change to its required predecessor.
# - Architectural Purpose: Enforces migration ordering and a single upgrade path.
# - Plain-English: 'Run revision 0002 before this one.'
down_revision = "0002"
# - Declares that this revision is not part of a named branch.
# - Architectural Purpose: Keeps the migration graph linear for this project.
# - Plain-English: 'This change does not start a parallel migration branch.'
branch_labels = None
# - Declares that this revision has no additional migration dependencies.
# - Architectural Purpose: Makes dependency ordering explicit to Alembic.
# - Plain-English: 'There are no extra revisions this change depends on.'
depends_on = None


# - Applies the forward schema change that creates lifecycle history.
# - Architectural Purpose: Preserves auditable transitions separately from the mutable student row.
# - Plain-English: 'Create a table for recording every student status change.'
def upgrade() -> None:
    # - Creates the transition table and defines its columns and referential relationship.
    op.create_table(
        # - Names the durable audit-history table.
        "student_transitions",
        # - Assigns each transition row a database-generated integer identity.
        sa.Column("id", sa.Integer(), primary_key=True),
        # - Links each record to its student and removes dependent history with a deleted student.
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        # - Allows the initial transition to have no prior status.
        sa.Column("from_status", sa.String(), nullable=True),
        # - Requires the destination status for every recorded transition.
        sa.Column("to_status", sa.String(), nullable=False),
        # - Stores the business event category that caused the transition.
        sa.Column("event_type", sa.String(), nullable=False),
        # - Allows optional operator or provider explanation text.
        sa.Column("reason", sa.Text(), nullable=True),
        # - Stores an optional external request identifier for transition correlation.
        sa.Column("correlation_id", sa.String(), nullable=True),
        # - Uses the database clock to record when the transition was written.
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    # - Indexes the student foreign key for fast retrieval of one student's history.
    op.create_index("ix_student_transitions_student_id", "student_transitions", ["student_id"])
    # - Indexes correlation IDs so related rows from one webhook or workflow can be located quickly.
    op.create_index("ix_student_transitions_correlation_id", "student_transitions", ["correlation_id"])


# - Reverses the forward schema change for an explicit downgrade.
# - Architectural Purpose: Supports controlled rollback to the prior migration revision.
# - Plain-English: 'Remove the audit table if the database is downgraded.'
def downgrade() -> None:
    # - Drops the correlation lookup index before dropping its table.
    op.drop_index("ix_student_transitions_correlation_id", table_name="student_transitions")
    # - Drops the student-history index before dropping its table.
    op.drop_index("ix_student_transitions_student_id", table_name="student_transitions")
    # - Removes the table and all history rows created by this revision.
    op.drop_table("student_transitions")
