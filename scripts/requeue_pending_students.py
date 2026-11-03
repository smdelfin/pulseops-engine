import asyncio
import json
import logging
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.core.db import SessionLocal
from src.models.student import Student
from src.services.queue_service import QueueService

# Configure logger for the recovery script
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def main() -> None:
    """
    Identifies unprovisioned students and pushes them back into the Azure Storage Queue.
    """
    # Use the existing database engine/session setup from the core project
    # Note: Since the project uses SessionLocal, we ensure we use it or create a matching async one
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=SessionLocal, bind=engine, autocommit=False, autoflush=False)

    queue_service = QueueService()
    requeued_count = 0

    try:
        async with async_session() as session:
            # Fetch students in 'pending' state or missing a ClickUp task ID
            stmt = select(Student).where(
                or_(
                    Student.status == "pending",
                    Student.clickup_task_id.is_(None)
                )
            )
            result = await session.execute(stmt)
            students = result.scalars().all()

            for student in students:
                payload = {
                    "student_id": student.id,
                    "name": student.name,
                    "ghl_contact_id": student.ghl_contact_id
                }
                
                # Push to Azure Storage Queue via the project's QueueService
                await queue_service.push_message(json.dumps(payload))
                
                print(f"[RECOVERY] Re-enqueued student ID: {student.id} | Name: {student.name} | GHL ID: {student.ghl_contact_id}")
                requeued_count += 1

        print(f"Recovery completed. Total records re-enqueued: {requeued_count}")

    except Exception as e:
        logger.error(f"Recovery script failed: {e}")
        raise
    finally:
        # Ensure connections are closed
        await queue_service.close()
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
