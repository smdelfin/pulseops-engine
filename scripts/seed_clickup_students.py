# Runtime: Provides the event loop for async database seeding.
# Architecture: Uses the same async PostgreSQL stack as the API and workers.
# Plain English: Runs the demo setup without blocking database operations.
import asyncio
# Runtime: Parses the explicit --apply option for persistent demo data creation.
# Architecture: Keeps the default invocation safe and read-only.
# Plain English: Lets the operator preview or explicitly create demo records.
import argparse
import os
# Runtime: Resolves the repository .env file independently of the current shell directory.
# Architecture: Uses the project's established local configuration source.
# Plain English: Finds the project's environment settings.
from pathlib import Path
import sys

# Runtime: Loads configured environment values before importing application settings.
# Architecture: Ensures database and integration configuration is available at module startup.
# Plain English: Makes the local settings available to this script.
from dotenv import load_dotenv

# Runtime: Resolves the repository root and conventional environment file before app imports.
# Architecture: Ensures Pydantic settings use the same local configuration regardless of shell directory.
# Plain English: Loads project settings before database and service modules initialize.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
# Runtime: Adds the project root so path-based and module-based invocations can import app modules.
# Architecture: Makes the documented script command compatible with the repository package layout.
# Plain English: Lets the script find the application's `src` package.
sys.path.insert(0, str(ENV_PATH.parent))
from src.domain.student_tags import build_student_tags
# Runtime: Loads configured values without overriding variables already set by Docker or the shell.
# Architecture: Preserves environment-specific deployment configuration precedence.
# Plain English: Reads the local .env file when values were not supplied another way.
load_dotenv(dotenv_path=ENV_PATH)

# Runtime: Defines synthetic students using fields supported by the current Student model.
# Architecture: Exercises program/cohort segmentation, health signals, and CSM assignment.
# Plain English: Lists realistic but fictional records for the interview demo.
DEMO_STUDENTS = (
    {
        "name": "Marcus Vance",
        "ghl_contact_id": "demo-pulseops-001",
        "program_type": "High-Ticket Agency Sprint",
        "cohort": "Cohort 8",
        "health_score": 95,
        "follow_up_count": 0,
    },
    {
        "name": "Elena Rostova",
        "ghl_contact_id": "demo-pulseops-002",
        "program_type": "Scale Mastermind",
        "cohort": "Cohort 8",
        "health_score": 88,
        "follow_up_count": 1,
    },
    {
        "name": "Derek Chen",
        "ghl_contact_id": "demo-pulseops-003",
        "program_type": "Remote Closer Academy",
        "cohort": "Cohort 9",
        "health_score": 64,
        "follow_up_count": 2,
    },
    {
        "name": "Chloe Davenport",
        "ghl_contact_id": "demo-pulseops-004",
        "program_type": "High-Ticket Agency Sprint",
        "cohort": "Cohort 8",
        "health_score": 42,
        "follow_up_count": 3,
    },
    {
        "name": "Liam O'Connor",
        "ghl_contact_id": "demo-pulseops-005",
        "program_type": "Executive RevOps Intensive",
        "cohort": "Cohort 1",
        "health_score": 98,
        "follow_up_count": 0,
    },
    {
        "name": "Fatima Al-Mansoor",
        "ghl_contact_id": "demo-pulseops-006",
        "program_type": "Scale Mastermind",
        "cohort": "Cohort 8",
        "health_score": 75,
        "follow_up_count": 1,
    },
    {
        "name": "Julian Mercado",
        "ghl_contact_id": "demo-pulseops-007",
        "program_type": "Remote Closer Academy",
        "cohort": "Cohort 9",
        "health_score": 35,
        "follow_up_count": 4,
    },
    {
        "name": "Sophie Tremblay",
        "ghl_contact_id": "demo-pulseops-008",
        "program_type": "High-Ticket Agency Sprint",
        "cohort": "Cohort 8",
        "health_score": 91,
        "follow_up_count": 0,
    },
    {
        "name": "Trevor Brooks",
        "ghl_contact_id": "demo-pulseops-009",
        "program_type": "Executive RevOps Intensive",
        "cohort": "Cohort 1",
        "health_score": 20,
        "follow_up_count": 5,
    },
    {
        "name": "Aaliyah Patel",
        "ghl_contact_id": "demo-pulseops-010",
        "program_type": "Scale Mastermind",
        "cohort": "Cohort 9",
        "health_score": 100,
        "follow_up_count": 0,
    },
)

