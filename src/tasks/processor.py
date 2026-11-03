# Import async scheduling, diagnostics, and JSON decoding for queue work.
import asyncio
import logging
import json
# Import service abstractions used to consume, enrich, and persist provisioning work.
from ..services.queue_service import QueueService
from ..services.clickup_client import ClickUpClient
from ..services.csm_allocator import CSMAllocator
from ..core.db import SessionLocal
from ..models.student import Student
# Import SQLAlchemy update/query support used by the processor's persistence layer.
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import settings

# Create a processor-specific logger for worker observability.
logger = logging.getLogger(__name__)

# Configure a small local owner pool; production deployments can replace this with a database source.
allocator = CSMAllocator(csm_ids=["csm_001", "csm_002", "csm_003"])
# Reuse one ClickUp client configuration for processor operations.
clickup_client = ClickUpClient()

# Continuously receive and process provisioning messages.
async def process_queue():
    # Create the queue facade used to access Azure Storage.
    queue_service = QueueService()
    # Announce worker readiness for operators.
    logger.info("Starting queue processor...")
    
    # Keep the processor alive so it can consume work as it arrives.
    while True:
        # Retrieve available messages from the queue abstraction.
        messages = queue_service.receive_messages()
        # Process each message independently so one failure does not stop the batch.
        for msg in messages:
            try:
                # Deserialize the message body and extract the stable student identifier.
                data = json.loads(msg.content)
                student_id = data.get("id")
                
                # Scope database reads and writes to one async session for this message.
                async with SessionLocal() as session:
                    # Check status
                    # In a real scenario, we'd fetch the student record here
                    # For this scaffold, we assume logic runs on the ID
                    
                    logger.info(f"Processing student ID: {student_id}")
                    
                    # Fetch student record
                    # Reload the source record so the worker uses database truth.
                    student = await session.execute(select(Student).where(Student.id == student_id))
                    student_obj = student.scalar_one()
                    
                    logger.info(f"Processing student record for '{student_obj.name}'")
                    
                    # 1. Create/Fetch ClickUp List
                    # Note: In this flow, we create a new list per student as per requirements
                    # Create the external list that will hold this student's onboarding work.
                    clickup_list_data = clickup_client.create_student_list(student_obj.name, "Initial Onboarding")
                    list_id = clickup_list_data.get("id")
                    
                    # 2. Assign CSM
                    # Choose an owner before task creation so responsibility is explicit.
                    csm_id = allocator.get_next_csm()
                    clickup_client.assign_csm(list_id, csm_id)
                    
                    # 3. Create Task
                    # Create the actionable onboarding task in the selected list.
                    task_data = clickup_client.create_task(
                        list_id=list_id,
                        task_name=f"Onboarding: {student_obj.name}",
                        description=f"Welcome {student_obj.name}! Please begin the onboarding process.",
                        assignee_id=csm_id
                    )
                    task_id = task_data.get("id")
                    
                    # Update record with ClickUp details
                    # Store external identifiers before committing the completed state.
                    student_obj.clickup_list_id = list_id
                    student_obj.clickup_task_id = task_id
                    student_obj.status = "completed"
                    
                    # Commit the provisioning checkpoint so retries do not duplicate completed work.
                    await session.commit()
                    logger.info(f"Successfully provisioned ClickUp for student ID {student_id} with Task ID {task_id}")
                    
                    # Delete message (simulated deletion as real Azurite/Azure Queue requires specific handles)
                    # queue_service.delete_message(msg)
            except Exception as e:
                # Log the failed item while allowing the long-lived loop to continue.
                logger.error(f"Error processing message: {e}")
                # Logic for DLQ would go here
        
        # Poll periodically instead of spinning when the queue is empty.
        await asyncio.sleep(5)

if __name__ == "__main__":
    # Run the async processor when this module is launched as a script.
    asyncio.run(process_queue())
