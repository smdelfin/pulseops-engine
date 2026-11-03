# Runtime: Provides the event loop for asynchronous reconciliation.
# Architecture: Matches async SQLAlchemy and ClickUp client operations.
# Plain English: Runs coroutine-based work.
import asyncio
# Runtime: Provides operational logging for repair decisions.
# Architecture: Makes database and integration corrections observable.
# Plain English: Writes diagnostic messages.
import logging
# Runtime: Parses the optional --fix command-line switch.
# Architecture: Separates safe reporting from mutating maintenance runs.
# Plain English: Reads script options.
import argparse
from uuid import uuid4
# Runtime: Supplies the cutoff timestamp used to select stale records.
# Architecture: Limits reconciliation work to records that have stopped changing.
# Plain English: Calculates which active records have been inactive too long.
from datetime import datetime, timedelta
# Runtime: Documents collection and result shapes.
# Architecture: Clarifies data exchanged during cross-system reconciliation.
# Plain English: Provides type annotations.

# Runtime: Builds ORM queries and boolean predicates.
# Architecture: Reads Student rows from PostgreSQL via SQLAlchemy.
# Plain English: Provides database query tools.
from sqlalchemy import select

from src.core.db import SessionLocal
from src.domain.lifecycle import StudentStatus, transition_status
from src.domain.provisioning import ProvisioningMessage
from src.models.messaging import OutboxEvent
from src.models.student import Student
from src.models.student_transition import StudentTransition
from src.services.clickup_client import (
    ClickUpAPIError,
    ClickUpClient,
    ClickUpNotFoundError,
    ClickUpTimeoutError,
)
from src.services.outbox_service import OutboxService

# Runtime: Creates a named logger for reconciliation actions.
# Architecture: Integrates repair decisions with application observability.
# Plain English: Gives the script a logger.
logger = logging.getLogger(__name__)


def classify_clickup_error(error: ClickUpAPIError) -> str:
    # Treat only the typed 404 as proof that the task does not exist.
    if isinstance(error, ClickUpNotFoundError):
        return "CONFIRMED_MISSING_IN_CLICKUP"
    # Keep exhausted connectivity failures distinct so they can never trigger destructive repair.
    if isinstance(error, ClickUpTimeoutError):
        return "CLICKUP_UNAVAILABLE"
    # Preserve the actual HTTP code for auth, throttling, and provider-server diagnostics.
    return f"CLICKUP_HTTP_ERROR_{error.status_code or 'UNKNOWN'}"


