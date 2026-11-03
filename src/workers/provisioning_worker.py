from src.services.alert_service import send_alert

import os
import signal
import asyncio
import json
import logging
import time
import traceback
from typing import Any

from azure.storage.queue.aio import QueueClient
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from src.core.config import settings
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.clickup_client import ClickUpClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("worker.provisioning")

async def process_message(message, queue_client: QueueClient) -> None:
    message_payload = None
    try:
        message_payload = json.loads(message.content)
        student_id = int(message_payload["id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        logger.error("Dropping malformed provisioning message")
        await queue_client.delete_message(message)
        return

    start_time = time.perf_counter()
    
    # Logic to wrap the entire consumption process to prevent one message from crashing the worker.
    try:
        async with SessionLocal() as session:
            # Retry Loop for Database Concurrency Issues
            max_db_retries = 3
            db_retry_count = 0
            
            while True:
                try:
                    # Attempt to claim the message
                    claimed = await session.execute(
                        update(Student)
                        .where(Student.id == student_id, Student.status.in_(("queued", "pending")))
                        .values(status="processing")
                    )
                    if claimed.rowcount != 1:
                        await session.rollback()
                        await queue_client.delete_message(message)
                        return
                    await session.commit()
                    break # Exit retry loop on success
                except DBAPIError as e:
                    await session.rollback()
                    # Check for PostgreSQL concurrency/deadlock codes
                    # 40P01: Deadlock Detected, 55P03: Lock Not Available, 40001: Serialization Failure
                    if e.orig.pgcode in ('40P01', '55P03', '40001'):
                        db_retry_count += 1
                        if db_retry_count < max_db_retries:
                            wait_time = min(2.0, 0.2 * (2 ** db_retry_count))
                            logger.warning(
                                f"[DB Lock Conflict] Concurrency issue on student_id={student_id} "
                                f"(attempt {db_retry_count}/{max_db_retries}): {e.orig}. "
                                f"Rolling back and retrying in {wait_time:.2f}s..."
                            )
                            await asyncio.sleep(wait_time)
                            continue
                    else:
                        raise # Re-raise if it's not a concurrency issue
                except Exception:
                    await session.rollback()
                    raise

            # Fetch student record
            result = await session.execute(select(Student).where(Student.id == student_id))
            student = result.scalar_one_or_none()
            if student is None:
                await queue_client.delete_message(message)
                return

            # Instantiate the hardened worker client
            clickup = ClickUpClient()
            
            payload = {
                "name": f"Student: {student.name}",
                "description": f"GHL Contact ID: {student.ghl_contact_id}\nProvisioned via PulseOps Worker",
                "status": "TO DO",
                "priority": 3,
            }
            
            try:
                # Use the hardened create_task method which handles retries, 429s, and timeouts
                # We pass student_id and ghl_contact_id for structured logging
                task_data = await clickup.create_task(
                    list_id=str(settings.CLICKUP_DEFAULT_LIST_ID),
                    task_name=f"Student: {student.name}",
                    description=f"GHL Contact ID: {student.ghl_contact_id}\nProvisioned via PulseOps Worker",
                    assignee_id=None,
                    student_id=str(student.id),
                    ghl_contact_id=str(student.ghl_contact_id)
                )
                
                student.clickup_task_id = task_data["id"]
                student.status = "completed"
                await session.commit()
                logger.info(
                    f"Success | student_id={student.id} | ghl_id={student.ghl_contact_id} | "
                    f"elapsed={((time.perf_counter() - start_time) * 1000):.2f}ms"
                )
            except Exception as e:
                await session.rollback()
                await session.execute(
                    update(Student)
                    .where(Student.id == student_id, Student.status == "processing")
                    .values(status="queued")
                )
                await session.commit()
                logger.error(f"Provisioning failed for student {student_id} after retries. Error: {e}")
                return

        # Success Case
        await queue_client.delete_message(message)
        logger.info("Provisioned student %s", student_id)

    except Exception as outer_err:
        # Final containment block for unhandled logic errors
        if 'session' in locals():
            await session.rollback()
        
        logger.critical(
            f"[Worker Logic Error] Unhandled exception processing student_id={student_id} "
            f"message_id={message.message_id}: {outer_err}", 
            exc_info=True
        )
        # Do not delete message from queue; let it reappear via visibility timeout (poison message handling)

async def main_worker() -> None:
    queue_client = QueueClient.from_connection_string(
        conn_str=settings.AZURE_STORAGE_CONNECTION_STRING,
        queue_name="student-provisioning",
    )
    try:
        await queue_client.create_queue()
    except Exception:
        logger.exception("Unable to create or access provisioning queue")
        await queue_client.close()
        raise

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
