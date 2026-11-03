# Runtime: Provides the event loop for asynchronous database and queue operations.
# Architecture: Matches the async service runtime used by FastAPI.
# Plain English: Runs coroutine-based recovery work.
import asyncio
# Runtime: Serializes student records into queue message JSON.
# Architecture: Matches Azure Storage Queue's text-message boundary.
# Plain English: Turns Python data into a message string.
import json
# Runtime: Provides operational logging for recovery failures.
# Architecture: Sends diagnostics to the same process log pipeline as workers.
# Plain English: Writes error information.
import logging
# Runtime: Builds ORM SELECT expressions and OR predicates.
# Architecture: Queries PostgreSQL through SQLAlchemy's model layer.
# Plain English: Lets the script find pending students.
from sqlalchemy import select, or_
# Runtime: Creates an asynchronous SQLAlchemy engine.
# Architecture: Enables non-blocking PostgreSQL access in this maintenance job.
# Plain English: Opens async database connections.
from sqlalchemy.ext.asyncio import create_async_engine
# Runtime: Creates async session factories for ORM work.
# Architecture: Provides transactional database contexts.
# Plain English: Builds reusable database sessions.
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.queue_service import QueueService

# Configure logger for the recovery script
# Runtime: Creates a named recovery logger.
# Architecture: Makes scheduled repair failures searchable in service logs.
# Plain English: Gives the script a logger.
logger = logging.getLogger(__name__)
# Runtime: Sets the default logging threshold for this standalone process.
# Architecture: Ensures recovery diagnostics are emitted in local/container runs.
# Plain English: Turns on informational logs.
logging.basicConfig(level=logging.INFO)

# Runtime: Defines the asynchronous recovery entrypoint.
# Architecture: Requeues database records into the Azure-backed work pipeline.
# Plain English: Finds work that needs another provisioning attempt.
async def main() -> None:
    """
    Identifies unprovisioned students and pushes them back into the Azure Storage Queue.
    """
    # Use the existing database engine/session setup from the core project
    # Note: Since the project uses SessionLocal, we ensure we use it or create a matching async one
    # Runtime: Creates an async PostgreSQL engine using centralized application settings.
    # Architecture: Connects this repair utility to the same database as FastAPI.
    # Plain English: Opens the database connection factory.
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    # Runtime: Creates a session factory bound to the async engine.
    # Architecture: Keeps each recovery query inside an explicit ORM session.
    # Plain English: Prepares sessions for database work.
    async_session = sessionmaker(engine, expire_on_commit=False, class_=SessionLocal, bind=engine, autocommit=False, autoflush=False)

    # Runtime: Instantiates the project's queue abstraction.
    # Architecture: Keeps Azure Storage Queue details behind a shared service.
    # Plain English: Creates the sender used to put work back on the queue.
    queue_service = QueueService()
    # Runtime: Initializes the batch counter.
    # Architecture: Provides an operational total for the recovery run.
    # Plain English: Starts counting requeued records.
    requeued_count = 0

    # Runtime: Begins exception/finalization handling for all resources.
    # Architecture: Guarantees queue and database cleanup on success or failure.
    # Plain English: Runs recovery while preparing to clean up.
    try:
        # Runtime: Opens and automatically closes an ORM session.
        # Architecture: Bounds PostgreSQL resources to the recovery batch.
        # Plain English: Starts querying students.
        async with async_session() as session:
            # Fetch students in 'pending' state or missing a ClickUp task ID
            # Runtime: Builds a query matching pending or unprovisioned rows.
            # Architecture: Finds records whose work may have been lost from Azure Queue.
            # Plain English: Selects students that need another attempt.
            stmt = select(Student).where(
                or_(
                    Student.status == "pending",
                    Student.clickup_task_id.is_(None)
                )
            )
            # Runtime: Executes the query asynchronously.
            # Architecture: Reads PostgreSQL without blocking other async work.
            # Plain English: Runs the recovery lookup.
            result = await session.execute(stmt)
            # Runtime: Materializes ORM objects from the query result.
            # Architecture: Gives the queue payload builder application models.
            # Plain English: Collects matching students.
            students = result.scalars().all()

            # Runtime: Iterates over each selected record.
            # Architecture: Reconstructs one independent queue message per student.
            # Plain English: Processes every recovery candidate.
            for student in students:
                # Runtime: Builds the minimal JSON-safe message body.
                # Architecture: Preserves identifiers needed by provisioning_worker.
                # Plain English: Describes the student to the queue consumer.
                payload = {
                    "student_id": student.id,
                    "name": student.name,
                    "ghl_contact_id": student.ghl_contact_id
                }
                
                # Push to Azure Storage Queue via the project's QueueService
                # Runtime: Serializes the payload and asynchronously sends it to Azure Queue.
                # Architecture: Re-enters the normal provisioning pipeline.
                # Plain English: Puts the student back into the work queue.
                await queue_service.push_message(json.dumps(payload))
                
                print(f"[RECOVERY] Re-enqueued student ID: {student.id} | Name: {student.name} | GHL ID: {student.ghl_contact_id}")
                requeued_count += 1

        # Runtime: Reports the completed batch count after all sends finish.
        # Architecture: Gives operators a reconciliation total.
        # Plain English: Announces how many records were recovered.
        print(f"Recovery completed. Total records re-enqueued: {requeued_count}")

    # Runtime: Logs and propagates unexpected recovery failures.
    # Architecture: Preserves failure semantics for schedulers and monitoring.
    # Plain English: Records the problem, then lets the run fail.
    except Exception as e:
        logger.error(f"Recovery script failed: {e}")
        raise
    finally:
        # Ensure connections are closed
        # Runtime: Closes the queue client and network resources.
        # Architecture: Prevents Azure SDK connections from leaking between runs.
        # Plain English: Shuts down the queue service.
        await queue_service.close()
        # Runtime: Disposes the async database engine and pooled connections.
        # Architecture: Completes the maintenance job's resource lifecycle.
        # Plain English: Closes the database.
        await engine.dispose()

# Runtime: Runs recovery only when this module is launched directly.
# Architecture: Keeps imports from triggering database or queue side effects.
# Plain English: Starts the script's async entrypoint.
if __name__ == "__main__":
    # Runtime: Creates an event loop and executes the recovery coroutine.
    # Architecture: Hosts async PostgreSQL and Azure Queue operations.
    # Plain English: Runs the recovery job.
    asyncio.run(main())
