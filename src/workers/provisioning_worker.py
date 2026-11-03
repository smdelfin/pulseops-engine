# Import the alert sink used when repeated worker failures need operator attention.
from src.services.alert_service import send_alert

# Import process control, async scheduling, message serialization, logging, timing, and traceback tools.
import os
import signal
import asyncio
import json
import logging
import time
import traceback
# Import a general typing helper for worker-facing values.
from typing import Any

# Import Azure's async queue client used to receive, acknowledge, and retry messages.
from azure.storage.queue.aio import QueueClient
# Import SQLAlchemy query/update primitives and database error classification.
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

# Import centralized deployment settings so credentials never live in worker logic.
from src.core.config import settings
# Import the per-operation async session factory and mapped student model.
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.clickup_client import ClickUpClient
from src.domain.lifecycle import InvalidStudentTransition, StudentDomainEvent, StudentStatus, transition_status
from src.models.student_transition import StudentTransition
from src.services.queue_service import QueueService


# Configure timestamped logs suitable for container stdout collection.
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# Name worker logs so they can be filtered from API and migration logs.
logger = logging.getLogger("worker.provisioning")

# - Processes one Azure Queue message through durable claiming, external provisioning, and acknowledgement.
# - Architectural Purpose: Combines database idempotency, external ClickUp work, and queue retry semantics at one worker boundary.
# - Plain-English: 'Take one queued student, set up the external task, and remove the message only when appropriate.'
async def process_message(message, queue_client: QueueClient) -> None:
    # Keep the decoded payload available for diagnostics if later processing fails.
    message_payload = None
    try:
        # Decode the queue's JSON body and normalize the identifier to an integer key.
        message_payload = json.loads(message.content)
        student_id = int(message_payload["id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        # Delete invalid poison messages because retrying malformed input cannot succeed.
        logger.error("Dropping malformed provisioning message")
        await queue_client.delete_message(message)
        return

    # - Sets a bounded delivery-attempt threshold before a message is sent to dead-letter storage.
    # - Architectural Purpose: Prevents poison messages from retrying forever and blocking queue capacity.
    # - Plain-English: 'Give a message a limited number of tries before isolating it.'
    max_dequeue_attempts = 5
    # - Routes over-retried messages to the dead-letter queue and removes the original queue item.
    if getattr(message, "dequeue_count", 1) > max_dequeue_attempts:
        await QueueService().dead_letter_message(message.content)
        await queue_client.delete_message(message)
        logger.error("Dead-lettered student provisioning message after %s attempts", message.dequeue_count)
        return

    # - Starts a monotonic timer for accurate elapsed-duration measurement.
    # - Architectural Purpose: Monotonic time is unaffected by wall-clock corrections during processing.
    # - Plain-English: 'Measure how long this job takes with a clock that only moves forward.'
    start_time = time.perf_counter()
    
    # - Contains all remaining message-processing errors so one item does not terminate the worker loop.
    # - Architectural Purpose: The outer boundary preserves queue service availability while allowing retry visibility.
    # - Plain-English: 'Handle a failure for this message without crashing the whole worker.'
    try:
        # Scope all database work to one async session and close it after processing.
        async with SessionLocal() as session:
            # - Establishes a finite retry policy for transient database lock conflicts.
            # - Architectural Purpose: Allows normal transaction contention to recover without masking persistent failures.
            # - Plain-English: 'Retry temporary database conflicts a few times, but do not spin forever.'
            # Bound lock-conflict retries so persistent database problems surface promptly.
            max_db_retries = 3
            # Track how many serialization/deadlock retries have already occurred.
            db_retry_count = 0
            
            # - Repeats only the claim operation when PostgreSQL reports a known transient conflict.
            while True:
                try:
                    # Attempt to claim the message
                    # Atomically claim only pending rows, preventing two workers from provisioning one student.
                    claimed = await session.execute(
                        update(Student)
                        .where(Student.id == student_id, Student.status.in_(("queued", "pending")))
                        .values(status="processing")
                    )
                    # Treat zero updated rows as already claimed, completed, or missing work.
                    if claimed.rowcount != 1:
                        await session.rollback()
                        await queue_client.delete_message(message)
                        return
                    # Commit the claim before calling ClickUp so another worker cannot duplicate the call.
                    await session.commit()
                    # - Stops retrying after the row has been successfully claimed and committed.
                    break # Exit retry loop on success
                except DBAPIError as e:
                    await session.rollback()
                    # Check for PostgreSQL concurrency/deadlock codes
                    # 40P01: Deadlock Detected, 55P03: Lock Not Available, 40001: Serialization Failure
                    # Retry only PostgreSQL errors known to be transient concurrency conflicts.
                    if e.orig.pgcode in ('40P01', '55P03', '40001'):
                        # Increment the bounded retry counter for this student claim.
                        db_retry_count += 1
                        if db_retry_count < max_db_retries:
                            # Increase delay modestly to reduce lock contention without long stalls.
                            wait_time = min(2.0, 0.2 * (2 ** db_retry_count))
                            logger.warning(
                                f"[DB Lock Conflict] Concurrency issue on student_id={student_id} "
                                f"(attempt {db_retry_count}/{max_db_retries}): {e.orig}. "
                                f"Rolling back and retrying in {wait_time:.2f}s..."
                            )
                            # Yield while the conflicting transaction completes.
                            await asyncio.sleep(wait_time)
                            continue
                    else:
                        raise # Re-raise if it's not a concurrency issue
                except Exception:
                    await session.rollback()
                    raise

            # Fetch student record
            # Reload current student state after the claim so external payloads use fresh data.
            result = await session.execute(select(Student).where(Student.id == student_id))
            student = result.scalar_one_or_none()
            # A deleted record has no useful external work and can be acknowledged safely.
            if student is None:
                await queue_client.delete_message(message)
                return

            # - Creates the configured ClickUp adapter for the external provisioning call.
            # - Architectural Purpose: The client owns bounded timeouts, retries, and provider error handling.
            # - Plain-English: 'Prepare the component that creates the ClickUp task.'
            # Create the hardened ClickUp client that owns timeout and retry policy.
            clickup = ClickUpClient()
            
            # Build the intended external task representation for logging/future provider use.
            # - Assembles a provider-shaped task summary from the freshly loaded student.
            payload = {
                "name": f"Student: {student.name}",
                "description": f"GHL Contact ID: {student.ghl_contact_id}\nProvisioned via PulseOps Worker",
                "status": "TO DO",
                "priority": 3,
            }
            
            try:
                # Use the hardened create_task method which handles retries, 429s, and timeouts
                # We pass student_id and ghl_contact_id for structured logging
                # Create the external task while preserving correlation IDs in client logs.
                task_data = await clickup.create_task(
                    list_id=str(settings.CLICKUP_DEFAULT_LIST_ID),
                    task_name=f"Student: {student.name}",
                    description=f"GHL Contact ID: {student.ghl_contact_id}\nProvisioned via PulseOps Worker",
                    assignee_id=None,
                    student_id=str(student.id),
                    ghl_contact_id=str(student.ghl_contact_id)
                )
                
                # - Stores ClickUp's task identifier so later synchronization can find the external record.
                # - Architectural Purpose: The external ID is persisted before local completion is committed.
                # - Plain-English: 'Remember the created ClickUp task on the student.'
                student.clickup_task_id = task_data["id"]
                # Mark completion only after ClickUp confirms task creation.
                # - Saves the pre-completion state for the immutable transition audit record.
                previous_status = student.status
                # - Moves the student through domain validation into the completed state.
                student.status = transition_status(previous_status, StudentStatus.COMPLETED).value
                # - Stages the status-change audit event in the same transaction as the student update.
                session.add(StudentTransition(
                    student_id=student.id,
                    from_status=previous_status,
                    to_status=student.status,
                    event_type=StudentDomainEvent(
                        event_type="student.provisioned",
                        aggregate_id=student.id,
                        payload={"clickup_task_id": student.clickup_task_id},
                    ).event_type,
                ))
                # Commit the external-success checkpoint so reruns remain idempotent.
                # - Persists the task reference, completed state, and audit history together.
                await session.commit()
                # - Emits structured timing and correlation details for operations monitoring.
                logger.info(
                    f"Success | student_id={student.id} | ghl_id={student.ghl_contact_id} | "
                    f"elapsed={((time.perf_counter() - start_time) * 1000):.2f}ms"
                )
            # - Handles provider or local persistence failures by restoring a retryable state.
            except Exception as e:
                # Undo any uncommitted local changes after an external failure.
                await session.rollback()
                # - Re-queues only a row still in processing, avoiding overwriting a concurrent state change.
                await session.execute(
                    update(Student)
                    .where(Student.id == student_id, Student.status == "processing")
                    .values(status=StudentStatus.QUEUED.value)
                )
                # Persist the queued state so a later queue delivery can retry provisioning.
                await session.commit()
                logger.error(f"Provisioning failed for student {student_id} after retries. Error: {e}")
                return

        # - Reaches acknowledgement only after the external task and local completion were committed.
        # Acknowledge only successful processing, removing the message from Azure's queue.
        await queue_client.delete_message(message)
        logger.info("Provisioned student %s", student_id)

    # - Catches unexpected worker logic errors outside the provider-specific recovery block.
    except Exception as outer_err:
        # Final containment block for unhandled logic errors
        # Roll back any open transaction before allowing the message to reappear.
        if 'session' in locals():
            await session.rollback()
        
        logger.critical(
            f"[Worker Logic Error] Unhandled exception processing student_id={student_id} "
            f"message_id={message.message_id}: {outer_err}", 
            exc_info=True
        )
        # Do not delete message from queue; let it reappear via visibility timeout (poison message handling)

# - Runs the queue consumer lifecycle, including initialization, signal handling, polling, and cleanup.
# - Architectural Purpose: Owns long-lived Azure resources and ensures graceful termination in container deployments.
# - Plain-English: 'Start the worker, keep checking for jobs, and close the queue connection when it stops.'
async def main_worker() -> None:
    # Construct the worker's long-lived async queue client from deployment configuration.
    queue_client = QueueClient.from_connection_string(
        conn_str=settings.AZURE_STORAGE_CONNECTION_STRING,
        queue_name="student-provisioning",
    )
    try:
        # Ensure the queue exists before entering the receive loop.
        await queue_client.create_queue()
    except Exception:
        logger.exception("Unable to create or access provisioning queue")
        await queue_client.close()
        raise

    # Announce readiness after queue initialization succeeds.
    logger.info("Provisioning worker started")
    consecutive_failures = 0
    max_failure_threshold = 3
    last_heartbeat = time.time()
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        # Set the event so the receive loop exits after its current batch.
        shutdown_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, request_shutdown)
        except NotImplementedError:
            signal.signal(signum, lambda _signum, _frame: request_shutdown())

    try:
        while not shutdown_event.is_set():
            received = False
            try:
                async for message in queue_client.receive_messages(
                    messages_per_page=10,
                    visibility_timeout=120,
                ):
                    received = True
                    await process_message(message, queue_client)

                if received:
                    consecutive_failures = 0
            except Exception as err:
                consecutive_failures += 1
                logger.error("Batch processing error: %s", err, exc_info=True)
                if consecutive_failures >= max_failure_threshold:
                    await send_alert(
                        subject="Worker Failure Threshold Exceeded",
                        message=f"Provisioning worker has failed {consecutive_failures} consecutive times.",
                        details={"error": str(err)}
                    )
                    consecutive_failures = 0

            if not received:
                if time.time() - last_heartbeat > 60:
                    logger.info("[Worker Heartbeat] Worker active and polling queue | PID: %s", os.getpid())
                    last_heartbeat = time.time()
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError):
                pass
        await queue_client.close()


if __name__ == "__main__":
    asyncio.run(main_worker())
