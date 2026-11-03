from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from src.core.db import Base


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"),
    )

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    provider_payment_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    failure_reason = Column(Text, nullable=True)
    occurred_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class OffboardingCase(Base):
    __tablename__ = "offboarding_cases"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = Column(String, nullable=False)
    status = Column(String, nullable=False, default="open", index=True)
    access_revoked = Column(Boolean, nullable=False, default=False)
    final_communication_sent = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
