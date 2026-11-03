"""
Alembic migration to add SLA tracking, CSM attribution, and program-tier metadata
to the Student model.
"""
# Runtime: Imports SQLAlchemy column and type constructors for schema changes.
# Architecture: Describes PostgreSQL columns through Alembic's SQLAlchemy bridge.
# Plain English: Provides building blocks for new table fields.
from sqlalchemy import Column, String, DateTime, Integer, Boolean
# Runtime: Imports SQL function expressions such as database-side now().
# Architecture: Keeps timestamp defaults evaluated by PostgreSQL.
# Plain English: Supplies the current-time SQL function.
from sqlalchemy.sql import func
# Runtime: Imports Alembic's migration operation facade.
# Architecture: Applies reversible schema changes to the configured PostgreSQL database.
# Plain English: Provides commands for adding and removing columns.
from alembic import op

# revision identifiers, used by Alembic.
# Runtime: Stores this migration's unique graph identifier.
# Architecture: Lets Alembic record that SLA fields have been applied.
# Plain English: Names this schema step.
revision = '0002'
# Runtime: Points Alembic to the migration that must run first.
# Architecture: Preserves the ordered migration chain.
# Plain English: Says this follows migration 0001.
down_revision = '0001'
# Runtime: Leaves branch grouping unset.
# Architecture: Keeps this migration on the default Alembic branch.
# Plain English: Declares no branch label.
branch_labels = None
# Runtime: Leaves optional external migration dependency unset.
# Architecture: Allows Alembic to schedule this step independently of other branches.
# Plain English: Declares no extra dependency.
offline = None

# Runtime: Defines the forward schema operation invoked by Alembic upgrade.
# Architecture: Adds SLA, CSM, and program metadata used by the FastAPI domain model.
# Plain English: Creates the new student-tracking fields.
def upgrade():
    # Runtime: Adds a required text column with a database default for existing rows.
    # Architecture: Gives SLA policy code a program tier for each student.
    # Plain English: Stores which program the student belongs to.
    op.add_column('students', Column('program_type', String, nullable=False, server_default='Standard'))
    # Runtime: Adds an optional text attribution column.
    # Architecture: Links a student record to the responsible customer success manager.
    # Plain English: Stores the assigned CSM identifier.
    op.add_column('students', Column('assigned_csm_id', String, nullable=True))
    # Runtime: Adds a nullable timestamp initialized by PostgreSQL's current time.
    # Architecture: Records the latest interaction for SLA evaluation.
    # Plain English: Stores when the student last interacted.
    op.add_column('students', Column('last_interaction_at', DateTime, server_default=func.now(), nullable=True))
    # Runtime: Adds a timestamp for the beginning of the current SLA status window.
    # Architecture: Gives the auditor an anchor for elapsed-time thresholds.
    # Plain English: Stores when the current SLA clock started.
    op.add_column('students', Column('sla_status_start_at', DateTime, server_default=func.now(), nullable=True))
    # Runtime: Adds a non-null integer counter with a zero database default.
    # Architecture: Supports follow-up volume and escalation decisions.
    # Plain English: Counts how many follow-ups have occurred.
    op.add_column('students', Column('follow_up_count', Integer, nullable=False, server_default='0'))
    # Runtime: Adds a non-null boolean with a false database default.
    # Architecture: Allows the SLA auditor to exclude intentionally paused students.
    # Plain English: Records whether auditing is paused.
    op.add_column('students', Column('is_paused', Boolean, nullable=False, server_default='false'))

# Runtime: Defines the reverse schema operation invoked by Alembic downgrade.
# Architecture: Restores the students table to its pre-SLA shape.
# Plain English: Removes all fields introduced above.
def downgrade():
    # Runtime: Removes the pause flag before other SLA fields.
    # Architecture: Reverses the forward migration cleanly.
    # Plain English: Deletes the audit pause column.
    op.drop_column('students', 'is_paused')
    # Runtime: Removes the follow-up counter.
    # Architecture: Reverts the escalation-tracking schema.
    # Plain English: Deletes the follow-up count.
    op.drop_column('students', 'follow_up_count')
    # Runtime: Removes the SLA start timestamp.
    # Architecture: Restores the prior student schema without SLA timing.
    # Plain English: Deletes the SLA clock field.
    op.drop_column('students', 'sla_status_start_at')
    # Runtime: Removes the interaction timestamp.
    # Architecture: Reverts the last-contact tracking field.
    # Plain English: Deletes last interaction time.
    op.drop_column('students', 'last_interaction_at')
    # Runtime: Removes CSM attribution.
    # Architecture: Restores the earlier integration-neutral student model.
    # Plain English: Deletes the assigned CSM field.
    op.drop_column('students', 'assigned_csm_id')
    # Runtime: Removes program metadata introduced by upgrade.
    # Architecture: Completes the reversible migration contract.
    # Plain English: Deletes the program type field.
    op.drop_column('students', 'program_type')