# Runtime: Defines the async reconciliation pass and its dry-run/fix mode.
# Architecture: Compares Postgres onboarding state with ClickUp task state.
# Plain English: Finds records that may be stuck or inconsistent.
async def reconcile_students(fix: bool):
    # Runtime: Opens an async ORM session using the application's session factory.
    # Architecture: Reads and optionally updates the shared PostgreSQL database.
    # Plain English: Starts a database work context.
    async with SessionLocal() as session:
        # 1. Criteria & Query
        # Runtime: Computes a UTC cutoff for records untouched for twelve hours.
        # Architecture: Identifies likely stalled provisioning work.
        # Plain English: Marks older records as candidates.
        cutoff_time = datetime.utcnow() - timedelta(hours=12)
        
        # Runtime: Builds a query for stale students in operational lifecycle states.
        # Architecture: Narrows reconciliation to records requiring cross-system review.
        # Plain English: Selects suspicious onboarding rows.
        query = select(Student).where(
            Student.status.in_(
                (
                    StudentStatus.PENDING.value,
                    StudentStatus.QUEUED.value,
                    StudentStatus.PROCESSING.value,
                    StudentStatus.ONBOARDING_STARTED.value,
                    StudentStatus.AT_RISK.value,
                )
            ),
            Student.updated_at < cutoff_time,
        )
        
        # Runtime: Executes the candidate query asynchronously against PostgreSQL.
        # Architecture: Uses the same ORM boundary as FastAPI services.
        # Plain English: Fetches records needing review.
        result = await session.execute(query)
        # Runtime: Converts database results into Student model instances.
        # Architecture: Gives the reconciliation logic typed domain objects.
        # Plain English: Collects the selected students.
        students = result.scalars().all()
        
        # Runtime: Creates a client for ClickUp API lookups.
        # Architecture: Provides external truth for task existence checks.
        # Plain English: Prepares to compare each student with ClickUp.
        clickup = ClickUpClient()
        # Runtime: Allocates the report rows accumulated during comparison.
        # Architecture: Decouples diagnostic output from later fix actions.
        # Plain English: Starts the reconciliation report.
        reconciled_data = []

        # 2. ClickUp Cross-Referencing
        # Runtime: Evaluates each candidate against its external task.
        # Architecture: Correlates Postgres records with ClickUp by task ID.
        # Plain English: Reviews students one at a time.
        for student in students:
            # Runtime: Initializes the comparison result before branching.
            # Architecture: Guarantees every candidate gets a report verdict.
            # Plain English: Starts with no decision.
            if not student.clickup_task_id:
                verdict = "NO_TASK_REFERENCE"
            else:
                try:
                    await clickup._request_with_retry("GET", f"/task/{student.clickup_task_id}", student_id=str(student.id))
                    verdict = "TASK_EXISTS"
                except ClickUpAPIError as exc:
                    verdict = classify_clickup_error(exc)

            reconciled_data.append({
                "student": student,
                "id": student.id,
                "name": student.name,
                "db_status": student.status,
                "clickup_id": student.clickup_task_id or "NULL",
                "verdict": verdict
            })

        # 3. Output Summary Table
        # Runtime: Prints column headings for the human-readable reconciliation report.
        # Architecture: Makes dry-run output useful to operators without another UI.
        # Plain English: Labels the report columns.
        print(f"{'Student ID':<12} | {'Name':<20} | {'DB Status':<10} | {'ClickUp ID':<15} | {'Verdict':<18}")
        # Runtime: Prints a fixed-width separator matching the report layout.
        # Architecture: Improves readability in terminal and container logs.
        # Plain English: Draws a line under the headings.
        print("-" * 85)
        # Runtime: Formats every collected report row into aligned text.
        # Architecture: Provides a compact operational view of cross-system state.
        # Plain English: Displays each student's result.
        for row in reconciled_data:
            print(f"{row['id']:<12} | {row['name'][:20]:<20} | {row['db_status']:<10} | {row['clickup_id']:<15} | {row['verdict']:<18}")

        # 4. Reconciliation Actions
        # Runtime: Chooses between mutating repair mode and read-only reporting.
        # Architecture: Makes corrective writes explicit and safe by default.
        # Plain English: Decides whether to apply fixes.
        if fix:
            repaired = 0
            for row in reconciled_data:
                student = row["student"]
                # Do not mutate local state unless the provider explicitly confirms a 404.
                if row["verdict"] != "CONFIRMED_MISSING_IN_CLICKUP":
                    continue
                current = await session.execute(
                    select(Student.status, Student.clickup_task_id)
                    .where(Student.id == student.id)
                    .with_for_update()
                )
                current_state = current.one_or_none()
                if current_state is None:
                    continue
                current_status, current_clickup_task_id = current_state
                if current_clickup_task_id != row["clickup_id"]:
                    logger.info(
                        "Skipping reconciliation for student %s because its ClickUp task reference changed",
                        student.id,
                    )
                    continue
                # Keep terminal, at-risk, and onboarding records out of the automatic retry path.
                if current_status not in {
                    StudentStatus.PENDING.value,
                    StudentStatus.QUEUED.value,
                    StudentStatus.PROCESSING.value,
                }:
                    logger.warning(
                        "ClickUp task is missing but student %s is in non-retryable status %s",
                        student.id,
                        current_status,
                    )
                    continue

                previous_status = current_status
                # Re-enter the only worker-claimable lifecycle state through domain validation.
                target_status = transition_status(previous_status, StudentStatus.QUEUED)
                # Clear the stale external key so successful reprovisioning can store its new task ID.
                student.clickup_task_id = None
                student.status = target_status.value
                # Record non-no-op lifecycle changes in the audit history.
                if previous_status != target_status.value:
                    session.add(StudentTransition(
                        student_id=student.id,
                        from_status=previous_status,
                        to_status=target_status.value,
                        event_type="student.reconciliation-requeued",
                        reason="ClickUp confirmed the referenced task no longer exists",
                    ))
                # Commit retry intent to the transactional outbox with the worker's shared payload contract.
                session.add(OutboxEvent(
                    id=str(uuid4()),
                    event_type="student.provisioning.requested",
                    aggregate_id=student.id,
                    payload=ProvisioningMessage(id=student.id).model_dump(),
                ))
                repaired += 1

            if repaired:
                # Persist student repair and queue intent atomically before trying Azure delivery.
                await session.commit()
                # Send due commands; failed publication remains retryable in PostgreSQL.
                await OutboxService().publish_pending(session)
            else:
                await session.rollback()
            print(f"\nReconciliation fixes applied: {repaired}")
        else:
            print("\nDry-run complete. Use --fix to apply changes.")

 # Runtime: Defines the CLI async entrypoint.
# Architecture: Converts parsed options into one reconciliation run.
# Plain English: Starts the command-line workflow.
async def main():
    # Runtime: Creates an argument parser for operator-facing options.
    # Architecture: Keeps dry-run default and mutation opt-in.
    # Plain English: Prepares to read command-line flags.
    parser = argparse.ArgumentParser(description="Reconcile student records with ClickUp.")
    # Runtime: Registers a boolean flag that enables database/queue repairs.
    # Architecture: Prevents accidental writes during inspection.
    # Plain English: Adds the optional --fix switch.
    parser.add_argument("--fix", action="store_true", help="Apply fixes to the database and queue.")
    # Runtime: Parses the current process arguments.
    # Architecture: Produces the operator's requested reconciliation mode.
    # Plain English: Reads the command line.
    args = parser.parse_args()

    # Runtime: Awaits the reconciliation pass using the parsed flag.
    # Architecture: Runs the comparison and optional durable updates.
    # Plain English: Performs the requested check.
    await reconcile_students(fix=args.fix)

# Runtime: Prevents reconciliation during module import.
# Architecture: Keeps maintenance actions explicit.
# Plain English: Runs the CLI only when launched directly.
if __name__ == "__main__":
    # Runtime: Creates the event loop and executes the CLI coroutine.
    # Architecture: Hosts async Postgres and ClickUp calls.
    # Plain English: Starts reconciliation.
    asyncio.run(main())
