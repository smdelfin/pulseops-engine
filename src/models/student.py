# Import SQLAlchemy column types and primary key/index support for model definition.
from sqlalchemy import Column, Integer, String, Float, DateTime
# Import func to leverage database-native functions like current timestamps.
from sqlalchemy.sql import func
# Import the declarative base from our db configuration to link this model to the DB.
from src.core.db import Base

# Define the Student entity which represents a prospect in the pipeline.
class Student(Base):
    # Define the table name in the PostgreSQL schema.
    __tablename__ = "students"

    # Primary key 'id' for internal record management.
    id = Column(Integer, primary_key=True, index=True)
    # Full name of the lead/student.
    name = Column(String, nullable=False)
    # Unique identifier from GoHighLevel to prevent duplicate lead creation.
    ghl_contact_id = Column(String, unique=True, nullable=False)
    # Numerical score evaluating the lead's readiness for onboarding.
    health_score = Column(Integer, default=100)
    # Tracking status: 'pending', 'completed', 'failed', 'scheduled'.
    status = Column(String, default="pending", nullable=False)
    # Reference to the ClickUp list where provisioning is recorded.
    clickup_list_id = Column(String, nullable=True)
    # Reference to the specific ClickUp task created for this student.
    clickup_task_id = Column(String, nullable=True)
    # Program tier for SLA and behavior targeting (e.g., 'Enterprise', 'Standard', 'FastTrack').
    program_type = Column(String, default="Standard", nullable=False)
    # ID of the assigned Customer Success Manager (CSM).
    assigned_csm_id = Column(String, nullable=True)
    # Timestamp of the last meaningful touchpoint (DB update or API activity).
    last_interaction_at = Column(DateTime, server_default=func.now(), nullable=True)
    # Timestamp when the student entered their current status (used for SLA tracking).
    sla_status_start_at = Column(DateTime, server_default=func.now(), nullable=True)
    # Counter for manual follow-ups performed by staff.
    follow_up_count = Column(Integer, default=0, nullable=False)
    # Flag to pause automated worker processing for this record.
    is_paused = Column(Boolean, default=False, nullable=False)
    # Automatically set on row creation using the database server-side clock.
    created_at = Column(DateTime, server_default=func.now())
    # Automatically updated on every row change to provide a last-modified signal.
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now())
