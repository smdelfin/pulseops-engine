import asyncio
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import engine, SessionLocal
from src.models.student import Student
from src.services.student_auditor import StudentAuditor
from src.services.alert_service import send_csm_sla_alert
from src.services.clickup_client import ClickUpClient

logger = logging.getLogger(__name__)

async def main():
    auditor = StudentAuditor()
    clickup_client = ClickUpClient()
    breaches: List[Dict[str, Any]] = []

    async with AsyncSession(engine) as session:
        # 1. Database Query: Fetch active, non-paused students
        stmt = select(Student).where(
            ~Student.status.in_(['completed', 'cancelled']),
            Student.is_paused == False
        )
        result = await session.execute(stmt)
        students = result.scalars().all()

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
            evaluation = auditor.evaluate_student(student)
            if evaluation:
                breaches.append(evaluation)

    # 4. Output & Alert Dispatch
    if breaches:
        # Print ASCII Summary
        header = f"{'| Student ID | Name | Program | Assigned CSM | Breach Type | Elapsed Time |':^85}"
        print(header)
        print("-" * 85)
        for b in breaches:
            print(f"| {b['student_id']:<10} | {b['name']:<14} | {b['program']:<11} | {str(b['csm_id']):<12} | {b['breach_type']:<13} | {b['elapsed_hours']:<13} |")
        
        # Dispatch Alert
        await send_csm_sla_alert(breaches)
    else:
        print("Audit complete: No breaches detected.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Ensure engine is disposed
        from src.core.db import engine
        engine.dispose()
