from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from src.core.db import Base


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False, index=True)
    aggregate_id = Column(Integer, nullable=False, index=True)
    payload = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    published_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class InboxEvent(Base):
    __tablename__ = "inbox_events"

    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)
    provider_event_id = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

