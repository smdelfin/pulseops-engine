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


# Configure timestamped logs suitable for container stdout collection.
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# Name worker logs so they can be filtered from API and migration logs.
logger = logging.getLogger("worker.provisioning")

# Process one queue message with database claiming, external provisioning, and acknowledgement.
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

    # Start a monotonic timer to measure end-to-end provisioning latency.
    start_time = time.perf_counter()
    
    # Logic to wrap the entire consumption process to prevent one message from crashing the worker.
    try:
        # Scope all database work to one async session and close it after processing.
        async with SessionLocal() as session:
            # Retry Loop for Database Concurrency Issues
            # Bound lock-conflict retries so persistent database problems surface promptly.
            max_db_retries = 3
            # Track how many serialization/deadlock retries have already occurred.
            db_retry_count = 0
            
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

            # Instantiate the hardened worker client
            # Create the hardened ClickUp client that owns timeout and retry policy.
            clickup = ClickUpClient()
            
            # Build the intended external task representation for logging/future provider use.
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
                
                # Persist the provider identifier before marking the local workflow complete.
                student.clickup_task_id = task_data["id"]
                # Mark completion only after ClickUp confirms task creation.
                student.status = "completed"
                # Commit the external-success checkpoint so reruns remain idempotent.
                await session.commit()
                logger.info(
                    f"Success | student_id={student.id} | ghl_id={student.ghl_contact_id} | "
                    f"elapsed={((time.perf_counter() - start_time) * 1000):.2f}ms"
                )
            except Exception as e:
                # Undo any uncommitted local changes after an external failure.
                await session.rollback()
                await session.execute(
                    update(Student)
                    .where(Student.id == student_id, Student.status == "processing")
                    .values(status="queued")
                )
                # Persist the queued state so a later queue delivery can retry provisioning.
                await session.commit()
                logger.error(f"Provisioning failed for student {student_id} after retries. Error: {e}")
                return

        # Success Case
        # Acknowledge only successful processing, removing the message from Azure's queue.
        await queue_client.delete_message(message)
        logger.info("Provisioned student %s", student_id)

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
            MAX_FAILURE_THRESHOLD = 3
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
                        logger.error(f"Batch processing error: {err}")
                        if consecutive_failures >= MAX_FAILURE_THRESHOLD:
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
                            break
                        except asyncio.TimeoutError:
                            continue
            finally:
                await queue_client.close()


if __name__ == "__main__":
    asyncio.run(main_worker())
