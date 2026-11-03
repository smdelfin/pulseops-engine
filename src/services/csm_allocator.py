# Import the SQL count function and async session type used to measure active ownership.
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
# Import the ORM entity whose assigned work contributes to each CSM's workload.
from src.models.student import Student
# Import sequence typing for explicit candidate and workload contracts.
from typing import Dict, Iterable

class CSMAllocator:
    # - Defines which lifecycle states count as active CSM workload.
    # - Architectural Purpose: Excludes terminal records so assignments reflect current operational responsibility.
    # - Plain-English: 'Only count students who still need active attention.'
    ACTIVE_STATUSES = ("pending", "queued", "processing", "onboarding_started", "at_risk", "offboarding")

    # - Normalizes the configured CSM identifiers and validates the assignment pool.
    # - Architectural Purpose: Fails configuration early instead of silently assigning work to nobody.
    # - Plain-English: 'Prepare a clean list of people eligible to receive students.'
    def __init__(self, csm_ids: Iterable[str]):
        # - Trims whitespace, removes blank/duplicate identifiers, and sorts for deterministic behavior.
        self.csm_ids = tuple(sorted({csm_id.strip() for csm_id in csm_ids if csm_id.strip()}))
        # - Rejects an empty pool before any webhook can attempt assignment.
        if not self.csm_ids:
            raise ValueError("At least one CSM identifier is required")

    # - Selects the candidate with the smallest active workload and stable identifier tie-breaking.
    # - Architectural Purpose: Produces predictable assignments and balances CSM ownership.
    # - Plain-English: 'Choose the least-busy CSM, using name order if workloads tie.'
    @staticmethod
    def choose_least_loaded(csm_ids: Iterable[str], workloads: Dict[str, int]) -> str:
        # - Applies the same normalization to candidates supplied directly to this helper.
        candidates = tuple(sorted({csm_id.strip() for csm_id in csm_ids if csm_id.strip()}))
        # - Rejects invalid empty input instead of returning a misleading assignment.
        if not candidates:
            raise ValueError("At least one CSM identifier is required")
        # - Uses workload first and CSM ID second as a deterministic ordering key.
        return min(candidates, key=lambda csm_id: (workloads.get(csm_id, 0), csm_id))

    # - Reads current active ownership counts and chooses the next CSM for one student.
    # - Architectural Purpose: Performs workload allocation from current PostgreSQL state within the caller's async transaction.
    # - Plain-English: 'Count each CSM's active students, then assign to the person with the fewest.'
    async def get_next_csm(self, session: AsyncSession) -> str:
        # - Queries each configured CSM's count of students in active lifecycle states.
        result = await session.execute(
            # - Selects the assignee and aggregates the number of student rows.
            select(Student.assigned_csm_id, func.count(Student.id))
            # - Restricts counting to this assignment pool and statuses considered active.
            .where(
                Student.assigned_csm_id.in_(self.csm_ids),
                Student.status.in_(self.ACTIVE_STATUSES),
            )
            # - Produces one count row per assigned CSM.
            .group_by(Student.assigned_csm_id)
        )
        # - Converts query results to a lookup and ignores unassigned rows.
        workloads = {csm_id: count for csm_id, count in result.all() if csm_id is not None}
        # - Applies the shared deterministic selection rule to those counts.
        return self.choose_least_loaded(self.csm_ids, workloads)
