"""create students table
# Runtime: Docstring used by Alembic to identify migration description.
# Architecture: Provides migration metadata for SQLAlchemy.
# Summary: Declares this migration will create the students table.
Revision ID: 0001
# Runtime: Unique ID for this migration applied sequentially.
# Architecture: Ensures migration order.
# Summary: Migration identifier.
Revises:
# Runtime: Indicates dependencies on previous migrations; None means first migration.
# Architecture: Allows Alembic to build dependency graph.
# Summary: No parent migration.
"""

from alembic import op
# Runtime: Alembic operation object used to generate/execute SQL.
# Architecture: Provides the migration engine with DB abstraction.
# Summary: Imports Alembic ops for defining migration steps.
import sqlalchemy as sa
# Runtime: SQLAlchemy library for column definitions, types.
# Architecture: Supplies column type constructors.
# Summary: Imports SQLAlchemy to describe table schema.

revision = "0001"
# Runtime: Identifier used by Alembic to track migrations.
# Architecture: Marks this migration's unique ID.
# Summary: Sets the current migration ID.

down_revision = None
# Runtime: Indicates this migration has no predecessor.
# Architecture: Signals first migration in the chain.
# Summary: No parent migration.

branch_labels = None
# Runtime / Architecture: Placeholder for branching migration groups.
# Summary: None; not used.

depends_on = None
# Runtime / Architecture: Dependencies on other migration scripts.
# Summary: None; this migration stands alone.


def upgrade() -> None:
    # Runtime: Called by Alembic to apply the migration.
    # Architecture: Encapsulates all table creation logic.
    # Summary: Sets up the students table.
    op.create_table(
        "students",
        # Primary key column: auto‑increment integer
        sa.Column("id", sa.Integer(), primary_key=True),
        # Student's full name; required
        sa.Column("name", sa.String(), nullable=False),
        # External contact ID; unique constraint below
        sa.Column("ghl_contact_id", sa.String(), nullable=False),
        # Optional health score field
        sa.Column("health_score", sa.Integer(), nullable=True),
        # Status flag with default 'pending'
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        # Integrations to ClickUp IDs
        sa.Column("clickup_list_id", sa.String(), nullable=True),
        sa.Column("clickup_task_id", sa.String(), nullable=True),
        # Timestamps auto‑filled by DB
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        # Ensure external ID uniqueness across rows
        sa.UniqueConstraint("ghl_contact_id"),
    )
    # Index on the primary key for fast lookups – not strictly necessary
    # but mirrors common patterns.
    op.create_index("ix_students_id", "students", ["id"], unique=False)



def downgrade() -> None:
    # Runtime: Called by Alembic to reverse the migration.
    # Architecture: Drops indexes and the table, restoring pre‑migration state.
    # Summary: Cleans up the students table.
    op.drop_index("ix_students_id", table_name="students")
    op.drop_table("students")
