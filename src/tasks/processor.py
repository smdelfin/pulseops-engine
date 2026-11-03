import asyncio
import logging
import json
from ..services.queue_service import QueueService
from ..services.clickup_client import ClickUpClient
from ..services.csm_allocator import CSMAllocator
from ..core.db import SessionLocal
from ..models.student import Student
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import settings

logger = logging.getLogger(__name__)

# Pre-defined CSMs for the allocator (should ideally be in DB)
allocator = CSMAllocator(csm_ids=["csm_001", "csm_002", "csm_003"])
clickup_client = ClickUpClient()

async def process_queue():
    queue_service = QueueService()
    logger.info("Starting queue processor...")
    
    while True:
        messages = queue_service.receive_messages()
        for msg in messages:
            try:
                data = json.loads(msg.content)
                student_id = data.get("id")
                
                async with SessionLocal() as session:
                    # Check status
                    # In a real scenario, we'd fetch the student record here
                    # For this scaffold, we assume logic runs on the ID
                    
                    logger.info(f"Processing student ID: {student_id}")
                    
                    # Fetch student record
                    student = await session.execute(select(Student).where(Student.id == student_id))
                    student_obj = student.scalar_one()
                    
                    logger.info(f"Processing student record for '{student_obj.name}'")
                    
                    # 1. Create/Fetch ClickUp List
                    # Note: In this flow, we create a new list per student as per requirements
                    clickup_list_data = clickup_client.create_student_list(student_obj.name, "Initial Onboarding")
                    list_id = clickup_list_data.get("id")
                    
                    # 2. Assign CSM
                    csm_id = allocator.get_next_csm()
                    clickup_client.assign_csm(list_id, csm_id)
                    
                    # 3. Create Task
                    task_data = clickup_client.create_task(
                        list_id=list_id,
                        task_name=f"Onboarding: {student_obj.name}",
                        description=f"Welcome {student_obj.name}! Please begin the onboarding process.",
                        assignee_id=csm_id
                    )
                    task_id = task_data.get("id")
                    
                    # Update record with ClickUp details
                    student_obj.clickup_list_id = list_id
                    student_obj.clickup_task_id = task_id
                    student_obj.status = "completed"
                    
                    await session.commit()
                    logger.info(f"Successfully provisioned ClickUp for student ID {student_id} with Task ID {task_id}")
                    
                    # Delete message (simulated deletion as real Azurite/Azure Queue requires specific handles)
                    # queue_service.delete_message(msg)
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Logic for DLQ would go here
        
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(process_queue())