# Runtime: Defines a small set of student-linked work items for the interview demo.
# Architecture: Shows human operations in ClickUp without implying that these tasks trigger live payment or access actions.
# Plain English: Provides one onboarding checklist, follow-up, payment exception, and offboarding example.
DEMO_WORK_ITEMS = (
    {
        "kind": "onboarding",
        "title": "Onboarding Checklist",
        "student_name": "Marcus Vance",
        "priority": 3,
        "tags": ["demo", "work-onboarding"],
        "actions": (
            "Send the welcome message",
            "Confirm kickoff call is scheduled",
            "Verify program access with the student",
        ),
    },
    {
        "kind": "csm-follow-up",
        "title": "CSM Follow-up",
        "student_name": "Derek Chen",
        "priority": 2,
        "tags": ["demo", "work-follow-up"],
        "actions": (
            "Review the missed milestone",
            "Agree on the next student action",
            "Record the interaction and next follow-up date",
        ),
    },
    {
        "kind": "payment-exception",
        "title": "Payment Exception",
        "student_name": "Chloe Davenport",
        "priority": 1,
        "tags": ["demo", "work-payment-exception", "health-red"],
        "actions": (
            "Verify the payment-provider event",
            "Contact the student using the approved billing process",
            "Record resolution; do not retry or refund from this demo task",
        ),
    },
    {
        "kind": "offboarding",
        "title": "Offboarding Case",
        "student_name": "Trevor Brooks",
        "priority": 1,
        "tags": ["demo", "work-offboarding", "health-red"],
        "actions": (
            "Confirm the authorized cancellation/refund request",
            "Route billing changes to the payment provider",
            "Coordinate access changes with the learning platform owner",
        ),
    },
)


