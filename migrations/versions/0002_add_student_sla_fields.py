"""
Alembic migration to add SLA tracking, CSM attribution, and program-tier metadata
to the Student model.
"""
from sqlalchemy import Column, String, DateTime, Integer, Boolean
from sqlalchemy.sql import func
from alembic import op

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
offline = None

def upgrade():
    op.add_column('students', Column('program_type', String, nullable=False, server_default='Standard'))
    op.add_column('students', Column('assigned_csm_id', String, nullable=True))
    op.add_column('students', Column('last_interaction_at', DateTime, server_default=func.now(), nullable=True))
    op.add_column('students', Column('sla_status_start_at', DateTime, server_default=func.now(), nullable=True))
    op.add_column('students', Column('follow_up_count', Integer, nullable=False, server_default='0'))
    op.add_column('students', Column('is_paused', Boolean, nullable=False, server_default='false'))

def downgrade():
    op.drop_column('students', 'is_paused')
    op.drop_column('students', 'follow_up_count')
    op.drop_column('students', 'sla_status_start_at')
    op.drop_column('students', 'last_interaction_at')
    op.drop_column('students', 'assigned_csm_id')
    op.drop_column('students', 'program_type')
