from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from src.core.db import Base


class StudentTransition(Base):
    __tablename__ = "student_transitions"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    correlation_id = Column(String, nullable=True, index=True)
    occurred_at = Column(DateTime, server_default=func.now(), nullable=False)