# Runtime: Reports the deterministic preview and, when requested, inserts missing students and outbox work.
# Architecture: Makes the demo repeatable while keeping the default invocation non-mutating.
# Plain English: Shows what will be created, and only writes when --apply is supplied.
async def seed_demo_students(apply: bool) -> int:
    # Runtime: Prints the number of deterministic demo records in this run.
    # Architecture: Gives the operator a clear preview before external provisioning begins.
    # Plain English: Shows how many sample students are in the demo set.
    print(f"Demo records defined: {len(DEMO_STUDENTS)}")
    # Runtime: Exits before opening a database session unless the operator opts in.
    # Architecture: Prevents accidental writes from a casual script invocation.
    # Plain English: Preview mode does not create student records or ClickUp tasks.
    if not apply:
        for demo in DEMO_STUDENTS:
            print(
                f"  {demo['ghl_contact_id']}: {demo['name']} | "
                f"{demo['program_type']} / {demo['cohort']} | "
                f"health={demo['health_score']} | follow-ups={demo['follow_up_count']}"
            )
        print(
            "\nPreview only. Use --apply for PostgreSQL and outbox seeding, "
            "or --clickup-only to create ClickUp demo tasks directly."
        )
        return 0

    # Runtime: Imports persistence and assignment components only for the integrated database path.
    # Architecture: Keeps preview and direct ClickUp mode independent from PostgreSQL configuration.
    # Plain English: Loads database components only when saving student records.
    from sqlalchemy import select

    from src.core.config import settings
    from src.core.db import SessionLocal
    from src.domain.lifecycle import StudentStatus
    from src.models.messaging import OutboxEvent
    from src.models.student import Student
    from src.models.student_transition import StudentTransition
    from src.services.csm_allocator import CSMAllocator

    # Runtime: Parses the optional comma-separated CSM assignment pool.
    # Architecture: Matches production behavior while allowing the demo to run without configured CSMs.
    # Plain English: Finds the people available for sample assignment.
    csm_ids = tuple(
        csm_id.strip()
        for csm_id in (settings.CSM_IDS or "").split(",")
        if csm_id.strip()
    )
    # Runtime: Creates the allocator only when at least one configured CSM exists.
    # Architecture: Preserves the application's unassigned-intake behavior when no pool is configured.
    # Plain English: Enables balanced assignments when the team list is available.
    allocator = CSMAllocator(csm_ids) if csm_ids else None

    # Runtime: Opens one database session for the complete demo batch.
    # Architecture: Keeps each inserted student, transition, and outbox request in one transaction.
    # Plain English: Starts the database operation that makes demo students provisionable.
    async with SessionLocal() as session:
        # Runtime: Checks which deterministic external IDs are already present.
        # Architecture: Makes repeated demo runs idempotent rather than creating duplicate students/tasks.
        # Plain English: Finds sample students that were already added.
        existing_ids = set(
            (
                await session.scalars(
                    select(Student.ghl_contact_id).where(
                        Student.ghl_contact_id.in_(
                            demo["ghl_contact_id"] for demo in DEMO_STUDENTS
                        )
                    )
                )
            ).all()
        )
        created = 0

        # Runtime: Creates a student and matching transactional outbox command for each missing fixture.
        # Architecture: Sends demo records through the regular worker-driven ClickUp provisioning path.
        # Plain English: Adds each new sample to the normal onboarding pipeline.
        for demo in DEMO_STUDENTS:
            if demo["ghl_contact_id"] in existing_ids:
                print(f"[SKIP] Existing demo student: {demo['name']}")
                continue

            # Runtime: Assigns the next least-loaded configured CSM when the pool is available.
            # Architecture: Uses the production workload-aware selection rule on the same session.
            # Plain English: Chooses the sample student's owner fairly.
            assigned_csm_id = (
                await allocator.get_next_csm(session)
                if allocator
                else None
            )
            # Runtime: Creates a worker-claimable student record using current model fields.
            # Architecture: Keeps sample data aligned with database constraints and lifecycle values.
            # Plain English: Saves the fake student in the normal queued state.
            student = Student(
                name=demo["name"],
                ghl_contact_id=demo["ghl_contact_id"],
                health_score=demo["health_score"],
                status=StudentStatus.QUEUED.value,
                program_type=demo["program_type"],
                cohort=demo["cohort"],
                assigned_csm_id=assigned_csm_id,
                follow_up_count=demo["follow_up_count"],
            )
            # Runtime: Adds the student and flushes so PostgreSQL assigns its primary key.
            # Architecture: Makes the identifier available for the audit row and queue command.
            # Plain English: Saves the student first to get its database ID.
            session.add(student)
            await session.flush()
            # Runtime: Adds an initial audit record explaining that this is demo intake.
            # Architecture: Preserves the same lifecycle history expected for operational records.
            # Plain English: Records why the student entered the queue.
            session.add(StudentTransition(
                student_id=student.id,
                from_status=None,
                to_status=StudentStatus.QUEUED.value,
                event_type="student.demo-seeded",
                reason="Synthetic record created for the PulseOps live demo",
            ))
            # Runtime: Persists a provisioning command using the worker's strict `id` payload contract.
            # Architecture: Enlists Azure delivery in the same database transaction as student creation.
            # Plain English: Queues the student for normal ClickUp task creation.
            session.add(OutboxEvent(
                id=f"demo-provisioning-{student.id}",
                event_type="student.provisioning.requested",
                aggregate_id=student.id,
                payload={"id": student.id},
            ))
            # Runtime: Prevents this uncommitted student from being considered again within this batch.
            existing_ids.add(demo["ghl_contact_id"])
            created += 1
            print(
                f"[ADD] {demo['name']} | {demo['program_type']} / {demo['cohort']} | "
                f"CSM={assigned_csm_id or 'unassigned'}"
            )

        # Runtime: Commits the new students, audit rows, and outbox requests atomically.
        # Architecture: Prevents a student being stored without the work request needed to provision it.
        # Plain English: Saves each new student together with the task that will create its ClickUp record.
        await session.commit()

    # Runtime: Reports the count of newly inserted demo records.
    # Architecture: Helps operators confirm the effect of this idempotent seed run.
    # Plain English: Says how many sample students were added.
    print(f"\nAdded {created} demo student(s).")
    if created:
        print(
            "The outbox publisher and provisioning worker must be running "
            "to create the corresponding ClickUp tasks."
        )
    return created


