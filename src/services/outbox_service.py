import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.messaging import OutboxEvent
from src.services.queue_service import QueueService

logger = logging.getLogger(__name__)


class OutboxService:
    def __init__(self, queue_service: QueueService | None = None) -> None:
        self.queue_service = queue_service or QueueService()

    async def publish_pending(self, session: AsyncSession, limit: int = 50) -> int:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()
        published = 0

        for event in events:
            event.attempts += 1
            try:
                await self.queue_service.push_message(json.dumps(event.payload))
            except Exception as exc:
                event.last_error = str(exc)
                event.available_at = now + timedelta(seconds=min(300, 2 ** event.attempts))
                logger.exception("Failed to publish outbox event %s", event.id)
            else:
                event.status = "published"
                event.published_at = now
                event.last_error = None
                published += 1

        await session.commit()
        return published

