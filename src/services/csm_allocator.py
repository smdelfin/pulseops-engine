# Import the SQL count function and async session type used to measure active ownership.
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
# Import the ORM entity whose assigned work contributes to each CSM's workload.
from src.models.student import Student
# Import sequence typing for explicit candidate and workload contracts.
from typing import Dict, Iterable

class CSMAllocator:
    # Exclude terminal records so completed work does not bias new onboarding ownership.
    ACTIVE_STATUSES = ("pending", "queued", "processing", "onboarding_started", "at_risk", "offboarding")

    # Accept the configured candidate pool and reject an empty pool before processing traffic.
    def __init__(self, csm_ids: Iterable[str]):
        self.csm_ids = tuple(sorted({csm_id.strip() for csm_id in csm_ids if csm_id.strip()}))
        if not self.csm_ids:
            raise ValueError("At least one CSM identifier is required")

    # Select deterministically by smallest workload, then identifier for stable tie-breaking.
    @staticmethod
    def choose_least_loaded(csm_ids: Iterable[str], workloads: Dict[str, int]) -> str:
        candidates = tuple(sorted({csm_id.strip() for csm_id in csm_ids if csm_id.strip()}))
        if not candidates:
            raise ValueError("At least one CSM identifier is required")
        return min(candidates, key=lambda csm_id: (workloads.get(csm_id, 0), csm_id))

    # Read active ownership counts and assign the next student to the least-loaded CSM.
    async def get_next_csm(self, session: AsyncSession) -> str:
        result = await session.execute(
            select(Student.assigned_csm_id, func.count(Student.id))
            .where(
                Student.assigned_csm_id.in_(self.csm_ids),
                Student.status.in_(self.ACTIVE_STATUSES),
            )
            .group_by(Student.assigned_csm_id)
        )
        workloads = {csm_id: count for csm_id, count in result.all() if csm_id is not None}
        return self.choose_least_loaded(self.csm_ids, workloads)