# Runtime: Creates missing demo tasks directly in the configured ClickUp list.
# Architecture: Supports a presentation-only run without PostgreSQL or Azure Queue services.
# Plain English: Puts sample students on the ClickUp screen without creating database records.
async def seed_clickup_only() -> int:
    # Runtime: Imports the async HTTP client used for ClickUp requests.
    # Architecture: Keeps direct demo mode independent of database and queue settings.
    # Plain English: Connects to ClickUp for this one seed run.
    import httpx

    # Runtime: Reads credentials and the destination list from environment configuration.
    # Architecture: Keeps secrets and workspace identifiers out of source code.
    # Plain English: Gets the ClickUp account and list configured in .env.
    clickup_token = os.getenv("CLICKUP_API_TOKEN")
    clickup_list_id = os.getenv("CLICKUP_DEFAULT_LIST_ID")
    if not clickup_token or not clickup_list_id:
        raise RuntimeError("CLICKUP_API_TOKEN and CLICKUP_DEFAULT_LIST_ID must be configured")

    # Runtime: Builds ClickUp's list-scoped API base and authorization header.
    # Architecture: Restricts all demo writes to the configured task list.
    # Plain English: Chooses where the sample tasks will appear.
    base_url = f"https://api.clickup.com/api/v2/list/{clickup_list_id}"
    headers = {"Authorization": clickup_token}
    timeout = httpx.Timeout(20.0, connect=5.0)
    existing_tasks: dict[str, dict[str, object]] = {}

    # Runtime: Reuses one bounded HTTP client for list scanning and task creation.
    # Architecture: Pools connections and closes network resources after the batch.
    # Plain English: Opens the ClickUp connection for the demo.
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        # Runtime: Reads all task pages before creating anything.
        # Architecture: Prevents duplicates when the same demo script is run more than once.
        # Plain English: Checks which demo cards are already in the target list.
        page = 0
        while True:
            response = await client.get(
                f"{base_url}/task",
                params={"page": page, "include_closed": "true"},
            )
            response.raise_for_status()
            page_data = response.json()
            tasks = page_data.get("tasks")
            if not isinstance(tasks, list):
                raise RuntimeError("ClickUp task-list response did not contain a tasks array")
            for task in tasks:
                if (
                    isinstance(task, dict)
                    and isinstance(task.get("name"), str)
                    and isinstance(task.get("id"), str)
                ):
                    existing_tasks[task["name"]] = task
            if page_data.get("last_page") is True or len(tasks) < 100:
                break
            page += 1
            if page >= 100:
                raise RuntimeError("Stopped duplicate scan after 100 ClickUp pages")

        created = 0
        updated = 0
        # Runtime: Creates missing demo tasks and repairs tags on existing demo tasks.
        # Architecture: Makes direct writes idempotent while keeping old demo cards aligned with current labels.
        # Plain English: Adds missing students and fills in any absent cohort or health tags.
        for demo in DEMO_STUDENTS:
            task_name = f"Student: {demo['name']}"
            tags = build_student_tags(demo["cohort"], demo["health_score"])
            existing_task = existing_tasks.get(task_name)
            if existing_task:
                # Runtime: Extracts provider tag names already attached to this task.
                # Architecture: Avoids duplicate add-tag requests during repeated seed runs.
                # Plain English: Checks which demo labels the task already has.
                raw_tags = existing_task.get("tags", [])
                existing_tag_names = {
                    tag.get("name")
                    for tag in raw_tags
                    if isinstance(tag, dict) and isinstance(tag.get("name"), str)
                } if isinstance(raw_tags, list) else set()
                # Runtime: Adds each required label only when it is currently absent.
                # Architecture: Repairs existing demo cards without recreating or duplicating tasks.
                # Plain English: Updates older cards to show the same tags as new cards.
                added_tags = []
                task_id = str(existing_task["id"])
                for tag in tags:
                    if tag in existing_tag_names:
                        continue
                    tag_response = await client.post(
                        f"https://api.clickup.com/api/v2/task/{task_id}/tag/{tag}"
                    )
                    tag_response.raise_for_status()
                    added_tags.append(tag)
                if added_tags:
                    updated += 1
                print(
                    f"[UPDATE] Existing ClickUp demo task: {task_name} | "
                    f"tags added={','.join(added_tags) if added_tags else 'none'}"
                )
                continue

            # Runtime: Sets ClickUp priority from the sample health score.
            # Architecture: Makes low-health examples visually prominent for the demo.
            # Plain English: Flags the students who need more attention.
            priority = 1 if demo["health_score"] < 50 else 2 if demo["health_score"] < 75 else 3
            # Runtime: Formats operational fields into the task's readable description.
            # Architecture: Uses the same current Student model dimensions as integrated provisioning.
            # Plain English: Shows program, cohort, health, and follow-up details on the task.
            description = (
                "### Student Operations Demo\n"
                f"- **Program:** {demo['program_type']}\n"
                f"- **Cohort:** {demo['cohort']}\n"
                "- **Assigned CSM:** Unassigned (configure CSM_IDS for the integrated workflow)\n"
                f"- **Health score:** {demo['health_score']}/100\n"
                f"- **Follow-ups:** {demo['follow_up_count']}\n"
                f"- **Demo contact ID:** `{demo['ghl_contact_id']}`\n\n"
                "Synthetic record created for the PulseOps live demo."
            )
            # Runtime: Sends the task to ClickUp with its demo details and priority.
            # Architecture: Provides a visible ClickUp demo surface without implying a database write.
            # Plain English: Creates a sample student card in the chosen list.
            task_response = await client.post(
                f"{base_url}/task",
                json={
                    "name": task_name,
                    "description": description,
                    "priority": priority,
                    "tags": tags,
                },
            )
            task_response.raise_for_status()
            task_id = task_response.json().get("id")
            if not task_id:
                raise RuntimeError(f"ClickUp did not return a task ID for {task_name}")
            existing_tasks[task_name] = {
                "id": task_id,
                "name": task_name,
                "tags": [{"name": tag} for tag in tags],
            }
            created += 1
            print(
                f"[ADD] {task_name} | priority={priority} | "
                f"tags={','.join(tags)} | ClickUp task ID={task_id}"
            )

    # Runtime: Reports the ClickUp-only result and its persistence boundary.
    # Architecture: Distinguishes visible demo tasks from integrated student records.
    # Plain English: Confirms tasks were added and clarifies they are not in PostgreSQL.
    print(
        f"\nCreated {created} ClickUp demo task(s) and updated tags on "
        f"{updated} existing task(s)."
    )
    print("ClickUp-only mode does not create PostgreSQL student records or outbox events.")
    return created


