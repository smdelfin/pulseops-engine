# - Imports SQLAlchemy column types used to define lifecycle audit fields.
# - Architectural Purpose: A relational audit model supports indexed history queries and referential integrity.
# - Plain-English: 'Choose database columns for each recorded status change.'
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
# - Imports the database clock function for default transition timestamps.
# - Architectural Purpose: Server-side time avoids dependence on application host clocks.
# - Plain-English: 'Let the database timestamp each transition.'
from sqlalchemy.sql import func

# - Imports the shared ORM base so SQLAlchemy and Alembic discover this table.
# - Architectural Purpose: Keeps runtime mappings aligned with migration metadata.
# - Plain-English: 'Register this model with the application database.'
from src.core.db import Base


# - Maps each student lifecycle change to an append-only audit row.
# - Architectural Purpose: Separates historical state changes from the current-state student record.
# - Plain-English: 'Keep a timeline of how each student's status changed.'
class StudentTransition(Base):
    # - Sets the database table name.
    __tablename__ = "student_transitions"

    # - Creates the local primary key for one transition entry.
    id = Column(Integer, primary_key=True)
    # - Links the history entry to a student and indexes history retrieval by student.
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    # - Records the previous status; null represents initial creation without a prior state.
    from_status = Column(String, nullable=True)
    # - Records the new status after the transition.
    to_status = Column(String, nullable=False)
    # - Identifies the kind of operation that caused the change.
    event_type = Column(String, nullable=False)
    # - Stores optional operator or provider context explaining the transition.
    reason = Column(Text, nullable=True)
    # - Associates related history rows with the same webhook or workflow request.
    correlation_id = Column(String, nullable=True, index=True)
    # - Assigns the transition time from the database clock.
    occurred_at = Column(DateTime, server_default=func.now(), nullable=False)
