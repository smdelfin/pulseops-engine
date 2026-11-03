# Runtime: Provides async scheduling, process signals, and timed polling.
# Architecture: Lets the publisher run continuously without blocking the event loop.
# Plain English: Runs the background outbox delivery loop.
import asyncio
# Runtime: Emits batch outcomes and unexpected database failures.
# Architecture: Makes the independent dispatcher observable in container logs.
# Plain English: Records whether pending messages were delivered.
import logging
# Runtime: Provides operating-system signal constants for graceful container shutdown.
# Architecture: Lets Docker stop the loop without interrupting an active publication batch.
# Plain English: Handles normal stop requests.
import signal

# Runtime: Provides the application's async database session factory.
# Architecture: Reuses the shared PostgreSQL pool and persistence models.
# Plain English: Opens database sessions for fetching queued events.
from src.core.db import SessionLocal
# Runtime: Provides the retryable outbox-to-Azure publication workflow.
# Architecture: Keeps event delivery policy outside the long-running worker loop.
# Plain English: Sends saved events to the configured queue.
from src.services.outbox_service import OutboxService

# Runtime: Creates a named publisher logger.
# Architecture: Lets operators distinguish dispatch logs from API and provisioning logs.
# Plain English: Labels messages from this process.
logger = logging.getLogger("worker.outbox_publisher")

# Runtime: Bounds how long an idle dispatcher waits before checking for new work.
# Architecture: Balances low event-delivery latency against unnecessary database polling.
# Plain English: Checks for pending messages every few seconds.
POLL_INTERVAL_SECONDS = 5


# Runtime: Owns the long-running publisher and its database/queue resource lifetimes.
# Architecture: Retries persisted outbox records even when no new webhook arrives.
# Plain English: Keeps checking the database and sending work until the process is stopped.
async def main() -> None:
    # Runtime: Configures timestamped output suitable for Docker log collection.
    # Architecture: Gives each publication attempt an operational timestamp.
    # Plain English: Starts readable process logging.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    # Runtime: Creates one queue adapter for reuse throughout the process lifetime.
    # Architecture: Avoids rebuilding transport resources for every polling interval.
    # Plain English: Prepares the message sender.
    outbox_service = OutboxService()
    # Runtime: Creates a shared signal used to leave the loop cleanly.
    # Architecture: Allows the current batch to finish before shutdown.
    # Plain English: Provides a safe stop switch.
    shutdown_event = asyncio.Event()
    # Runtime: Provides access to asyncio's signal registration API.
    # Architecture: Connects container stop signals to the async shutdown mechanism.
    # Plain English: Sets up handling for stop requests.
    loop = asyncio.get_running_loop()

    # Runtime: Requests loop termination without cancelling active database or queue calls.
    # Architecture: Preserves orderly cleanup when the process receives a termination signal.
    # Plain English: Signals the publisher to stop after its current work.
    def request_shutdown() -> None:
        shutdown_event.set()

    # Runtime: Registers handlers for interactive and container termination signals.
    # Architecture: Supports graceful operation in both local runs and Docker deployments.
    # Plain English: Makes Ctrl+C and container stop initiate a clean exit.
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_shutdown)
        except NotImplementedError:
            signal.signal(signum, lambda _signum, _frame: request_shutdown())

    # Runtime: Announces startup after all required resources have been constructed.
    # Architecture: Gives operators an explicit process lifecycle marker.
    # Plain English: Confirms that the outbox publisher has started.
    logger.info("Outbox publisher started")
    try:
        # Runtime: Polls until a shutdown signal is received.
        # Architecture: Makes durable publication independent of inbound webhook traffic.
        # Plain English: Continues sending pending events in the background.
        while not shutdown_event.is_set():
            try:
                # Runtime: Opens a fresh session for one bounded publication batch.
                # Architecture: Prevents a long-lived session from retaining stale ORM state.
                # Plain English: Starts a new database work unit.
                async with SessionLocal() as session:
                    # Runtime: Publishes due events and commits published/retry metadata.
                    # Architecture: Reuses outbox locking and retry backoff semantics.
                    # Plain English: Sends a batch and remembers what succeeded or needs retry.
                    published = await outbox_service.publish_pending(session)
                # Runtime: Reports successful queue handoffs for operational monitoring.
                # Architecture: Provides a simple delivery throughput signal.
                # Plain English: Logs how many messages were sent.
                if published:
                    logger.info("Published %s outbox event(s)", published)
            except Exception:
                # Runtime: Logs the full unexpected error while preserving the persistent outbox rows.
                # Architecture: A later poll can recover from temporary database or process-level failures.
                # Plain English: Records the problem and keeps the dispatcher alive to try again.
                logger.exception("Outbox publication cycle failed")

            # Runtime: Waits for either new polling time or a shutdown request.
            # Architecture: Avoids a busy loop while allowing prompt graceful termination.
            # Plain English: Pauses briefly, unless the process is stopping.
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=POLL_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass
    finally:
        # Runtime: Removes registered OS signal callbacks before event-loop shutdown.
        # Architecture: Avoids leaving process-level handlers attached during cleanup.
        # Plain English: Unhooks stop handlers.
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError):
                pass
        # Runtime: Closes the Azure queue client even if polling or shutdown raises.
        # Architecture: Prevents async transport sockets from leaking on container restart.
        # Plain English: Releases the publisher's queue connection.
        await outbox_service.close()


# Runtime: Prevents imports from starting a background process as a side effect.
# Architecture: Keeps this module safe to inspect and test.
# Plain English: Runs the publisher only when launched as a script.
if __name__ == "__main__":
    # Runtime: Creates the event loop and awaits the publisher lifecycle.
    # Architecture: Hosts asynchronous PostgreSQL polling and Azure delivery.
    # Plain English: Starts the standalone outbox publisher.
    asyncio.run(main())