# Runtime: Reads every task from a ClickUp list into a name-indexed mapping.
# Architecture: Supports duplicate detection and links related work to student tasks.
# Plain English: Looks up existing cards before adding or linking demo work.
async def fetch_clickup_tasks(client, list_id: str) -> dict[str, dict[str, object]]:
    # Runtime: Builds ClickUp's list-scoped endpoint for paginated task retrieval.
    # Architecture: Keeps reads and writes scoped to the intended student or operations list.
    # Plain English: Selects which list to inspect.
    list_url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    tasks_by_name: dict[str, dict[str, object]] = {}
    page = 0
    while True:
        # Runtime: Requests one page, including closed tasks for comprehensive duplicate checks.
        # Architecture: Avoids recreating demo tasks that were already completed or archived.
        # Plain English: Reads the next page of existing tasks.
        response = await client.get(
            list_url,
            params={"page": page, "include_closed": "true"},
        )
        response.raise_for_status()
        page_data = response.json()
        tasks = page_data.get("tasks")
        if not isinstance(tasks, list):
            raise RuntimeError(f"ClickUp task-list response for list {list_id} had no tasks array")
        for task in tasks:
            if (
                isinstance(task, dict)
                and isinstance(task.get("name"), str)
                and task.get("id") is not None
            ):
                tasks_by_name[task["name"]] = task
        if page_data.get("last_page") is True or len(tasks) < 100:
            return tasks_by_name
        page += 1
        if page >= 100:
            raise RuntimeError(f"Stopped duplicate scan for ClickUp list {list_id} after 100 pages")


