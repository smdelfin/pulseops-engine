# Runtime: Provides the event loop used by asynchronous database and ClickUp calls.
# Architecture: Matches FastAPI's non-blocking service model.
# Plain English: Runs coroutine-based operations.
import asyncio
# Runtime: Provides structured operational logging.
# Architecture: Reports integration failures to process logs.
# Plain English: Writes diagnostic messages.
import logging
# Runtime: Supplies type annotations for breach collections and values.
# Architecture: Documents the data exchanged between the auditor and alert service.
# Plain English: Describes expected Python value shapes.
from typing import List, Dict, Any, Optional

# Runtime: Builds SQL SELECT statements for PostgreSQL through SQLAlchemy.
# Architecture: Reads student state using the application's ORM layer.
# Plain English: Lets the script query students.
from sqlalchemy import select
# Runtime: Provides an async ORM session context.
# Architecture: Keeps PostgreSQL I/O cooperative with the event loop.
# Plain English: Opens a database conversation without blocking.
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import engine, SessionLocal
from src.models.student import Student
from src.services.student_auditor import StudentAuditor
from src.services.alert_service import send_csm_sla_alert
from src.services.clickup_client import ClickUpClient

# Runtime: Creates a module logger for audit failures.
# Architecture: Integrates this scheduled job with application observability.
# Plain English: Gives the auditor a named logger.
logger = logging.getLogger(__name__)

# Runtime: Defines the asynchronous SLA audit entrypoint.
# Architecture: Combines Postgres state, ClickUp state, and alert dispatch.
# Plain English: Runs one complete audit pass.
async def main():
    # Runtime: Instantiates the rule evaluator.
    # Architecture: Centralizes SLA policy rather than duplicating it in the script.
    # Plain English: Creates the component that decides whether a student breached SLA.
    auditor = StudentAuditor()
    # Runtime: Instantiates the ClickUp API client.
    # Architecture: Enables cross-system consistency checks against the external task record.
    # Plain English: Creates the ClickUp connection helper.
    clickup_client = ClickUpClient()
    # Runtime: Allocates the accumulator sent to the CSM alert service.
    # Architecture: Collects database and integration breaches into one notification batch.
    # Plain English: Starts an empty list of problems.
    breaches: List[Dict[str, Any]] = []

    # Runtime: Opens an async SQLAlchemy session and closes it on exit.
    # Architecture: Reads PostgreSQL state using the same connection lifecycle as the API.
    # Plain English: Starts a safe database query context.
    async with AsyncSession(engine) as session:
        # 1. Database Query: Fetch active, non-paused students
        # Runtime: Builds a parameterized query excluding terminal and paused records.
        # Architecture: Limits SLA work to active students who can still breach policy.
        # Plain English: Selects students that need auditing.
        stmt = select(Student).where(
            ~Student.status.in_(['completed', 'cancelled']),
            Student.is_paused == False
        )
        # Runtime: Sends the SELECT to PostgreSQL without blocking the event loop.
        # Architecture: Uses SQLAlchemy's async adapter for the service database.
        # Plain English: Runs the student query.
        result = await session.execute(stmt)
        # Runtime: Converts ORM results into a concrete list of Student objects.
        # Architecture: Gives the audit loop stable model instances.
        # Plain English: Collects the matching students.
        students = result.scalars().all()

        # Runtime: Evaluates each active student against integration and SLA rules.
        # Architecture: Keeps one student's failure from skipping other audit records.
        # Plain English: Checks students one by one.
        for student in students:
            # 2. Cross-Platform Sync Check
            if student.clickup_task_id:
                try:
                    # Fetch task details from ClickUp
                    # Note: Using the internal request method as a standalone getter
                    task_data = await clickup_client._request_with_retry(
                        "GET", 
                        f"/task/{student.clickup_task_id}",
                        student_id=str(student.id),
                        ghl_contact_id=student.ghl_contact_id
                    )
                    
                    clickup_status = task_data.get("status")
                    if clickup_status != student.status:
                        breaches.append({
                            "student_id": student.id,
                            "name": student.name,
                            "program": student.program_type,
                            "csm_id": student.assigned_csm_id,
                            "breach_type": "OUT_OF_SYNC",
                            "elapsed_hours": 0.0,
                            "threshold_hours": 0.0,
                            "details": f"DB: {student.status}, ClickUp: {clickup_status}"
                        })
                except Exception as e:
                    logger.error(f"Failed to sync ClickUp for student {student.id}: {e}")

            # 3. Run Auditor Evaluation
            # Runtime: Applies the configured SLA policy to the current ORM model.
            # Architecture: Produces a normalized breach record for alert dispatch.
            # Plain English: Asks whether this student needs attention.
            evaluation = auditor.evaluate_student(student)
            if evaluation:
                breaches.append(evaluation)

    # 4. Output & Alert Dispatch
    # Runtime: Branches based on whether any breach records were collected.
    # Architecture: Avoids sending empty alerts while preserving an observable no-op run.
    # Plain English: Decides whether to alert or report a clean audit.
    if breaches:
        # Print ASCII Summary
        header = f"{'| Student ID | Name | Program | Assigned CSM | Breach Type | Elapsed Time |':^85}"
        print(header)
        print("-" * 85)
        for b in breaches:
            print(f"| {b['student_id']:<10} | {b['name']:<14} | {b['program']:<11} | {str(b['csm_id']):<12} | {b['breach_type']:<13} | {b['elapsed_hours']:<13} |")
        
        # Dispatch Alert
        # Runtime: Awaits asynchronous notification delivery.
        # Architecture: Sends one consolidated alert to responsible CSMs.
        # Plain English: Notifies people about all detected breaches.
        await send_csm_sla_alert(breaches)
    else:
        print("Audit complete: No breaches detected.")

# Runtime: Restricts scheduled execution to direct CLI use.
# Architecture: Keeps importing the audit function side-effect free.
# Plain English: Starts the audit only when launched as a script.
if __name__ == "__main__":
    # Runtime: Wraps the async audit in a process-level cleanup block.
    # Architecture: Ensures SQLAlchemy's engine is disposed after scheduled execution.
    # Plain English: Runs the audit and always cleans up database resources.
    try:
        # Runtime: Creates an event loop and executes the audit coroutine.
        # Architecture: Hosts async PostgreSQL and ClickUp operations.
        # Plain English: Starts the audit pass.
        asyncio.run(main())
    finally:
        # Ensure engine is disposed
        # Runtime: Imports the shared engine for final resource cleanup.
        # Architecture: Reuses the application's configured database lifecycle.
        # Plain English: Gets the engine that must be closed.
        from src.core.db import engine
        # Runtime: Releases pooled connections and async driver resources.
        # Architecture: Prevents connection leaks in a recurring job.
        # Plain English: Closes the database engine.
        engine.dispose()
