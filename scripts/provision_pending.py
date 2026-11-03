# Runtime: Provides environment-variable access for the fallback database URL.
# Architecture: Lets this operational script share deployment configuration with FastAPI.
# Summary: Imports operating-system helpers.
import os
# Runtime: Provides access to OS environment variables.
# Architecture: Used to retrieve DATABASE_URL if not set in settings.
# Summary: Imports os module.
import asyncio
# Runtime: Run async tasks and event loop.
# Architecture: Needed for asynchronous database and HTTP calls.
# Summary: Imports asyncio.
import httpx
# Runtime: Async HTTP client library.
# Architecture: Enables non-blocking HTTP requests to ClickUp API.
# Summary: Imports httpx.
from sqlalchemy.ext.asyncio import create_async_engine
# Runtime: Factory to create async SQLAlchemy engine.
# Architecture: Allows async DB interactions with PostgreSQL.
# Summary: Imports create_async_engine.
from sqlalchemy import text
# Runtime: Utility to construct raw SQL statements.
# Architecture: Provides parameterized query support.
# Summary: Imports text.
from src.core.config import settings
# Runtime: Loads configuration values such as DATABASE_URL and ClickUp tokens.
# Architecture: Centralizes config across application.
# Summary: Imports settings.

async def main():
    # Runtime: Main entrypoint for provisioning logic.
    # Architecture: Wraps DB and HTTP interactions in async context.
    # Summary: Defines main async function.
    # Runtime: Allows database and HTTP operations to be awaited without blocking the event loop.
    # Architecture: Follows the same cooperative-I/O model used by FastAPI handlers.
    # Summary: Starts one asynchronous provisioning pass.
    # Retrieve DB URL from settings or environment, defaulting to container postgres
    db_url = getattr(settings, "DATABASE_URL", None) or os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://postgres:postgres@db:5432/pulseops"
    )

    # Runtime: Tests and then normalizes the URL to the asyncpg driver when needed.
    # Architecture: Ensures engine is created with async driver.
    # Summary: Adjusts database URL if using sync postgres prefix
    if db_url.startswith("postgresql://"):
        # Runtime: Replaces the synchronous PostgreSQL scheme with SQLAlchemy's asyncpg scheme.
        # Architecture: Ensures the async engine uses a non-blocking PostgreSQL driver.
        # Summary: Normalizes the database URL for async access.
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Runtime: Logs the non-credential-bearing suffix of the configured URL.
    # Architecture: Preserves connection observability without exposing URL credentials.
    # Summary: Reports the database destination safely.
    print(f"Connecting to database: {db_url.split('@')[-1]}")
    # Runtime: Establishes async connection to PostgreSQL.
    # Architecture: Uses asyncpg driver for non-blocking operations.
    # Summary: Creates engine instance.
    engine = create_async_engine(db_url, echo=False)

    # Runtime: Opens a transaction-scoped async connection for the pending-row query.
    # Architecture: Reads the database-backed work queue without holding it during network calls.
    # Summary: Fetches students that still need provisioning.
    async with engine.begin() as conn:
        # Runtime: Executes the pending-student SELECT through the active connection.
        # Architecture: Reads the provisioning work queue from PostgreSQL.
        # Summary: Queries rows awaiting ClickUp provisioning.
        result = await conn.execute(
            text("SELECT id, name, ghl_contact_id FROM students WHERE status = 'pending'")
        )
        # Runtime: Materializes all returned database rows before leaving the connection context.
        # Architecture: Allows external API calls to run after releasing the DB connection.
        # Summary: Stores the pending batch in memory.
        students = result.fetchall()

    # Runtime: Materializes rows before the connection context closes.
    # Architecture: Separates short database I/O from the slower external API work.
    # Summary: Keeps the pending records available for the batch.
    print(f"Found {len(students)} pending student(s) to provision.")

    # Runtime: Disposes the engine before returning when the queue is empty.
    # Architecture: Ensures the no-op path releases async resources like the normal path.
    # Summary: Exits cleanly when there is no pending work.
    if not students:
        # Runtime: Reports that no records require processing.
        # Architecture: Gives scheduled runs an explicit no-work outcome.
        # Summary: Announces the empty batch.
        print("Done!")
        # Runtime: Releases the engine even on the early-return path.
        # Architecture: Prevents pooled connection resources from leaking.
        # Summary: Cleans up before exiting.
        await engine.dispose()
        # Runtime: Leaves the coroutine without entering the HTTP batch.
        # Architecture: Avoids unnecessary ClickUp client setup.
        # Summary: Ends the no-op run.
        return

    # Runtime: Prepares authentication and content metadata for each outbound request.
    # Architecture: This script creates its own outbound payload, so inbound FastAPI payload verification is not applicable.
    # Summary: Builds the headers ClickUp expects.
    headers = {
        "Authorization": settings.CLICKUP_API_TOKEN,
        "Content-Type": "application/json"
    }

    # Runtime: Reuses one asynchronous HTTP client and connection pool for the batch.
    # Architecture: Avoids blocking the event loop and repeated connection setup.
    # Summary: Opens one client for all ClickUp calls.
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Runtime: Iterates through the materialized pending rows.
        # Architecture: Gives each student an independent provisioning attempt.
        # Summary: Begins the outbound batch loop.
        for sid, name, ghl_id in students:
            # Runtime: Retains the source row identifiers needed for the eventual database update.
            # Architecture: Keeps each queue item independently recoverable if another item fails.
            # Summary: Begins one student's provisioning attempt.
            print(f"Provisioning {name}...")
            # Runtime: Creates the JSON body that httpx will serialize for ClickUp.
            # Architecture: Includes the stable source contact ID for traceability across systems.
            # Summary: Defines the external task details.
            payload = {
                "name": f"Student: {name}",
                "description": f"GHL Contact ID: {ghl_id}\nProvisioned via PulseOps Engine",
                "status": "TO DO",
                "priority": 3
            }
            # Runtime: Resolves the configured ClickUp list endpoint.
            # Architecture: Keeps deployment-specific routing in centralized settings.
            # Summary: Selects where the task will be created.
            url = f"https://api.clickup.com/api/v2/list/{settings.CLICKUP_DEFAULT_LIST_ID}/task"

            # Runtime: Begins per-student exception isolation.
            # Architecture: Keeps one failed ClickUp call from aborting the whole batch.
            # Summary: Attempts this student's provisioning.
            try:
                # Runtime: Chooses live API mode only when both required ClickUp settings exist.
                # Architecture: Keeps local runs safe while preserving the same completion transition.
                # Summary: Decides whether to create a real task or use a mock ID.
                # If ClickUp credentials are set, make the live call; otherwise mock the ID
                if settings.CLICKUP_API_TOKEN and settings.CLICKUP_DEFAULT_LIST_ID:
                    # Runtime: Awaits the network request instead of blocking the worker thread.
                    # Architecture: Preserves async behavior used by FastAPI-style services.
                    # Summary: Sends the task payload to ClickUp.
                    res = await client.post(url, json=payload, headers=headers)
                    # Runtime: Reads an ID only from an accepted create response.
                    # Architecture: Prevents failed API responses from being recorded as completed work.
                    # Summary: Verifies that ClickUp accepted the task.
                    if res.status_code in (200, 201):
                        # Runtime: Decodes the accepted response and extracts ClickUp's task ID.
                        # Architecture: Uses the external ID as the database correlation key.
                        # Summary: Captures the created task identifier.
                        task_id = res.json().get("id")
                    else:
                        # Runtime: Reports the non-success status and response body.
                        # Architecture: Preserves API diagnostics while leaving the row pending.
                        # Summary: Explains why this task was not recorded.
                        print(f" -> ClickUp API error: {res.status_code} {res.text}")
                        continue
                else:
                    # Runtime: Creates a deterministic identifier without making an external request.
                    # Architecture: Makes dry runs repeatable and avoids pretending a real ClickUp task exists.
                    # Summary: Uses a predictable mock task ID.
                    task_id = f"mock_{ghl_id}"

                # Runtime: Commits the completed state only after an external or mock task ID exists.
                # Architecture: The pending-to-completed transition is the idempotency checkpoint for normal reruns.
                # Summary: Records success so pending rows are not provisioned again.
                async with engine.begin() as conn:
                    await conn.execute(
                        text("UPDATE students SET status = 'completed', clickup_task_id = :task_id WHERE id = :id"),
                        {"task_id": str(task_id), "id": sid}
                    )
                # Runtime: Logs the identifier after the database update succeeds.
                # Architecture: Makes each queue transition observable for operations and troubleshooting.
                # Summary: Reports the task assigned to the student.
                print(f" -> Assigned ClickUp ID: {task_id} for {name}")

            # Runtime: Catches an unexpected per-student failure and continues with later rows.
            # Architecture: Leaves the failed row pending so a future run can retry it.
            # Summary: Isolates and reports one provisioning error.
            except Exception as e:
                # Runtime: Logs the isolated exception after the failed attempt.
                # Architecture: Leaves the row eligible for a later retry.
                # Summary: Reports this student's provisioning failure.
                print(f" -> Error provisioning {name}: {e}")

    # Runtime: Closes pooled database connections after all HTTP work completes.
    # Architecture: Releases async resources at the end of the worker lifecycle.
    # Summary: Shuts down the database engine.
    await engine.dispose()
    # Runtime: Prints completion only after cleanup has finished.
    # Architecture: Gives scheduled-job operators a clear terminal marker.
    # Summary: Announces that the batch is done.
    print("Done!")

# Runtime: Restricts batch execution to direct CLI use.
# Architecture: Keeps importing the script from triggering provisioning.
# Summary: Selects the command-line entrypoint.
if __name__ == "__main__":
    # Runtime: Creates and runs the event loop only for direct CLI execution.
    # Architecture: Keeps importing this module side-effect free.
    # Summary: Launches the asynchronous worker.
    asyncio.run(main())