# Runtime: Creates four idempotent demo work items linked to seeded student tasks.
# Architecture: Demonstrates CSM operations while explicitly avoiding real billing or access side effects.
# Plain English: Adds sample onboarding, follow-up, payment-exception, and offboarding work in ClickUp.
async def seed_clickup_work_items() -> int:
    # Runtime: Imports the async HTTP client used for ClickUp API calls.
    # Architecture: Keeps work-item demo mode independent from PostgreSQL and Azure.
    # Plain English: Connects to ClickUp for this sample-work batch.
    import httpx

    # Runtime: Reads account and list configuration from the loaded local environment.
    # Architecture: Keeps tokens external and allows a separate operational-work list.
    # Plain English: Gets the token and the student/work list destinations.
    clickup_token = os.getenv("CLICKUP_API_TOKEN")
    student_list_id = os.getenv("CLICKUP_DEFAULT_LIST_ID")
    work_list_id = os.getenv("CLICKUP_DEMO_OPERATIONS_LIST_ID") or student_list_id
    if not clickup_token or not student_list_id or not work_list_id:
        raise RuntimeError(
            "CLICKUP_API_TOKEN and CLICKUP_DEFAULT_LIST_ID must be configured"
        )

    # Runtime: Creates one bounded async client for reading student tasks and writing work items.
    # Architecture: Reuses HTTP connections and closes them after the complete demo batch.
    # Plain English: Opens a single ClickUp connection for the run.
    async with httpx.AsyncClient(
        headers={"Authorization": clickup_token},
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        # Runtime: Loads the student list so each sample work item can link to its student task.
        # Architecture: Keeps ClickUp as an actionable work surface while preserving a visible student context.
        # Plain English: Finds the student cards these work examples belong to.
        student_tasks = await fetch_clickup_tasks(client, student_list_id)

        # Runtime: Validates every demo item has a corresponding student task before writing.
        # Architecture: Prevents orphan work records and partial demos with missing relationship context.
        # Plain English: Stops if the student cards have not been seeded yet.
        missing_students = sorted({
            item["student_name"]
            for item in DEMO_WORK_ITEMS
            if f"Student: {item['student_name']}" not in student_tasks
        })
        if missing_students:
            names = ", ".join(missing_students)
            raise RuntimeError(
                f"Student tasks missing for: {names}. Run "
                "`python scripts/seed_clickup_students.py --clickup-only` first."
            )

        # Runtime: Reads current work-list tasks to make this run duplicate-safe.
        # Architecture: Supports repeated demos without multiplying operational cards.
        # Plain English: Checks whether these demo work items already exist.
        work_tasks = await fetch_clickup_tasks(client, work_list_id)
        created = 0
        updated = 0
        for item in DEMO_WORK_ITEMS:
            task_name = f"DEMO | {item['title']} | {item['student_name']}"
            student_task = student_tasks[f"Student: {item['student_name']}"]
            student_task_id = str(student_task["id"])
            student_url = student_task.get("url") or f"https://app.clickup.com/t/{student_task_id}"
            student = next(
                student for student in DEMO_STUDENTS
                if student["name"] == item["student_name"]
            )
            tags = list(dict.fromkeys([
                *item["tags"],
                *build_student_tags(student["cohort"], student["health_score"]),
            ]))
            existing_task = work_tasks.get(task_name)

            # Runtime: Repairs missing tags on an existing example without creating a duplicate task.
            # Architecture: Makes reruns converge on the intended demo labels.
            # Plain English: Adds any work-type tags that are missing from the existing card.
            if existing_task:
                raw_tags = existing_task.get("tags", [])
                existing_tag_names = {
                    tag.get("name")
                    for tag in raw_tags
                    if isinstance(tag, dict) and isinstance(tag.get("name"), str)
                } if isinstance(raw_tags, list) else set()
                existing_id = str(existing_task["id"])
                added_tags = []
                for tag in tags:
                    if tag in existing_tag_names:
                        continue
                    tag_response = await client.post(
                        f"https://api.clickup.com/api/v2/task/{existing_id}/tag/{tag}"
                    )
                    tag_response.raise_for_status()
                    added_tags.append(tag)
                if added_tags:
                    updated += 1
                print(
                    f"[SKIP] Existing work item: {task_name} | "
                    f"tags added={','.join(added_tags) if added_tags else 'none'}"
                )
                continue

            # Runtime: Formats the checklist and student-task link into a clear demo description.
            # Architecture: Makes the relationship visible without relying on unsupported custom fields.
            # Plain English: Explains the action, its student, and the tasks to complete.
            checklist = "\n".join(f"- [ ] {action}" for action in item["actions"])
            description = (
                "**DEMO ONLY — sample work item; no billing or access changes are executed.**\n\n"
                f"**Student:** [{item['student_name']}]({student_url})\n"
                f"**Work type:** {item['kind']}\n"
                f"**Program:** {student['program_type']} | **Cohort:** {student['cohort']}\n"
                f"**Demo health score:** {student['health_score']}/100\n\n"
                f"### Actions\n{checklist}"
            )
            # Runtime: Creates the work item in the configured operations list with its tags.
            # Architecture: Separates human follow-up tasks from the student record list when configured.
            # Plain English: Adds the sample action card to ClickUp.
            response = await client.post(
                f"https://api.clickup.com/api/v2/list/{work_list_id}/task",
                json={
                    "name": task_name,
                    "description": description,
                    "priority": item["priority"],
                    "tags": tags,
                },
            )
            response.raise_for_status()
            task_id = response.json().get("id")
            if not task_id:
                raise RuntimeError(f"ClickUp did not return a task ID for {task_name}")
            work_tasks[task_name] = {
                "id": task_id,
                "name": task_name,
                "tags": [{"name": tag} for tag in tags],
            }
            created += 1
            print(
                f"[ADD] {task_name} | student task={student_task_id} | "
                f"tags={','.join(tags)} | task ID={task_id}"
            )

    # Runtime: Reports both new work items and existing cards whose tags were repaired.
    # Architecture: Gives operators an audit-friendly summary without implying workflow execution.
    # Plain English: Tells how many demo work cards were added or updated.
    print(f"\nCreated {created} demo work item(s); updated tags on {updated} existing item(s).")
    print("All work items are labeled DEMO ONLY and do not execute billing or access changes.")
    if not os.getenv("CLICKUP_DEMO_OPERATIONS_LIST_ID"):
        print("Set CLICKUP_DEMO_OPERATIONS_LIST_ID to keep work items in a separate ClickUp list.")
    return created


# Runtime: Keeps the database engine alive for the complete async seed operation.
# Architecture: Ensures engine cleanup happens on the same event loop that used its connections.
# Plain English: Runs the seed operation and always closes its database resources.
async def run_seed(apply: bool, clickup_only: bool, work_items: bool) -> None:
    if clickup_only:
        await seed_clickup_only()
        return
    if work_items:
        if not apply:
            print("Preview only: would create four student-linked ClickUp demo work items:")
            for item in DEMO_WORK_ITEMS:
                print(f"  - DEMO | {item['title']} | {item['student_name']}")
            print("Use --work-items --apply to create the ClickUp tasks.")
            return
        await seed_clickup_work_items()
        return
    if not apply:
        await seed_demo_students(apply=False)
        return

    # Runtime: Imports the database engine only for integrated PostgreSQL seeding.
    # Architecture: Avoids initializing a database pool for direct ClickUp-only runs.
    # Plain English: Loads database cleanup support only when it is needed.
    from src.core.db import engine

    try:
        await seed_demo_students(apply=apply)
    finally:
        # Runtime: Disposes the shared async engine and its connection pool.
        # Architecture: Releases database resources within the event loop that created them.
        # Plain English: Closes the database connections used by this script.
        await engine.dispose()


# Runtime: Defines the command-line interface for previewing or applying the seed data.
# Architecture: Requires an explicit write flag for a script that creates persistent records.
# Plain English: Adds a safety switch before sample data is saved.
def main() -> None:
    # Runtime: Creates the parser used for operator-facing help and options.
    # Architecture: Keeps the default mode read-only.
    # Plain English: Prepares to read the command-line request.
    parser = argparse.ArgumentParser(
        description="Preview or seed synthetic students through the normal provisioning pipeline."
    )
    # Runtime: Adds the explicit flag that enables database writes.
    # Architecture: Makes accidental demo data insertion less likely.
    # Plain English: Requires --apply before adding sample records.
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create missing demo students and transactional provisioning requests.",
    )
    # Runtime: Adds a distinct direct-to-ClickUp demo mode.
    # Architecture: Separates screen-demo tasks from integrated database/outbox seeding.
    # Plain English: Creates ClickUp cards without needing PostgreSQL or Azure services.
    parser.add_argument(
        "--clickup-only",
        action="store_true",
        help="Create missing ClickUp demo tasks directly, without PostgreSQL records.",
    )
    # Runtime: Adds a distinct mode for operational work items linked to demo students.
    # Architecture: Keeps sample work separate from student provisioning and requires explicit write consent.
    # Plain English: Previews action cards by default and creates them only with --apply.
    parser.add_argument(
        "--work-items",
        action="store_true",
        help="Preview or seed four student-linked ClickUp work items; add --apply to create them.",
    )
    # Runtime: Parses the user's selected operating mode.
    # Architecture: Separates safe preview from an intentional seed run.
    # Plain English: Reads whether the user asked to actually create records.
    args = parser.parse_args()
    # Runtime: Executes the asynchronous seed operation and returns its completion.
    # Architecture: Runs database operations under one managed event loop.
    # Plain English: Starts the requested preview or insertion.
    # Runtime: Rejects conflicting write modes before any external or database side effect.
    # Architecture: Requires one explicit destination for demo writes.
    # Plain English: Makes the operator choose integrated seeding or ClickUp-only seeding.
    if args.clickup_only and args.work_items:
        parser.error("--clickup-only and --work-items cannot be used together")
    if args.apply and args.clickup_only:
        parser.error("--apply and --clickup-only cannot be used together")
    asyncio.run(run_seed(
        apply=args.apply,
        clickup_only=args.clickup_only,
        work_items=args.work_items,
    ))


# Runtime: Prevents imports from creating sample data as a side effect.
# Architecture: Keeps this maintenance module safe to inspect and test.
# Plain English: Runs the seeder only when launched directly.
if __name__ == "__main__":
    main()
