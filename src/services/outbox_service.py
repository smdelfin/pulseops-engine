# - Imports JSON serialization for sending persisted event payloads to Azure Queue.
# - Architectural Purpose: The outbox stores structured JSON while the queue transports message text.
# - Plain-English: 'Convert event data into the text format the queue accepts.'
import json
# - Imports logging for explicit publication-failure diagnostics.
# - Architectural Purpose: Failed deliveries must be observable while remaining retryable.
# - Plain-English: 'Record a useful error when sending a message fails.'
import logging
# - Imports UTC datetime and delay arithmetic for due-event selection and retry scheduling.
# - Architectural Purpose: Shared UTC scheduling prevents ambiguity across distributed workers.
# - Plain-English: 'Work with consistent times and calculate retry delays.'
from datetime import datetime, timedelta, timezone

# - Imports SQLAlchemy's select constructor for ORM queries.
# - Architectural Purpose: Uses a composable query API for finding durable pending work.
# - Plain-English: 'Build a database query for events ready to send.'
from sqlalchemy import select
# - Imports the async ORM session type expected from request or worker lifecycle management.
# - Architectural Purpose: Reuses the application's asynchronous connection pool rather than opening ad hoc connections.
# - Plain-English: 'Use the current async database session.'
from sqlalchemy.ext.asyncio import AsyncSession

# - Imports the row model that holds messages until publication succeeds.
# - Architectural Purpose: The service claims transactional outbox records rather than losing work on process crashes.
# - Plain-English: 'Read the database records that still need to go onto the queue.'
from src.models.messaging import OutboxEvent
# - Imports the Azure Queue adapter responsible for external message delivery.
# - Architectural Purpose: Keeps queue SDK details behind the service boundary.
# - Plain-English: 'Use the existing component that talks to Azure Queue.'
from src.services.queue_service import QueueService

# - Creates a module-level logger named for this service.
# - Architectural Purpose: Log aggregation can identify publication failures by subsystem.
# - Plain-English: 'Give this component a recognizable name in logs.'
logger = logging.getLogger(__name__)


# - Coordinates retryable publication of PostgreSQL outbox events to Azure Queue.
# - Architectural Purpose: Separates durable transaction commit from transient external delivery.
# - Plain-English: 'Take messages saved in the database and send them when the queue is available.'
class OutboxService:
    # - Allows injection of a queue adapter while providing a production default.
    # - Architectural Purpose: Dependency injection makes testing deterministic and avoids hard-coding transport setup.
    # - Plain-English: 'Use a supplied queue connection or create the normal one.'
    def __init__(self, queue_service: QueueService | None = None) -> None:
        # - Reuses the injected adapter or constructs the standard Azure Queue service.
        self.queue_service = queue_service or QueueService()

    # - Publishes a bounded batch of due outbox messages and returns the successful count.
    # - Architectural Purpose: Limits database locks and queue work per invocation in worker/scheduler loops.
    # - Plain-English: 'Send up to a set number of ready messages and report how many worked.'
    async def publish_pending(self, session: AsyncSession, limit: int = 50) -> int:
        # - Captures one timezone-aware timestamp for this batch's comparisons and updates.
        now = datetime.now(timezone.utc)
        # - Loads only pending, due rows, oldest first, while safely skipping rows locked by other publishers.
        result = await session.execute(
            # - Builds a typed SQLAlchemy query for outbox entities.
            select(OutboxEvent)
            # - Excludes already-published and not-yet-due messages.
            .where(
                OutboxEvent.status == "pending",
                OutboxEvent.available_at <= now,
            )
            # - Favors older events so persistent work is not starved by newer inserts.
            .order_by(OutboxEvent.created_at)
            # - Bounds this invocation's work to the configured batch size.
            .limit(limit)
            # - Claims rows without waiting on rows already being processed elsewhere.
            .with_for_update(skip_locked=True)
        )
        # - Materializes ORM records from the query result for processing.
        events = result.scalars().all()
        # - Initializes the count of messages successfully handed off to the queue.
        published = 0

        # - Processes each locked event independently so one failure does not block later messages.
        for event in events:
            # - Records the attempt before making the external request.
            event.attempts += 1
            # - Separates transport failures from successful state transitions.
            try:
                # - Serializes the durable payload and asks the Azure Queue adapter to publish it.
                await self.queue_service.push_message(json.dumps(event.payload))
            # - Captures delivery errors so the event can remain pending and be retried.
            except Exception as exc:
                # - Persists the latest error message for support visibility.
                event.last_error = str(exc)
                # - Schedules a capped exponential delay to avoid hammering an unavailable dependency.
                event.available_at = now + timedelta(seconds=min(300, 2 ** event.attempts))
                # - Emits a traceback with the event ID to support diagnosis without discarding the record.
                logger.exception("Failed to publish outbox event %s", event.id)
            # - Marks the event delivered only after the external queue call succeeds.
            else:
                # - Removes the event from future pending scans.
                event.status = "published"
                # - Records the time the queue accepted the message.
                event.published_at = now
                # - Clears stale failure detail from any earlier retry.
                event.last_error = None
                # - Increments the returned successful-delivery count.
                published += 1

        # - Atomically stores all attempt counts, retry schedules, and successful publication states.
        await session.commit()
        # - Returns a simple metric for worker logging and scheduler monitoring.
        return published
